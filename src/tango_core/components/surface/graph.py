# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Generic, YAML-graph-driven surface / power-plant component for tango.

``GraphSurface`` builds its TESPy network entirely from a
``power_plant.nodes``/``power_plant.edges`` block in the YAML, rather than
hardcoding a fixed topology in Python. One class
covers single-flash, AGS direct-heat, and any future topology; adding a new
plant design is a YAML change, not a new Python class.

Required naming convention (the one piece that can't be pure YAML — this is
wiring to the rest of the simulation, not plant layout, so it has to be an
explicit, documented contract rather than inferred from graph shape):

- Exactly one ``Source`` node named ``"inlet"`` — ``solve()`` writes
  ``T``/``p``/``m``/``fluid`` onto its outgoing connection from its
  ``inlet`` parameter each timestep.
- Exactly one ``Sink`` node named ``"outlet"`` — ``solve()`` forces its
  incoming connection's pressure to ``self.injection_pressure`` (the BC
  variable ``SystemBCIteration`` iterates), and reads ``self.outlet`` back
  off it after solving.
- Any node contributing to the plant's net output tags itself with
  ``role: net_electric`` or ``role: net_thermal`` (see ``ComponentRole`` in
  ``core/policies.py``). Untagged nodes (valves, separators, condensers,
  mixers) are solved as part of the network but not summed into either total.

Sign convention for role aggregation (no per-component-type branch
needed): TESPy's ``P.val``/``Q.val`` are positive when power/heat flows
*into* the fluid and negative when it flows *out*. Summing ``-P.val`` over
every ``net_electric`` node therefore adds turbines (negative P → positive
contribution) and subtracts compressors/pumps (positive P → negative
contribution) uniformly; summing ``-Q.val`` over ``net_thermal`` nodes gives
positive delivered heat for a heat exchanger rejecting heat to a
district-heating loop.

``type: PumpOrValve`` (in addition to the real TESPy component types) is
a per-node opt-in for a circulation point whose physically correct
resolution (a passive ``Valve``, or a real ``Compressor``) depends on
design-point conditions rather than being knowable up front -- see
``init()``/``_NetworkBundle``/``_check_pump_or_valve_validity``. It
builds and holds TWO full networks, tries the Valve-resolved one first
each ``solve()``, and falls back to the Compressor-resolved one if that's
physically invalid for the current timestep -- see
``docs/archive/bugs-fixed-in-tango.md``'s "AGS closed loop has no pump
anywhere" entry for the physical motivation.

Example YAML (AGS direct-heat — the topology that motivated this class):

    surface:
      type: 'graph'
      power_plant:
        nodes:
          inlet: {type: Source}
          district_heating_hx: {type: SimpleHeatExchanger, role: net_thermal, T_out: 323.15, pressure_ratio: 0.99}
          circulation_control: {type: PumpOrValve, role: net_electric, efficiency: 1.0}
          outlet: {type: Sink}
        edges:
          1: {source: inlet, target: district_heating_hx}
          2: {source: district_heating_hx, target: circulation_control}
          3: {source: circulation_control, target: outlet}

Unit conventions (TESPy network created with ``p_unit="bar"``, ``T_unit="C"``):

  - YAML pressures in Pa -> bar via x 1e-5; ``p_out_megapascals`` -> bar via x 10
  - Temperatures: K -> degC for TESPy input, TESPy degC -> K for output
  - Power: TESPy node ``.P.val``/``.Q.val`` in W (SI), regardless of the
    ``h_unit="kJ/kg"`` display setting
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import Field

from tango_core.components.surface.base import SurfaceComponent
from tango_core.core.constants import (
    BAR_TO_PA,
    C_TO_K_OFFSET,
    J_PER_KG_TO_KJ_PER_KG,
    K_TO_C_OFFSET,
    KJ_PER_KG_TO_J_PER_KG,
    PA_TO_BAR,
)
from tango_core.core.errors import (
    ConfigError,
    CoolingLimitError,
    InvalidPowerStateError,
    NegativeNetPowerError,
    NegativeNetThermalError,
    PassivePressureRiseError,
    TESPyConvergenceError,
    TESPyCoolPropError,
    ValveCannotRaisePressureError,
)
from tango_core.core.fluid_state import FluidState
from tango_core.core.fluid_utils import (
    friction_factor_haaland,
    mean_velocity,
    pressure_drop_friction,
    reynolds_number,
)
from tango_core.core.locked_state import LockedState
from tango_core.core.policies import ComponentRole
from tango_core.core.state_methods import StateMethods
from tango_core.core.stream import Stream

if TYPE_CHECKING:
    from tespy.connections import Connection

logger = logging.getLogger(__name__)

# node config "type" string -> TESPy class. Extend as new topologies need
# component types not yet listed here.
# "PumpOrValve" is deliberately NOT a key here -- it isn't a real TESPy
# class, it's resolved to "Valve" or "Compressor" first (see
# _build_bundle), and only the resolved name is looked up in this dict.
_COMPONENT_TYPES: dict[str, str] = {
    "Sink": "Sink",
    "Source": "Source",
    "Turbine": "Turbine",
    "Compressor": "Compressor",
    "Valve": "Valve",
    "DropletSeparator": "DropletSeparator",
    "Merge": "Merge",
    "SimpleHeatExchanger": "SimpleHeatExchanger",
    "HeatExchanger": "HeatExchanger",
    "CycleCloser": "CycleCloser",
}

# Floating-point solver-noise tolerance for the "a pump can't generate
# power" check below (solve()) -- a genuinely unphysical negative-power
# state is many watts to kilowatts in practice, so this only exists to
# avoid a false positive from sub-milliwatt solver residual sitting
# exactly at zero, not to mask a real violation.
_PUMP_POWER_TOLERANCE_W = 1e-3

# Port-suffixed connection attrs: a bare YAML key applies to a node's ONE
# relevant connection (its single outgoing connection, or incoming for a
# Sink); the "_out{N}" suffixed form (e.g. "h0_out1", "fluid_out2") instead
# targets specifically the connection whose `source_id == f"out{N}"` --
# needed for a node with more than one outgoing port, e.g. a dual-fluid
# HeatExchanger (primary loop on out1, a secondary/ORC working-fluid loop on
# out2). Module-level, not a GraphSurface
# class attribute: a leading-underscore attribute on a Pydantic BaseModel
# becomes a ModelPrivateAttr descriptor at class-level access, not a plain
# dict -- see _apply_connection_config's staticmethod, which needs to read
# this without an instance.
_PORT_SUFFIXED_ATTRS: dict[str, str] = {
    "h0_out": "h0",  # TESPy guess value (kJ/kg), not a fixed constraint
    "p0_megapascals_out": "p0",  # TESPy guess value, not a fixed constraint; MPa -> bar
    "fluid_out": "fluid",
    "vapor_mass_fraction_out": "x",
}

