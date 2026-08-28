"""Generic, YAML-graph-driven surface / power-plant component for tango_next.

``GraphSurface`` builds its TESPy network entirely from a
``power_plant.nodes``/``power_plant.edges`` block in the YAML, rather than
hardcoding a fixed topology in Python — the same idea proven by
``src/tango/units/native/surface/flexible_pp.py``'s ``PowerPlant`` class,
adapted to tango_next's Component/LockedState/registry pattern. One class
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

Sign convention for role aggregation (matches ``src/tango/``'s
``PowerPlant.calculate_net_power()`` without needing a per-component-type
branch): TESPy's ``P.val``/``Q.val`` are positive when power/heat flows
*into* the fluid and negative when it flows *out*. Summing ``-P.val`` over
every ``net_electric`` node therefore adds turbines (negative P → positive
contribution) and subtracts compressors/pumps (positive P → negative
contribution) uniformly; summing ``-Q.val`` over ``net_thermal`` nodes gives
positive delivered heat for a heat exchanger rejecting heat to a
district-heating loop.

Example YAML (AGS direct-heat — the topology that motivated this class):

    surface:
      type: 'graph'
      power_plant:
        nodes:
          inlet: {type: Source}
          dh_hx: {type: SimpleHeatExchanger, role: net_thermal, T_out: 323.15, pressure_ratio: 0.99}
          circ_pump: {type: Compressor, role: net_electric, efficiency: 1.0}
          outlet: {type: Sink}
        edges:
          1: {source: inlet, target: dh_hx}
          2: {source: dh_hx, target: circ_pump}
          3: {source: circ_pump, target: outlet}

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

from tango_next.components.surface.base import SurfaceComponent
from tango_next.core.constants import (
    BAR_TO_PA,
    C_TO_K_OFFSET,
    K_TO_C_OFFSET,
    PA_TO_BAR,
)
from tango_next.core.errors import ConfigError, InvalidPowerStateError
from tango_next.core.fluid_utils import (
    fluid_density,
    fluid_viscosity,
    friction_factor_haaland,
    mean_velocity,
    pressure_drop_friction,
    reynolds_number,
)
from tango_next.core.locked_state import LockedState
from tango_next.core.policies import ComponentRole
from tango_next.core.state_methods import StateMethods
from tango_next.core.stream import Stream

if TYPE_CHECKING:
    from tespy.connections import Connection

# node config "type" string -> TESPy class. Extend as new topologies need
# component types not yet listed here — keep in sync with
# src/tango/units/native/surface/flexible_pp.py's _create_component() mapping.
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


def _ls() -> LockedState[float]:
    ls: LockedState[float] = LockedState(float("nan"))
    ls.mark_stale()
    return ls


def _ls_dict() -> LockedState[dict[str, dict[str, float]]]:
    ls: LockedState[dict[str, dict[str, float]]] = LockedState({})
    ls.mark_stale()
    return ls


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

    T_inlet: LockedState[float] = field(default_factory=_ls)
    P_inlet: LockedState[float] = field(default_factory=_ls)
    mass_rate: LockedState[float] = field(default_factory=_ls)

    dP_pipe: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Friction pressure drop across the surface pipe (Pa)."""
    P_tespy_inlet: LockedState[float] = field(default_factory=_ls)
    """Pressure passed to TESPy inlet = P_inlet - dP_pipe (Pa)."""

    net_power_W: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Sum of -P.val (W) over role=net_electric nodes. 0 if none tagged."""
    net_thermal_W: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Sum of -Q.val (W) over role=net_thermal nodes. 0 if none tagged."""

    T_outlet: LockedState[float] = field(default_factory=_ls)
    P_outlet: LockedState[float] = field(default_factory=_ls)
    rho: LockedState[float] = field(default_factory=_ls)
    mu: LockedState[float] = field(default_factory=_ls)

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

    T_inlet: list[float] = field(default_factory=list)
    T_outlet: list[float] = field(default_factory=list)
    P_inlet: list[float] = field(default_factory=list)
    P_outlet: list[float] = field(default_factory=list)
    mass_rate: list[float] = field(default_factory=list)
    dP_pipe: list[float] = field(default_factory=list)  # noqa: N815
    P_tespy_inlet: list[float] = field(default_factory=list)
    rho: list[float] = field(default_factory=list)
    mu: list[float] = field(default_factory=list)
    net_power_W: list[float] = field(default_factory=list)  # noqa: N815
    net_thermal_W: list[float] = field(default_factory=list)  # noqa: N815

    node_history: dict[str, dict[str, list[float]]] = field(default_factory=dict)
    """``node_history[node_name][quantity]`` -> time series. Populated
    lazily from ``state.node_detail``; stays empty if
    ``record_node_detail=False``. Keys appear the first timestep a node
    reports that quantity; every recorded node/quantity pair grows one
    entry per ``record()`` call so all lists stay the same length."""

    def record(self, state: GraphSurfaceState) -> None:
        """Append a snapshot of ``state`` as one timestep entry."""
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
    history: GraphSurfaceHistory = Field(default_factory=GraphSurfaceHistory)

    # ------------------------------------------------------------------
    # Lifecycle: build TESPy network
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Build the TESPy network from ``power_plant.nodes``/``edges``."""
        import tespy.components as tespy_components  # noqa: PLC0415
        from tespy.components import Sink, Source  # noqa: PLC0415
        from tespy.connections import Connection  # noqa: PLC0415
        from tespy.networks import Network  # noqa: PLC0415

        # TESPy manages its own logger ("TESPyLogger") independent of the
        # standard logging config (see ``tango_next_cli.py``'s
        # ``_configure_logging``, which syncs it for CLI runs only). Any
        # caller building a GraphSurface directly via the Workflow API
        # (e.g. applications/tango_next/*/sweep.py, which never goes
        # through the CLI) would otherwise get TESPy's intermediate
        # solver-iteration bound-violation warnings ("Invalid value for
        # pr/zeta...") printed at WARNING level, even though these are
        # normal, expected noise during convergence and not failures —
        # matches old tango's precedent (src/tango/utils.py's set_logger)
        # of silencing this by default. Set here, not just in the CLI, so
        # every caller of GraphSurface gets quiet-by-default TESPy output
        # rather than only the CLI path.
        logging.getLogger("TESPyLogger").setLevel(logging.ERROR)

        pp = self.power_plant
        node_cfgs: dict[str, dict[str, Any]] = pp.get("nodes", {})
        edge_cfgs: dict[str, dict[str, Any]] = pp.get("edges", {})

        self._validate_pressure_monotonicity(node_cfgs, edge_cfgs)

        nodes: dict[str, Any] = {}
        for name, cfg in node_cfgs.items():
            type_name = cfg.get("type")
            if type_name not in _COMPONENT_TYPES:
                raise ValueError(
                    f"power_plant.nodes.{name}: unknown TESPy component type {type_name!r} "
                    f"(known: {sorted(_COMPONENT_TYPES)})",
                )
            tespy_cls = getattr(tespy_components, _COMPONENT_TYPES[type_name])
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

        net = Network(p_unit="bar", T_unit="C", h_unit="kJ / kg", iterinfo=False)
        net.add_conns(*conns)

        # ---- Per-node fixed attributes (efficiency, T_out, p_out, ...) ----
        for name, cfg in node_cfgs.items():
            self._apply_node_config(nodes[name], conns, cfg)

        # ---- Role-tagged nodes, for net power/thermal aggregation ----
        net_electric = []
        net_thermal = []
        for name, cfg in node_cfgs.items():
            role = cfg.get("role")
            if role == ComponentRole.NET_ELECTRIC:
                net_electric.append(nodes[name])
            elif role == ComponentRole.NET_THERMAL:
                net_thermal.append(nodes[name])
            elif role is not None:
                raise ValueError(
                    f"power_plant.nodes.{name}: unknown role {role!r} "
                    f"(expected one of {[r.value for r in ComponentRole]})",
                )

        self._network = net
        self._conns = conns
        self._nodes = nodes
        self._net_electric_nodes = net_electric
        self._net_thermal_nodes = net_thermal
        self._inlet_conn = next(c for c in conns if c.source.label == "inlet")
        self._outlet_conn = next(c for c in conns if c.target.label == "outlet")

    @staticmethod
    def _validate_pressure_monotonicity(
        node_cfgs: dict[str, dict[str, Any]],
        edge_cfgs: dict[str, dict[str, Any]],
    ) -> None:
        """Check that fixed ``p_out_megapascals`` values decrease monotonically downstream.

        Ported from ``src/tango/``'s ``flexible_pp.py::validate_pressure_monotonicity``
        — same algorithm (walk upstream from every node with a fixed p_out,
        stopping at pressure-increasing ``Compressor`` nodes, flag any
        downstream p_out that exceeds an upstream one), adapted to
        ``power_plant.nodes``/``edges`` and the ``p_out_megapascals`` key.

        Known gap, not covered by this check (see docs/tango_next_tasks.md):
        nodes whose pressure is solved via ``Merge``'s pressure-equality
        constraint rather than an explicit ``p_out_megapascals`` (e.g.
        ``pump``/``pump2`` in the Single-Flash examples), and components with
        no pressure spec at all (e.g. AGS_direct_heat.yml's ``dh_hx``, whose
        pressure is implicitly whatever gap exists between two unrelated
        boundary conditions) — neither is caught by this walk since it only
        traces nodes that declare ``p_out_megapascals`` explicitly.
        """
        p_out_values: dict[str, float] = {
            name: float(cfg["p_out_megapascals"])
            for name, cfg in node_cfgs.items()
            if "p_out_megapascals" in cfg
        }

        pressure_increasing_types = {"Compressor"}

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
    def _apply_node_config(node: Any, conns: list[Connection], cfg: dict[str, Any]) -> None:
        """Apply fixed component/connection attributes from one node's YAML config.

        Component-level: ``efficiency`` -> ``eta_s`` (Turbine/Compressor);
        ``pressure_ratio`` -> ``pr`` (any component TESPy gives a ``pr``
        parameter, e.g. ``SimpleHeatExchanger``/``HeatExchanger`` — a
        RATIO, not an absolute value, so it scales with whatever pressure
        actually arrives at this node rather than fixing one; added for
        ``AGS_direct_heat.yml``'s ``dh_hx``, which needs its own
        pressure-drop spec once it's no longer the last node before the
        network's outlet Sink — see that YAML's ``circ_pump`` comment for
        why). Connection-level, set on the node's outgoing connection for
        Source/Valve, incoming connection for Sink: ``T``/``p``/``m``/
        ``fluid``/``vapor_mass_fraction_out`` -> ``x``,
        ``p_out_megapascals`` -> ``p`` (converted MPa -> bar), ``T_out``
        (K) -> ``T`` (converted K -> C). Extend here as new topologies need
        attributes not yet covered — deliberately not porting src/tango/'s
        full dynamic attribute list (ttd_u/ttd_l/string-function
        evaluation) until an AGS config actually needs it.
        """
        type_name = type(node).__name__
        component_attrs: dict[str, Any] = {}
        if "efficiency" in cfg:
            component_attrs["eta_s"] = float(cfg["efficiency"])
        if "pressure_ratio" in cfg:
            component_attrs["pr"] = float(cfg["pressure_ratio"])
        if component_attrs:
            node.set_attr(**component_attrs)

        conn_attrs: dict[str, Any] = {}
        if "p_out_megapascals" in cfg:
            conn_attrs["p"] = float(cfg["p_out_megapascals"]) * 10.0  # MPa -> bar
        if "T_out" in cfg:
            conn_attrs["T"] = float(cfg["T_out"]) + K_TO_C_OFFSET  # K -> degC
        if "vapor_mass_fraction_out" in cfg:
            conn_attrs["x"] = float(cfg["vapor_mass_fraction_out"])
        if not conn_attrs:
            return

        if type_name == "Sink":
            conn = next(c for c in conns if c.target is node)
        else:
            conn = next(c for c in conns if c.source is node)
        conn.set_attr(**conn_attrs)

    def _collect_node_detail(self) -> dict[str, dict[str, float]]:
        """Snapshot every node's P/Q (if present) and outgoing-connection T/p/m.

        Generic by construction: works for any node/component type without
        needing to know the topology ahead of time. ``getattr(..., None)``
        guards handle components that don't have a given TESPy attribute
        (e.g. a Valve has no ``P``/``Q``; a Sink has no outgoing connection).
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

            outgoing = next((c for c in self._conns if c.source is node), None)
            if outgoing is not None:
                values["T"] = outgoing.T.val + C_TO_K_OFFSET
                values["p"] = outgoing.p.val * BAR_TO_PA
                values["m"] = outgoing.m.val

            detail[name] = values
        return detail

    # ------------------------------------------------------------------
    # BC variable accessor — SystemBCIteration calls this each iteration
    # ------------------------------------------------------------------

    def set_injection_pressure(self, P: float) -> None:
        """Update the injection pressure BC variable (Pa)."""
        self.injection_pressure = P

    def get_injection_pressure(self) -> float:
        """Return the current injection pressure BC variable (Pa)."""
        return self.injection_pressure

    # ------------------------------------------------------------------
    # record / solve
    # ------------------------------------------------------------------

    def solve(self, inlet: Stream) -> None:
        """Solve the TESPy network and extract outlet conditions + net power/thermal."""
        s = self.state

        s.T_inlet.update(inlet.T.get_fresh())
        s.P_inlet.update(inlet.P.get_fresh())
        s.mass_rate.update(inlet.mass_rate.get_fresh())

        T_in = s.T_inlet.get_fresh()
        P_in = s.P_inlet.get_fresh()
        mdot = s.mass_rate.get_fresh()

        # ---- Surface pipe friction drop (wellhead -> plant) ----
        rho_in = fluid_density(self.common.fluid_name, T_in, P_in)
        mu_in = fluid_viscosity(self.common.fluid_name, T_in, P_in)
        u_in = mean_velocity(mdot, rho_in, self.pipe_diameter)
        Re_in = reynolds_number(mdot, self.pipe_diameter, mu_in)
        ff_in = friction_factor_haaland(Re_in, self.pipe_diameter, self.pipe_roughness)
        dp_pipe = pressure_drop_friction(ff_in, self.well_spacing, self.pipe_diameter, rho_in, u_in)
        P_tespy_in = P_in - dp_pipe
        s.dP_pipe.update(dp_pipe)
        s.P_tespy_inlet.update(P_tespy_in)

        # ---- Inlet connection ----
        self._inlet_conn.set_attr(
            fluid={self.common.fluid_name: 1},
            m=mdot,
            T=T_in + K_TO_C_OFFSET,
            p=P_tespy_in * PA_TO_BAR,
        )

        # ---- Outlet / injection pressure BC ----
        self._outlet_conn.set_attr(p=self.injection_pressure * PA_TO_BAR)

        # ---- Solve ----
        self._network.solve("design")

        # ---- Extract outlet conditions ----
        T_out = self._outlet_conn.T.val + C_TO_K_OFFSET
        P_out = self._outlet_conn.p.val * BAR_TO_PA
        s.T_outlet.update(T_out)
        s.P_outlet.update(P_out)

        # ---- Net power / thermal (see module docstring for sign convention) ----
        net_power_W = sum(-node.P.val for node in self._net_electric_nodes)
        net_thermal_W = sum(-node.Q.val for node in self._net_thermal_nodes)
        # Only a genuine generator (Turbine) creates an expectation that
        # net_power_W should be positive -- a plant with no generator at
        # all (e.g. AGS_direct_heat.yml's circ_pump-only setup: a pure
        # electric consumer, no by-product electricity) has NO way to ever
        # be net-positive, and that's the correct, permanent state, not a
        # feasibility-boundary artifact. See InvalidPowerStateError's own
        # docstring for the actual bug this guards against (a negative
        # value silently corrupting DoubletEconomicComponent's averaged
        # LCOE calc) -- that risk is specific to a topology that EXPECTS
        # net generation, confirmed unaffected here: main_product=HEAT's
        # LCOE formula already treats net_power_W as a by-product term
        # (_compute_lcoe) and was hardened for a negative value there.
        has_generator = any(type(node).__name__ == "Turbine" for node in self._net_electric_nodes)
        if has_generator and net_power_W < 0:
            raise InvalidPowerStateError(
                f"surface plant net_power_W={net_power_W:.1f} W is negative -- the surface plant "
                "is a net consumer, not producer, of electricity this timestep (turbine output no "
                "longer covers its own surface pump parasitic load).",
            )
        s.net_power_W.update(net_power_W)
        s.net_thermal_W.update(net_thermal_W)

        # ---- Per-node diagnostic detail (see GraphSurfaceState.node_detail) ----
        # Always update() — even {} when disabled — so node_detail is fresh
        # exactly once per solve() like every other state field; leaving it
        # un-written when record_node_detail=False would make the later
        # get_fresh() read in GraphSurfaceHistory.record() raise.
        s.node_detail.update(self._collect_node_detail() if self.record_node_detail else {})

        # ---- Fluid properties for injection stream ----
        rho_out = fluid_density(self.common.fluid_name, T_out, P_out)
        mu_out = fluid_viscosity(self.common.fluid_name, T_out, P_out)
        s.rho.update(rho_out)
        s.mu.update(mu_out)

        self.outlet.T.update(T_out)
        self.outlet.P.update(P_out)
        self.outlet.mass_rate.update(mdot)