_NODE_KEYS: frozenset[str] = frozenset(
    {
        "type",
        "role",
        "efficiency",
        "pressure_ratio",
        "pressure_ratio1",
        "pressure_ratio2",
        "ttd_l",
        "p_out_megapascals",
        "T_out",
        "vapor_mass_fraction_out",
        "subcooling_K",
        # Read by DoubletEconomicComponent for cooling-tower cost.
        "Subtype",
        "set_number",
        "design",
        "cooling_tower_mode",
    },
)
"""Every key a ``power_plant.nodes`` entry may have, besides the ``_PORT_SUFFIXED_ATTRS``
forms. Anything else is rejected, so a typo or a renamed key fails loudly
instead of being silently ignored."""


def _check_node_keys(name: str, cfg: dict[str, Any]) -> None:
    """Raise ``ConfigError`` for any key in node ``name``'s config that nothing reads."""
    unknown = []
    for key in cfg:
        prefix = key.rstrip("0123456789")
        if key in _NODE_KEYS or (prefix != key and prefix in _PORT_SUFFIXED_ATTRS):
            continue
        unknown.append(key)
    if unknown:
        hint = (
            " (p0_out{N} was renamed p0_megapascals_out{N}, given in MPa)"
            if any(k.rstrip("0123456789") == "p0_out" for k in unknown)
            else ""
        )
        raise ConfigError(
            f"power_plant.nodes.{name}: unknown key(s) {sorted(unknown)}{hint}. Allowed: "
            f"{sorted(_NODE_KEYS)}, plus {sorted(p + '{N}' for p in _PORT_SUFFIXED_ATTRS)}.",
        )


# Mirror-image tolerance for the "a valve can't raise pressure" check below
# (solve()): a real throttle valve is passive and dissipative, so it can
# only ever DROP pressure. A resolved network where a Valve node's outlet
# ends up more than this many bar above its inlet means the design's
# natural driving pressure fell short of what was needed there and a real
# pump belongs at that node instead -- not solver noise.
_VALVE_PRESSURE_INCREASE_TOLERANCE_BAR = 1e-6

# TESPy component types that do no work on the fluid, so pressure can never
# rise across them (see _check_passive_pressure). A dual-fluid HeatExchanger
# is checked per side (in1 -> out1, in2 -> out2); every other type is
# checked from each inlet to each outlet.
_PASSIVE_TYPES: frozenset[str] = frozenset(
    {"Valve", "DropletSeparator", "Merge", "SimpleHeatExchanger", "HeatExchanger", "CycleCloser"},
)

# A free-compression violation that matters is bars, not pascals; this only
# absorbs TESPy's own solver residual on pressures that are meant to be
# equal (e.g. across a Merge).
_PASSIVE_PRESSURE_RISE_TOLERANCE_BAR = 1e-3

# Absorbs solver residual on an outlet temperature that sits exactly at the
# site's cooling limit; a real violation is a kelvin or more.
_COOLING_LIMIT_TOLERANCE_K = 1e-3


def _ls() -> LockedState[float]:
    ls: LockedState[float] = LockedState(float("nan"))
    ls.mark_stale()
    return ls


def _ls_dict() -> LockedState[dict[str, dict[str, float]]]:
    ls: LockedState[dict[str, dict[str, float]]] = LockedState({})
    ls.mark_stale()
    return ls


# ---------------------------------------------------------------------------
# Dual-network bundle (PumpOrValve)
# ---------------------------------------------------------------------------


@dataclass
class _NetworkBundle:
    """One fully-built TESPy network + its component/connection lookups.

    Two of these exist only when ``power_plant.nodes`` includes a
    ``type: PumpOrValve`` node (see ``init()``) -- one with that node
    resolved to a passive ``Valve``, one to a real ``Compressor`` --
    because TESPy networks are built once, not swapped component-by-
    component mid-simulation. ``solve()`` tries the valve bundle first
    and falls back to the compressor bundle if it's physically invalid
    (see ``_check_pump_or_valve_validity``), reassigning
    ``GraphSurface``'s working attrs to whichever bundle succeeded via
    ``_activate_bundle`` so the rest of ``solve()`` doesn't need to know
    which one is active.

    There is no way to get ONE TESPy network to select the physically
    valid resolution itself: choosing between a passive ``Valve`` and a
    real ``Compressor`` here is a discrete either/or decision (does the
    natural driving pressure suffice, yes/no), and TESPy solves square
    systems of equations, not an optimization or a complementarity
    condition -- there's no single equation that would express "pick
    whichever component is feasible." Building and holding two complete
    networks, one per resolution, is the cost of getting that decision
    right automatically per design point rather than requiring a manual,
    per-config component choice -- see
    ``docs/archive/bugs-fixed-in-tango.md``'s "AGS closed loop has no pump
    anywhere" entry for the physical motivation.
    """

    network: Any
    """The built TESPy network."""
    conns: list[Connection]
    """All TESPy connections of the network."""
    nodes: dict[str, Any]
    """TESPy components keyed by their power_plant node name."""
    net_electric_nodes: list[Any]
    """Nodes tagged role=net_electric, summed as -P into net_power_W; a PumpOrValve node is left
    out of the network where it resolves to a Valve, which does no work."""
    net_thermal_nodes: list[Any]
    """Nodes tagged role=net_thermal, summed into net_thermal_W."""
    inlet_conn: Connection
    """Connection leaving the network's inlet source."""
    outlet_conn: Connection
    """Connection entering the network's outlet sink."""


# ---------------------------------------------------------------------------
# State / History
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GraphSurfaceState(StateMethods):
    """Full simulation state for one graph-surface solve step.

    Every field is ``LockedState``-wrapped — writable exactly once per
    timestep, ``LockedState[float]`` for scalars and
    ``LockedState[dict[str, dict[str, float]]]`` for ``node_detail``.
    ``mark_all_stale()`` (inherited from ``StateMethods``) is called by the
    orchestrator (via ``Component.mark_all_stale()``) immediately before
    each ``solve()``.
    """

    h_inlet: LockedState[float] = field(default_factory=_ls)
    """Specific enthalpy (J/kg) arriving on ``inlet``; set on TESPy's inlet connection as-is."""
    T_inlet: LockedState[float] = field(default_factory=_ls)
    """Inlet temperature from the production well (K), derived from (``h_inlet``, ``P_inlet``)."""
    P_inlet: LockedState[float] = field(default_factory=_ls)
    """Inlet pressure from the production well, before the surface pipe (Pa)."""
    mass_rate: LockedState[float] = field(default_factory=_ls)
    """Mass flow rate through the plant (kg/s)."""

    dP_pipe: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Friction pressure drop across the surface pipe (Pa)."""
    P_tespy_inlet: LockedState[float] = field(default_factory=_ls)
    """Pressure passed to TESPy inlet = P_inlet - dP_pipe (Pa)."""

    net_power_W: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Sum of -P.val (W) over role=net_electric nodes. 0 if none tagged."""
    net_thermal_W: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Sum of -Q.val (W) over role=net_thermal nodes. 0 if none tagged."""

    h_outlet: LockedState[float] = field(default_factory=_ls)
    """Specific enthalpy (J/kg) on TESPy's outlet connection -- what ``outlet`` carries."""
    T_outlet: LockedState[float] = field(default_factory=_ls)
    """Outlet temperature returned to the injection well (K)."""
    P_outlet: LockedState[float] = field(default_factory=_ls)
    """Outlet pressure returned to the injection well (Pa)."""
    rho: LockedState[float] = field(default_factory=_ls)
    """Fluid density at the outlet (kg/m3)."""
    mu: LockedState[float] = field(default_factory=_ls)
    """Fluid dynamic viscosity at the outlet (Pa s)."""

    node_detail: LockedState[dict[str, dict[str, float]]] = field(default_factory=_ls_dict)
    """Per-node diagnostic snapshot, keyed by node name then quantity
    (``P``/``Q`` in W where the component has them, ``T``/``p``/``m`` in
    SI units off that node's outgoing connection where one exists).
    Rebuilt fresh every ``solve()`` via whole-value ``update()`` (there's no
    write-once concern to protect since it's fully recomputed, not
    accumulated, but it's still ``LockedState``-wrapped like every other
    field here for uniformity — see ``mark_all_stale()``). ``{}`` if
    ``record_node_detail=False`` on the component. This is a generic
    replacement for hardcoded per-component named fields — works for any
    topology, at the cost of dict-key access instead of attribute access.
    """


@dataclass
class GraphSurfaceHistory:
    """Per-timestep history of graph-surface scalar and per-node state.

    One list field per ``GraphSurfaceState`` attribute (TANGO Commandment:
    every ``*State`` attribute must have an analog in its ``*History``
    class) — see ``record()``. ``node_detail`` is the one field whose
    analog is NOT a same-named, same-shaped list: it's a
    ``dict[node][quantity] -> value`` snapshot, so its time-series analog
    is ``node_history`` (``dict[node][quantity] -> list[value]``, transposed
    by node/quantity rather than by timestep) — a flat
    ``node_detail: list[dict]`` would just duplicate ``node_history`` in a
    clumsier shape.
    """

    h_inlet: list[float] = field(default_factory=list)
    h_outlet: list[float] = field(default_factory=list)
    T_inlet: list[float] = field(default_factory=list)
    """Per-timestep inlet temperature (K)."""
    T_outlet: list[float] = field(default_factory=list)
    """Per-timestep outlet temperature (K)."""
    P_inlet: list[float] = field(default_factory=list)
    """Per-timestep inlet pressure (Pa)."""
    P_outlet: list[float] = field(default_factory=list)
    """Per-timestep outlet pressure (Pa)."""
    mass_rate: list[float] = field(default_factory=list)
    """Per-timestep mass flow rate (kg/s)."""
    dP_pipe: list[float] = field(default_factory=list)  # noqa: N815
    """Per-timestep friction pressure drop across the surface pipe (Pa)."""
    P_tespy_inlet: list[float] = field(default_factory=list)
    """Per-timestep pressure passed to the TESPy inlet (Pa)."""
    rho: list[float] = field(default_factory=list)
    """Per-timestep fluid density at the outlet (kg/m3)."""
    mu: list[float] = field(default_factory=list)
    """Per-timestep fluid dynamic viscosity at the outlet (Pa s)."""
    net_power_W: list[float] = field(default_factory=list)  # noqa: N815
    """Per-timestep net electric power of the role=net_electric nodes, before economics-level parasitic loads (W)."""
    net_thermal_W: list[float] = field(default_factory=list)  # noqa: N815
    """Per-timestep net thermal power of the role=net_thermal nodes (W)."""

    node_history: dict[str, dict[str, list[float]]] = field(default_factory=dict)
    """``node_history[node_name][quantity]`` -> time series. Populated
    lazily from ``state.node_detail``; stays empty if
    ``record_node_detail=False``. Keys appear the first timestep a node
    reports that quantity; every recorded node/quantity pair grows one
    entry per ``record()`` call so all lists stay the same length."""

    def record(self, state: GraphSurfaceState) -> None:
        """Append a snapshot of ``state`` as one timestep entry."""
        self.h_inlet.append(state.h_inlet.get_fresh())
        self.h_outlet.append(state.h_outlet.get_fresh())
        self.T_inlet.append(state.T_inlet.get_fresh())
        self.T_outlet.append(state.T_outlet.get_fresh())
        self.P_inlet.append(state.P_inlet.get_fresh())
        self.P_outlet.append(state.P_outlet.get_fresh())
        self.mass_rate.append(state.mass_rate.get_fresh())
        self.dP_pipe.append(state.dP_pipe.get_fresh())
        self.P_tespy_inlet.append(state.P_tespy_inlet.get_fresh())
        self.rho.append(state.rho.get_fresh())
        self.mu.append(state.mu.get_fresh())
        self.net_power_W.append(state.net_power_W.get_fresh())
        self.net_thermal_W.append(state.net_thermal_W.get_fresh())

        for node_name, values in state.node_detail.get_fresh().items():
            node_hist = self.node_history.setdefault(node_name, {})
            for quantity, value in values.items():
                node_hist.setdefault(quantity, []).append(value)


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


class GraphSurface(SurfaceComponent):
    """TESPy-backed surface / power plant with topology read entirely from YAML.

    See module docstring for the inlet/outlet/role naming contract. TESPy
    objects are built once in ``init()`` and stored as private (non-Pydantic,
    leading-underscore) attributes, excluded from ``model_dump()`` — on
    restore, call ``init()`` again to rebuild the network.
    """

    power_plant: dict[str, Any] = Field(default_factory=dict, frozen=True)
    """``{"nodes": {name: {type, role?, ...attrs}}, "edges": {n: {source, target,
    source_port?, target_port?}}}``. See module docstring for the full shape.
    """
    well_spacing: float = Field(default=707.0, frozen=True)
    """Injector-to-producer distance (m), used as surface pipe length,
    before the Darcy-Weisbach friction drop to the TESPy inlet."""
    record_node_detail: bool = Field(default=True, frozen=True)
    """If True (default), populate state.node_detail / history.node_history
    with every node's P/Q/T/p/m each solve(). Set False to skip this
    (e.g. a large network run over many timesteps where the extra
    bookkeeping/storage isn't worth it)."""

    # ---- Runtime state / history ----
    state: GraphSurfaceState = Field(default_factory=GraphSurfaceState)
    """Plant state of the current solve; an orchestrator that re-solves within a timestep restores
    it first."""
    history: GraphSurfaceHistory = Field(default_factory=GraphSurfaceHistory)
    """Per-timestep record of the plant state."""

    def record(self, timestep: int) -> None:
        """Raise if the converged timestep delivers negative power or heat, then record it.

        A plant with a turbine delivers negative power when the turbine no
        longer covers the plant's own pumps, and a plant with ``role:
        net_thermal`` exchangers delivers negative heat when the produced
        fluid has cooled so far (e.g. once the reservoir is depleted) that
        those exchangers would heat it instead. Both are checked here, once
        per timestep on the converged state, rather than in ``solve()``: the
        injection-enthalpy iteration's first pass starts a closed loop from
        the cold seed, whose produced fluid is legitimately too cool for a
        solve or two before the loop converges.

        Only a plant with a turbine is expected to make power. A plant
        without one (e.g. a direct-heat plant whose only electric node is a
        circulation pump) is always a net consumer, which is its correct
        state, and the economics count its power as a by-product cost.

        Raises:
            NegativeNetPowerError: with the net electric output.
            NegativeNetThermalError: with the net thermal output.
        """
        net_power_W = self.state.net_power_W.get_fresh()  # noqa: N806
        has_generator = any(type(node).__name__ == "Turbine" for node in self._net_electric_nodes)
        if has_generator and net_power_W < 0:
            raise NegativeNetPowerError(
                f"surface plant net_power_W={net_power_W:.1f} W is negative at timestep {timestep} -- "
                "the surface plant is a net consumer, not producer, of electricity (turbine output no "
                "longer covers its own surface pump parasitic load).",
            )
        net_thermal_W = self.state.net_thermal_W.get_fresh()  # noqa: N806
        if self._net_thermal_nodes and net_thermal_W < 0:
            raise NegativeNetThermalError(
                f"surface plant net_thermal_W={net_thermal_W:.1f} W is negative at timestep {timestep} -- "
                "the produced fluid is too cool for the plant to deliver any heat (its net_thermal "
                "exchangers would heat the fluid instead).",
            )
        super().record(timestep)

    # ------------------------------------------------------------------
    # Lifecycle: build TESPy network
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Build the TESPy network(s) from ``power_plant.nodes``/``edges``.

        Normally builds exactly one network. If any node's ``type`` is
        ``PumpOrValve``, builds TWO instead -- one resolving every such
        node to ``Valve``, one to ``Compressor`` -- and activates the
        Valve one first; ``solve()`` falls back to the Compressor one if
        the Valve one turns out physically invalid for a given timestep's
        conditions. See ``_NetworkBundle``'s docstring for why this is
        two full networks rather than one smarter one.
        """
        pp = self.power_plant
        node_cfgs: dict[str, dict[str, Any]] = pp.get("nodes", {})
        edge_cfgs: dict[str, dict[str, Any]] = pp.get("edges", {})

        self._validate_pressure_monotonicity(node_cfgs, edge_cfgs)

        self._dual_mode = any(cfg.get("type") == "PumpOrValve" for cfg in node_cfgs.values())
        if self._dual_mode:
            self._valve_bundle = self._build_bundle(
                node_cfgs,
                edge_cfgs,
                "Valve",
                self.common.coolprop_backend,
            )
            self._compressor_bundle = self._build_bundle(
                node_cfgs,
                edge_cfgs,
                "Compressor",
                self.common.coolprop_backend,
            )
            self._activate_bundle(self._valve_bundle)
        else:
            # "Compressor" here is an inert default: no node in this config
            # is type: PumpOrValve, so no node actually gets resolved by it.
            self._activate_bundle(
                self._build_bundle(node_cfgs, edge_cfgs, "Compressor", self.common.coolprop_backend),
            )

    @staticmethod
    def _build_bundle(
        node_cfgs: dict[str, dict[str, Any]],
        edge_cfgs: dict[str, dict[str, Any]],
        pump_or_valve_resolution: str,
        backend: str,
    ) -> _NetworkBundle:
        """Build one complete TESPy network, resolving any ``PumpOrValve`` node.

        Every ``type: PumpOrValve`` node becomes a real ``pump_or_valve_resolution``
        (``"Valve"`` or ``"Compressor"``) TESPy component in the network this
        builds; every other node is built exactly as its own ``type`` says,
        unaffected by ``pump_or_valve_resolution``. Called once (with an
        inert ``pump_or_valve_resolution``) for a config with no
        ``PumpOrValve`` node, or twice (once per resolution) for one that
        has one -- see ``init()``.
        """
        import tespy.components as tespy_components  # noqa: PLC0415
        from tespy.components import Sink, Source  # noqa: PLC0415
        from tespy.connections import Connection  # noqa: PLC0415
        from tespy.networks import Network  # noqa: PLC0415

        # TESPy manages its own logger ("TESPyLogger") independent of the
        # standard logging config (see ``cli.py``'s
        # ``_configure_logging``, which syncs it for CLI runs only). Any
        # caller building a GraphSurface directly via the Workflow API
        # (e.g. applications/*/sweep.py, which never goes
        # through the CLI) would otherwise get TESPy's intermediate
        # solver-iteration bound-violation warnings ("Invalid value for
        # pr/zeta...") printed at WARNING level, even though these are
        # normal, expected noise during convergence and not failures, so
        # it's silenced by default. Set here, not just in the CLI, so
        # every caller of GraphSurface gets quiet-by-default TESPy output
        # rather than only the CLI path. MUST come after the imports
        # above: tespy.tools.logger's own module-level code sets this
        # same logger back to DEBUG on first import, which would silently
        # undo an earlier setLevel() call the first time anything
        # actually imports tespy.
        logging.getLogger("TESPyLogger").setLevel(logging.ERROR)

        nodes: dict[str, Any] = {}
        for name, cfg in node_cfgs.items():
            type_name = cfg.get("type")
            resolved_type = pump_or_valve_resolution if type_name == "PumpOrValve" else type_name
            if resolved_type not in _COMPONENT_TYPES:
                raise ValueError(
                    f"power_plant.nodes.{name}: unknown TESPy component type {type_name!r} "
                    f"(known: {sorted(_COMPONENT_TYPES)}, plus 'PumpOrValve')",
                )
            tespy_cls = getattr(tespy_components, _COMPONENT_TYPES[resolved_type])
            nodes[name] = tespy_cls(name)

        if not isinstance(nodes.get("inlet"), Source):
            raise ValueError(
                "power_plant.nodes must include exactly one Source node named 'inlet'",
            )
        if not isinstance(nodes.get("outlet"), Sink):
            raise ValueError(
                "power_plant.nodes must include exactly one Sink node named 'outlet'",
            )

        conns: list[Connection] = []
        for edge in edge_cfgs.values():
            source = nodes[edge["source"]]
            target = nodes[edge["target"]]
            conns.append(
                Connection(
                    source,
                    edge.get("source_port", "out1"),
                    target,
                    edge.get("target_port", "in1"),
                ),
            )

        net = Network(iterinfo=False)
        net.units.set_defaults(
            pressure="bar",
            pressure_difference="bar",
            temperature="degC",
            enthalpy="kJ / kg",
        )
        net.add_conns(*conns)

        # ---- Per-node fixed attributes (efficiency, T_out, p_out, ...) ----
        for name, cfg in node_cfgs.items():
            _check_node_keys(name, cfg)
            GraphSurface._apply_node_config(nodes[name], conns, cfg, backend)

        # ---- Role-tagged nodes, for net power/thermal aggregation ----
        net_electric = []
        net_thermal = []
        for name, cfg in node_cfgs.items():
            role = cfg.get("role")
            if role == ComponentRole.NET_ELECTRIC:
                # A Valve has no TESPy `P` attribute at all -- it's passive
                # and does no work by construction (isenthalpic), unlike a
                # Compressor/Turbine, so it's excluded from the net-power
                # sum rather than included at a guaranteed-zero
                # contribution. It's still solved as part of the network
                # and still checked for physical validity every solve()
                # (see _check_pump_or_valve_validity) -- just not summed
                # here, since there's nothing on it to sum.
                if type(nodes[name]).__name__ != "Valve":
                    net_electric.append(nodes[name])
            elif role == ComponentRole.NET_THERMAL:
                net_thermal.append(nodes[name])
            elif role is not None:
                raise ValueError(
                    f"power_plant.nodes.{name}: unknown role {role!r} "
                    f"(expected one of {[r.value for r in ComponentRole]})",
                )

        return _NetworkBundle(
            network=net,
            conns=conns,
            nodes=nodes,
            net_electric_nodes=net_electric,
            net_thermal_nodes=net_thermal,
            inlet_conn=next(c for c in conns if c.source.label == "inlet"),
            outlet_conn=next(c for c in conns if c.target.label == "outlet"),
        )

    def _activate_bundle(self, bundle: _NetworkBundle) -> None:
        """Point every working attr ``solve()``/``_collect_node_detail()`` reads at ``bundle``."""
        self._network = bundle.network
        self._conns = bundle.conns
        self._nodes = bundle.nodes
        self._net_electric_nodes = bundle.net_electric_nodes
        self._net_thermal_nodes = bundle.net_thermal_nodes
        self._inlet_conn = bundle.inlet_conn
        self._outlet_conn = bundle.outlet_conn

    @staticmethod
    def _validate_pressure_monotonicity(
        node_cfgs: dict[str, dict[str, Any]],
        edge_cfgs: dict[str, dict[str, Any]],
    ) -> None:
        """Check that fixed ``p_out_megapascals`` values decrease monotonically downstream.

        Algorithm: walk upstream from every node with a fixed p_out,
        stopping at pressure-increasing ``Compressor`` nodes, flag any
        downstream p_out that exceeds an upstream one.

        Known gap, not covered by this check (see docs/tango_tasks.md):
        nodes whose pressure is solved via ``Merge``'s pressure-equality
        constraint rather than an explicit ``p_out_megapascals`` (e.g.
        ``condensate_pump``/``brine_pump`` in the single-flash examples), and components with
        no pressure spec at all (e.g. AGS_direct_heat.yml's ``district_heating_hx``, whose
        pressure is implicitly whatever gap exists between two unrelated
        boundary conditions) — neither is caught by this walk since it only
        traces nodes that declare ``p_out_megapascals`` explicitly.
        """
        p_out_values: dict[str, float] = {
            name: float(cfg["p_out_megapascals"])
            for name, cfg in node_cfgs.items()
            if "p_out_megapascals" in cfg
        }

        pressure_increasing_types = {"Compressor", "PumpOrValve"}

        upstream_map: dict[str, list[str]] = {}
        for edge in edge_cfgs.values():
            upstream_map.setdefault(edge["target"], []).append(edge["source"])

        def find_upstream_p_out(node_name: str, visited: set[str]) -> list[tuple[str, float]]:
            if node_name in visited:
                return []
            visited.add(node_name)
            results: list[tuple[str, float]] = []
            for upstream in upstream_map.get(node_name, []):
                upstream_type = node_cfgs.get(upstream, {}).get("type", "")
                if upstream_type in pressure_increasing_types:
                    continue
                if upstream in p_out_values:
                    results.append((upstream, p_out_values[upstream]))
                results.extend(find_upstream_p_out(upstream, visited))
            return results

        errors: list[str] = []
        for name, p_out in p_out_values.items():
            comp_type = node_cfgs.get(name, {}).get("type", "")
            if comp_type in pressure_increasing_types:
                continue
            for upstream_name, upstream_p_out in find_upstream_p_out(name, set()):
                if p_out > upstream_p_out:
                    errors.append(
                        f"{name}.p_out_megapascals ({p_out} MPa) > "
                        f"{upstream_name}.p_out_megapascals ({upstream_p_out} MPa)",
                    )

        if errors:
            raise ConfigError(
                "power_plant.nodes pressure configuration is not monotonically "
                "decreasing along the flow path:\n  " + "\n  ".join(errors),
            )

    @staticmethod
    def _apply_node_config(node: Any, conns: list[Connection], cfg: dict[str, Any], backend: str) -> None:
        """Apply fixed component/connection attributes from one node's YAML config.

        Component-level: ``efficiency`` -> ``eta_s`` (Turbine/Compressor);
        ``pressure_ratio`` -> ``pr`` (any component TESPy gives a ``pr``
        parameter, e.g. ``SimpleHeatExchanger``/``HeatExchanger`` — a
        RATIO, not an absolute value, so it scales with whatever pressure
        actually arrives at this node rather than fixing one; added for
        ``AGS_direct_heat.yml``'s ``district_heating_hx``, which needs its own
        pressure-drop spec once it's no longer the last node before the
        network's outlet Sink — see that YAML's ``circulation_control`` comment for
        why); ``pressure_ratio1``/``pressure_ratio2`` -> ``pr1``/``pr2``
        (a two-sided ``HeatExchanger`` has independent pressure ratios per
        side, unlike ``SimpleHeatExchanger``'s single ``pr`` -- added for a
        dual-fluid ``HeatExchanger``, see ``_apply_connection_config``'s
        docstring for why a dual-fluid node needs per-port connection
        attributes too); ``ttd_l`` -> ``ttd_l`` (HeatExchanger terminal
        temperature difference). ``efficiency`` is skipped for a node
        resolved to ``Valve`` (TESPy's ``Valve`` has no ``eta_s`` attribute
        at all) -- this is how a ``type: PumpOrValve`` node's ``efficiency``
        (needed by its Compressor-resolved bundle) is silently a no-op in
        its Valve-resolved bundle, rather than an error, without either
        bundle needing its own separate config.
        """
        type_name = type(node).__name__
        component_attrs: dict[str, Any] = {}
        if "efficiency" in cfg and type_name != "Valve":
            component_attrs["eta_s"] = float(cfg["efficiency"])
        if "pressure_ratio" in cfg:
            component_attrs["pr"] = float(cfg["pressure_ratio"])
        if "pressure_ratio1" in cfg:
            component_attrs["pr1"] = float(cfg["pressure_ratio1"])
        if "pressure_ratio2" in cfg:
            component_attrs["pr2"] = float(cfg["pressure_ratio2"])
        if "ttd_l" in cfg:
            component_attrs["ttd_l"] = float(cfg["ttd_l"])
        if component_attrs:
            node.set_attr(**component_attrs)

        GraphSurface._apply_connection_config(node, conns, cfg, type_name, backend)

    @staticmethod
    def _apply_connection_config(
        node: Any,
        conns: list[Connection],
        cfg: dict[str, Any],
        type_name: str,
        backend: str,
    ) -> None:
        """Apply fixed/guess connection attributes from one node's YAML config.

        Two independent groups of keys, since a node can have more than one
        outgoing connection (see ``_PORT_SUFFIXED_ATTRS``'s docstring):

        - Bare keys, targeting the node's single relevant connection (its
          outgoing connection for every type, incoming for a ``Sink``):
          ``p_out_megapascals`` -> ``p`` (MPa -> bar), ``T_out`` (K) -> ``T``
          (K -> degC), ``vapor_mass_fraction_out`` -> ``x``, ``subcooling_K``
          -> ``td_bubble`` (an outlet that many kelvin below the bubble-point
          temperature at its own pressure, so it tracks the
          pressure if that changes, e.g. in a sweep).
        - ``_out{N}``-suffixed keys (``_PORT_SUFFIXED_ATTRS``), targeting
          specifically the connection whose ``source_id == f"out{N}"``:
          ``h0_out{N}`` (kJ/kg) / ``p0_megapascals_out{N}`` (MPa -> bar) (TESPy
          guess values), ``fluid_out{N}``
          (a plain fluid-name string, e.g. ``R245fa`` -- wrapped in the same
          ``BACKEND::name`` CoolProp-backend syntax as the main loop's fluid,
          using this same node's ``backend`` param), ``vapor_mass_fraction_out{N}`` -> ``x``.

        Extend here as new topologies need attributes not yet covered --
        deliberately not adding dynamic attribute support (ttd_u/
        string-function evaluation) until a config actually needs it.
        """
        conn_attrs: dict[str, Any] = {}
        if "p_out_megapascals" in cfg:
            conn_attrs["p"] = float(cfg["p_out_megapascals"]) * 10.0  # MPa -> bar
        if "T_out" in cfg:
            conn_attrs["T"] = float(cfg["T_out"]) + K_TO_C_OFFSET  # K -> degC
        if "vapor_mass_fraction_out" in cfg:
            conn_attrs["x"] = float(cfg["vapor_mass_fraction_out"])
        if "subcooling_K" in cfg:
            subcooling = float(cfg["subcooling_K"])
            if subcooling <= 0:
                raise ConfigError(
                    f"subcooling_K must be positive (kelvin below saturation), got {subcooling}",
                )
            conn_attrs["td_bubble"] = subcooling
        if conn_attrs:
            if type_name == "Sink":
                conn = next(c for c in conns if c.target is node)
            else:
                conn = next(c for c in conns if c.source is node)
            conn.set_attr(**conn_attrs)

        for key, value in cfg.items():
            prefix = key.rstrip("0123456789")
            if prefix == key or prefix not in _PORT_SUFFIXED_ATTRS:
                continue
            port = f"out{key[len(prefix) :]}"
            conn = next(c for c in conns if c.source is node and c.source_id == port)
            tespy_attr = _PORT_SUFFIXED_ATTRS[prefix]
            if tespy_attr == "fluid":
                conn.set_attr(fluid={f"{backend}::{value}": 1})
            elif tespy_attr == "p0":
                conn.set_attr(p0=float(value) * 10.0)  # MPa -> bar (the network's pressure unit)
            else:
                conn.set_attr(**{tespy_attr: float(value)})

    def _collect_node_detail(self) -> dict[str, dict[str, float]]:
        """Snapshot every node's P/Q (if present) and every outgoing connection's T/p/m/h.

        Generic by construction: works for any node/component type without
        needing to know the topology ahead of time. ``getattr(..., None)``
        guards handle components that don't have a given TESPy attribute
        (e.g. a Valve has no ``P``/``Q``; a Sink has no outgoing connection).

        A node with more than one outgoing connection (e.g. a
        ``DropletSeparator``'s liquid/vapor split, or a dual-fluid
        ``HeatExchanger``'s primary/secondary sides) gets one entry PER
        connection, keyed ``"{name}:{source_id}"`` (``source_id`` is
        TESPy's own port label, e.g. ``"out1"``/``"out2"``) rather than one
        entry for the node as a whole -- an earlier version of this method
        picked only the first matching connection via
        ``next(c for c in conns if c.source is node)``, silently dropping
        every other port's state (found while building phase_diagrams.py:
        a DropletSeparator's vapor-branch turbine inlet was being recorded
        as its liquid-branch state instead). A single-output node keeps its
        plain, unqualified ``name`` key -- this is purely additive, so
        every existing bare-name lookup (``DoubletEconomicComponent``'s
        CAPEX dispatch, which only ever looks up single-output nodes like
        ``turbine``/``condenser``/``pump`` by name) is unaffected.
        """
        detail: dict[str, dict[str, float]] = {}
        for name, node in self._nodes.items():
            values: dict[str, float] = {}
            p_attr = getattr(node, "P", None)
            if p_attr is not None and p_attr.val is not None:
                values["P"] = p_attr.val
            q_attr = getattr(node, "Q", None)
            if q_attr is not None and q_attr.val is not None:
                values["Q"] = q_attr.val
            detail[name] = values

            outgoing = [c for c in self._conns if c.source is node]
            for conn in outgoing:
                key = name if len(outgoing) == 1 else f"{name}:{conn.source_id}"
                conn_values = detail.setdefault(key, {}) if key != name else values
                conn_values["T"] = conn.T.val + C_TO_K_OFFSET
                conn_values["p"] = conn.p.val * BAR_TO_PA
                conn_values["m"] = conn.m.val
                conn_values["h"] = conn.h.val * KJ_PER_KG_TO_J_PER_KG
                # Read directly off the connection rather than re-derived from
                # (T, p) via CoolProp -- a state sitting exactly on the
                # saturation curve (e.g. a condenser outlet) makes (T, p) an
                # ill-posed input pair for a tabular backend (can't tell which
                # quality it is), while the connection's own h is already
                # unambiguous (see phase_diagrams.py, the one consumer of this
                # field).

        return detail

    def _check_pump_or_valve_validity(self) -> None:
        """Enforce both physical directions of the pump/valve boundary in one pass.

        Two mirror-image checks, each scoped to ``role: net_electric``
        nodes of the relevant TESPy type:

        - A ``Compressor`` can never be a net SOURCE of power (``P.val`` <
          0). Even when a closed loop's natural driving force (e.g. the
          thermosiphon effect between a cold descending injection leg and
          a hot ascending production leg) already exceeds what a
          fixed-``p_out`` Compressor needs to hit its target pressure,
          TESPy's compressor equation still has a mathematically valid
          solution: a NEGATIVE ``P.val``, i.e. "this component would need
          to EXTRACT work from the flow" -- which isn't what the real
          device would do; a real pump facing surplus pressure simply
          wouldn't need to run that hard.
        - The mirror image: a ``Valve`` can never RAISE pressure (it's
          passive/dissipative, isenthalpic). If the natural driving
          pressure at that point in the network falls short of the target
          (e.g. high mass rate + small diameter + shallow depth, where
          friction losses exceed the thermosiphon margin), TESPy's valve
          equation still has a mathematically valid solution implying
          negative flow resistance -- unphysical for a real throttle.

        Both raise ``InvalidPowerStateError`` (an existing ``pymoo_api``
        ``INFEASIBLE_DESIGN_EXCEPTIONS`` member, so a plain ``Valve``/``Compressor``
        node hitting this just marks the design point infeasible during a
        search rather than crashing it); the valve case raises its subclass
        ``ValveCannotRaisePressureError``. For a ``type: PumpOrValve`` node,
        ``solve()`` catches that subclass on the Valve leg and retries with the
        Compressor leg (see ``_NetworkBundle``) -- so for that node type, the
        valve check is the fallback TRIGGER, not necessarily a final,
        user-visible failure.
        """
        for node in self._net_electric_nodes:
            if type(node).__name__ == "Compressor" and node.P.val < -_PUMP_POWER_TOLERANCE_W:
                raise InvalidPowerStateError(
                    f"{node.label} reports P={node.P.val:.1f} W (negative) -- a passive pump/"
                    "compressor can never be a net source of power; the real device at this "
                    "operating point would be a dissipative throttle (or simply not need to run "
                    "this hard), not something that extracts work from the flow. Consider "
                    f"changing {node.label}'s type to 'Valve' in the YAML.",
                )

        # Valve nodes are excluded from self._net_electric_nodes (they have
        # no `P` to sum -- see init()'s role-tagging loop), so this second
        # check walks every node directly rather than reusing that list.
        # Scoped to role: net_electric Valves specifically, not every
        # Valve in the plant -- an incidental throttle elsewhere (e.g. a
        # Single-Flash plant's pre-separator valve, explicitly p_out-fixed
        # by design) is expected to drop pressure and isn't a circulation
        # boundary condition someone might need to flip to a Compressor.
        node_cfgs = self.power_plant.get("nodes", {})
        for name, node in self._nodes.items():
            if type(node).__name__ != "Valve":
                continue
            if node_cfgs.get(name, {}).get("role") != ComponentRole.NET_ELECTRIC:
                continue
            inlet_conn = next(c for c in self._conns if c.target is node)
            outlet_conn = next(c for c in self._conns if c.source is node)
            dp_bar = outlet_conn.p.val - inlet_conn.p.val
            if dp_bar > _VALVE_PRESSURE_INCREASE_TOLERANCE_BAR:
                raise ValveCannotRaisePressureError(
                    f"{node.label} would need to RAISE pressure by {dp_bar * BAR_TO_PA:.1f} "
                    "Pa to hit this design's target -- a passive valve can only ever drop "
                    "pressure; the natural driving force here (e.g. thermosiphon) falls "
                    f"short and a real pump is needed. Consider changing {node.label}'s "
                    "type to 'Compressor' in the YAML.",
                )

    def _check_passive_pressure(self) -> None:
        """Raise if any passive component's outlet pressure is above its inlet's.

        TESPy accepts a fixed absolute outlet pressure (``p_out_megapascals``)
        on a heat exchanger even when the fluid actually arrives below it,
        and solves the network as if the heat exchanger compressed the fluid
        for free. The inlet pressure is only known at run time (it comes
        from the wells), so this can't be caught when the config is loaded.

        Raises:
            PassivePressureRiseError: naming the component, its ports, and
                both pressures.
        """
        for name, node in self._nodes.items():
            kind = type(node).__name__
            if kind not in _PASSIVE_TYPES:
                continue
            inlets = [c for c in self._conns if c.target is node]
            outlets = [c for c in self._conns if c.source is node]
            pairs = (
                [(i, o) for i in inlets for o in outlets if i.target_id[-1] == o.source_id[-1]]
                if kind == "HeatExchanger"
                else [(i, o) for i in inlets for o in outlets]
            )
            for inlet, outlet in pairs:
                rise_bar = outlet.p.val - inlet.p.val
                if rise_bar > _PASSIVE_PRESSURE_RISE_TOLERANCE_BAR:
                    raise PassivePressureRiseError(
                        f"{name} ({kind}) raises pressure from {inlet.p.val:.2f} bar at "
                        f"{inlet.target_id} to {outlet.p.val:.2f} bar at {outlet.source_id}, but it "
                        "does no work, so pressure can only fall across it. This usually means a "
                        "fixed p_out_megapascals is above the pressure that actually reaches the "
                        f"component; lower it or replace it with a pressure_ratio, and let a pump "
                        "(or PumpOrValve) take the pressure change.",
                    )

    def _check_cooling_limit(self) -> None:
        """Raise if a component rejecting heat leaves its fluid colder than the site can cool it.

        Every ``SimpleHeatExchanger`` that gives heat up (``Q < 0``: a
        condenser, cooler, or district-heating exchanger) needs a heat sink at
        least ``approach_temperature`` colder than its outlet, and the coldest
        sink available is the environment at ``common.surface_temperature``.
        TESPy accepts an outlet below ``surface_temperature +
        approach_temperature`` as if free refrigeration were available.

        Raises:
            CoolingLimitError: naming the component, its outlet temperature,
                and the limit.
        """
        limit_k = self.common.surface_temperature + self.approach_temperature
        for name, node in self._nodes.items():
            if type(node).__name__ != "SimpleHeatExchanger" or node.Q.val >= 0:
                continue
            outlet = next(c for c in self._conns if c.source is node)
            t_out_k = outlet.T.val + C_TO_K_OFFSET
            if t_out_k < limit_k - _COOLING_LIMIT_TOLERANCE_K:
                raise CoolingLimitError(
                    f"{name} cools its fluid to {t_out_k:.2f} K ({t_out_k + K_TO_C_OFFSET:.2f} degC), below "
                    f"the site's cooling limit of {limit_k:.2f} K (surface_temperature "
                    f"{self.common.surface_temperature:.2f} K + approach_temperature "
                    f"{self.approach_temperature:.2f} K). Raise its outlet pressure (for a condenser) or "
                    "outlet temperature so it can reject heat to the environment.",
                )

    # ------------------------------------------------------------------
    # record / solve
    # ------------------------------------------------------------------

    def _solve_active_bundle(
        self,
        mdot: float,
        h_in: float,
        P_tespy_in: float,
    ) -> tuple[float, float, float, float, float]:
        """Solve whichever bundle ``_activate_bundle`` last pointed at, or raise.

        Returns ``(h_out, T_out, P_out, net_power_W, net_thermal_W)`` on success.
        Raises ``TESPyCoolPropError`` (solver/CoolProp failure) or
        ``InvalidPowerStateError`` (a physically invalid result, e.g. a
        Valve that would need to raise pressure) on failure -- ``solve()``
        catches both to trigger its valve -> compressor fallback when
        ``self._dual_mode`` is True; this method itself has no fallback
        logic, it either succeeds outright or raises. A ``network.solve()``
        call can return without converging; that raises
        ``TESPyConvergenceError`` rather than passing the unconverged outlet
        conditions on.
        """
        self._inlet_conn.set_attr(
            # "BACKEND::fluid" is TESPy's own syntax for selecting a CoolProp
            # backend (Connection._fluid_specification) -- common.coolprop_backend
            # keeps this in sync with FluidState's own CoolProp backend choice.
            fluid={f"{self.common.coolprop_backend}::{self.common.fluid_name}": 1},
            m=mdot,
            h=h_in * J_PER_KG_TO_KJ_PER_KG,
            p=P_tespy_in * PA_TO_BAR,
        )
        self._outlet_conn.set_attr(p=self.injection_pressure * PA_TO_BAR)

        # TESPy calls CoolProp internally during its network solve; a CoolProp
        # flash failure (e.g. a design near the fluid's stability limits, where
        # CoolProp's internal solver can't find a solution) surfaces here as a
        # bare ValueError. Wrapping it here, rather than adding a bare
        # ValueError to pymoo_api.INFEASIBLE_DESIGN_EXCEPTIONS, keeps the CV net scoped to
        # this ONE call site instead of the entire simulation --
        # INFEASIBLE_DESIGN_EXCEPTIONS already catches CoolPropError, and TESPyCoolPropError
        # subclasses it, so no change is needed there once this is wrapped.
        try:
            self._network.solve("design")
        except ValueError as exc:
            raise TESPyCoolPropError(f"TESPy network solve failed: {exc}") from exc

        if not self._network.converged:
            raise TESPyConvergenceError(
                f"TESPy network did not converge ({self._network.problem.iter} iterations, residual "
                f"{self._network.problem.residual_history[-1]:.3g}); its outlet conditions can't be trusted.",
            )

        h_out = self._outlet_conn.h.val * KJ_PER_KG_TO_J_PER_KG
        T_out = self._outlet_conn.T.val + C_TO_K_OFFSET
        P_out = self._outlet_conn.p.val * BAR_TO_PA

        # ---- Net power / thermal (see module docstring for sign convention) ----
        net_power_W = sum(-node.P.val for node in self._net_electric_nodes)
        net_thermal_W = sum(-node.Q.val for node in self._net_thermal_nodes)
        # A negative net_power_W is checked in record(), on the converged
        # timestep only (see its docstring).
        self._check_pump_or_valve_validity()
        self._check_passive_pressure()
        self._check_cooling_limit()

        return h_out, T_out, P_out, net_power_W, net_thermal_W

    def solve(self, inlet: Stream) -> Stream:
        """Solve the TESPy network and extract outlet conditions + net power/thermal."""
        s = self.state

        s.h_inlet.update(inlet.h.get_fresh())
        s.P_inlet.update(inlet.P.get_fresh())
        s.mass_rate.update(inlet.mass_rate.get_fresh())

        h_in = s.h_inlet.get_fresh()
        P_in = s.P_inlet.get_fresh()
        mdot = s.mass_rate.get_fresh()
        inlet_state = FluidState.with_HP(self.common.fluid_name, h_in, P_in, self.common.coolprop_backend)
        s.T_inlet.update(inlet_state.T)

        # ---- Surface pipe friction drop (wellhead -> plant) ----
        # Adiabatic friction drops pressure at constant enthalpy, so TESPy's
        # inlet gets the arriving h unchanged at the reduced pressure.
        rho_in = inlet_state.rho
        mu_in = inlet_state.mu
        u_in = mean_velocity(mdot, rho_in, self.pipe_diameter)
        Re_in = reynolds_number(mdot, self.pipe_diameter, mu_in)
        ff_in = friction_factor_haaland(Re_in, self.pipe_diameter, self.pipe_roughness)
        dp_pipe = pressure_drop_friction(ff_in, self.well_spacing, self.pipe_diameter, rho_in, u_in)
        P_tespy_in = P_in - dp_pipe
        s.dP_pipe.update(dp_pipe)
        s.P_tespy_inlet.update(P_tespy_in)

        # ---- Solve, with valve -> compressor fallback for a PumpOrValve config ----
        if self._dual_mode:
            self._activate_bundle(self._valve_bundle)
            try:
                h_out, T_out, P_out, net_power_W, net_thermal_W = self._solve_active_bundle(
                    mdot,
                    h_in,
                    P_tespy_in,
                )
            except (
                PassivePressureRiseError,
                CoolingLimitError,
            ):
                # Neither depends on circulation_control resolving to a
                # valve: an upstream passive node raising pressure, or a
                # cooler below the site's cooling limit, is identical in both
                # bundles. Retrying can't fix either, and the compressor leg
                # would fail with a misleading negative-pump-power error
                # instead of the real cause.
                raise
            except (TESPyConvergenceError, TESPyCoolPropError, ValveCannotRaisePressureError):
                # The valve leg needs an unphysical pressure rise, or its
                # solve doesn't converge or hits a CoolProp flash failure
                # near that unphysical state -- retry with the real pump.
                # Any other InvalidPowerStateError (e.g. a different pump in
                # the plant reporting negative power) isn't about the
                # circulation device, so it propagates as it is.
                # The two bundles' upstream nodes see identical fixed
                # inlet/outlet conditions regardless of which one
                # circulation_control resolves to, so this can't also fail
                # for the opposite reason (needing a valve): a pressure
                # deficit at the valve leg is a pressure surplus nowhere
                # near what the compressor leg would need to reject.
                self._activate_bundle(self._compressor_bundle)
                h_out, T_out, P_out, net_power_W, net_thermal_W = self._solve_active_bundle(
                    mdot,
                    h_in,
                    P_tespy_in,
                )
        else:
            h_out, T_out, P_out, net_power_W, net_thermal_W = self._solve_active_bundle(
                mdot,
                h_in,
                P_tespy_in,
            )

        s.h_outlet.update(h_out)
        s.T_outlet.update(T_out)
        s.P_outlet.update(P_out)
        s.net_power_W.update(net_power_W)
        s.net_thermal_W.update(net_thermal_W)

        # ---- Per-node diagnostic detail (see GraphSurfaceState.node_detail) ----
        # Always update() — even {} when disabled — so node_detail is fresh
        # exactly once per solve() like every other state field; leaving it
        # un-written when record_node_detail=False would make the later
        # get_fresh() read in GraphSurfaceHistory.record() raise.
        s.node_detail.update(self._collect_node_detail() if self.record_node_detail else {})

        # ---- Fluid properties for injection stream ----
        outlet_state = FluidState.with_HP(self.common.fluid_name, h_out, P_out, self.common.coolprop_backend)
        s.rho.update(outlet_state.rho)
        s.mu.update(outlet_state.mu)

        self.outlet.h.update(h_out)
        self.outlet.P.update(P_out)
        self.outlet.mass_rate.update(mdot)
        return self.outlet
