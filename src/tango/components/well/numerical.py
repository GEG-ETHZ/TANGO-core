"""Discretized (numerically-integrated) wellbore components for tango.

``NumericalWell`` marches the wellbore state node-by-node: the wellbore is split
into ``num_cells`` axial CELLS, bounded by ``num_cells + 1`` axial NODES
(node 0 = inlet, node ``num_cells`` = outlet), and pressure + enthalpy are
integrated node-by-node with real CoolProp fluid-property lookups at each
step. Cells and nodes are NOT the same count, and mixing them up is an easy
mistake to make in this file: geometry/material fields that describe one
CELL (``cell_length``, ``T_r`` — see ``_compute_derived``'s docstring) have
``num_cells`` entries; marched per-position quantities (``P``, ``h``,
``T_f``, ``rho``, ``mu``, ``u`` in ``_march``, and the ``*_cells`` state/
history fields below despite their name) have ``num_cells + 1`` entries.

Governing equations (per cell):

- Pressure:  P[i] = P[i-1] - upward_component·ρ·g·dz - ΔP_friction   (Darcy-Weisbach)
- Enthalpy:  h[i] = h[i-1] - upward_component·g·dz - Q_loss / ṁ       (Zhang 2011 heat-loss)

A single class covers injection, production, and (future) deviated wells,
distinguished only by ``angle_from_vert_deg``: 0° = straight down
(injection), 180° = straight up (production), values in between describe a
deviated well, 90° a horizontal one. ``upward_component = -cos(radians(angle))``
(the vertical component of the unit flow direction, positive upward) so it
matches the sign convention above exactly at the two endpoints
(``upward_component = -1`` for straight-down injection, ``+1`` for straight-up
production) while interpolating smoothly in between — a horizontal well
(90°) correctly gets zero elevation-dependent pressure/enthalpy change.
Friction and heat-loss terms use the full ``cell_length`` (flow-path
distance) unscaled by angle, since those depend on distance traveled, not
vertical rise. ``NumericalInjectionWell``/``NumericalProductionWell`` below
are thin subclasses that just set the ``angle_from_vert_deg`` default so
existing YAML configs need no changes.

The rock temperature profile (``T_r``, built in ``_compute_derived``) is
projected onto true vertical depth via ``cos(angle_from_vert_deg)`` before
``thermal_gradient`` (K per vertical meter) is applied — so a horizontal
section correctly sees roughly-constant rock temperature even though fluid
keeps traveling along the flow path. ``cell_length`` (friction, heat-loss
geometry) is deliberately *not* scaled this way, since those depend on
distance traveled, not vertical rise. See ``_compute_derived``'s docstring
for the full breakdown.

Default physics selections:
  FrictionModel.HAALAND, HeatTransferModel.ZHANG_2011.
See ``core/physics_models.py`` to add or select a different variant.

**Dimensionless time:** ``t_d`` advances once per committed timestep; the
injection-enthalpy loop's re-solves within a timestep restore it from the
timestep-start snapshot (``Component.snapshot_convergence_state``).

**History:** each spatially-distributed quantity is one state variable whose value
is a vector along the well axis; recorded as one entry per timestep.
See ``save_interval`` on the base ``Component`` class.

**Serialization:** cell arrays are stored as ``list[float]`` so they serialize
natively via Pydantic.  The inner solve loop uses local numpy arrays for
performance; results are converted to lists before storing in state.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
from pydantic import Field, PositiveInt, SerializerFunctionWrapHandler, model_serializer, model_validator

from tango.components.well.base import WellComponent
from tango.core.constants import YEAR_TO_SECOND
from tango.core.errors import ConfigError, InvalidPowerStateError
from tango.core.fluid_state import FluidState
from tango.core.fluid_utils import reynolds_number
from tango.core.locked_state import LockedState
from tango.core.numerics import PUMP_BOOST_MAX_ITER, PUMP_BOOST_TOL_PA, secant_solve
from tango.core.physics_models import (
    FrictionModel,
    HeatTransferModel,
    compute_friction_factor,
    compute_heat_loss,
)
from tango.core.specs import Common
from tango.core.state_methods import StateMethods
from tango.core.stream import Stream

# ---------------------------------------------------------------------------
# Shared state / history types (injection and production use same shape)
# ---------------------------------------------------------------------------


def _ls_nan() -> LockedState[float]:
    ls: LockedState[float] = LockedState(float("nan"))
    ls.mark_stale()
    return ls


def _ls_zero() -> LockedState[float]:
    ls: LockedState[float] = LockedState(0.0)
    ls.mark_stale()
    return ls


def _ls_cells() -> LockedState[list[float]]:
    ls: LockedState[list[float]] = LockedState([])
    ls.mark_stale()
    return ls


@dataclass(frozen=True)
class NumericalWellState(StateMethods):
    """Full discretized simulation state for one numerical-well solve step.

    All scalar fields are ``LockedState[float]`` and cell arrays are
    ``LockedState[list[float]]``, each writable exactly once per timestep.
    ``mark_all_stale()`` (inherited from ``StateMethods``) is called by the
    orchestrator (via ``Component.mark_all_stale()``) immediately before
    each ``solve()``.

    The ``*_cells`` fields hold ``num_cells + 1`` values — one per axial
    NODE, not one per cell (the name is inherited from ``src/tango``; see
    module docstring's cells-vs-nodes note).
    """

    h_inlet: LockedState[float] = field(default_factory=_ls_nan)
    """Specific enthalpy (J/kg) arriving on ``inlet`` -- the march's starting state."""
    T_inlet: LockedState[float] = field(default_factory=_ls_nan)
    """Temperature (K) at the inlet, derived from (``h_inlet``, ``P_inlet``)."""
    P_inlet: LockedState[float] = field(default_factory=_ls_nan)
    mass_rate: LockedState[float] = field(default_factory=_ls_nan)
    t_d: LockedState[float] = field(default_factory=_ls_zero)
    """Dimensionless time at the end of this solve step (see module docstring).
    Also read via ``get_stale()`` at the start of the NEXT ``solve()`` call to
    get the value carried over from the previous timestep — a genuine
    cross-timestep accumulator, same as ``LumpedReservoir.state.energy_extracted``,
    which is exactly why it lives in ``state``: a within-timestep re-solve
    (an injection-temperature convergence loop) restores the whole of
    ``state`` first, so this always advances from the last converged value,
    never from a discarded re-solve attempt."""
    P_cells: LockedState[list[float]] = field(default_factory=_ls_cells)
    h_cells: LockedState[list[float]] = field(default_factory=_ls_cells)
    T_cells: LockedState[list[float]] = field(default_factory=_ls_cells)
    rho_cells: LockedState[list[float]] = field(default_factory=_ls_cells)
    mu_cells: LockedState[list[float]] = field(default_factory=_ls_cells)
    u_cells: LockedState[list[float]] = field(default_factory=_ls_cells)
    h_outlet: LockedState[float] = field(default_factory=_ls_nan)
    """Specific enthalpy (J/kg) at the last node -- what ``outlet`` carries."""
    T_outlet: LockedState[float] = field(default_factory=_ls_nan)
    P_outlet: LockedState[float] = field(default_factory=_ls_nan)
    pump_power_watts: LockedState[float] = field(default_factory=_ls_zero)
    """Pump shaft power (W). Non-zero only for pump-equipped well components."""


# Back-compat aliases so existing code that references the old specific names works.
NumericalInjectionWellState = NumericalWellState
NumericalProductionWellState = NumericalWellState


@dataclass
class NumericalWellHistory:
    """Per-timestep history of spatially-distributed well state.

    Shape: ``history.T_cells[timestep]`` is the full axial temperature
    list for that timestep — one entry per timestep, each entry holding
    ``num_cells + 1`` node values (see ``NumericalWellState``'s docstring).
    One list field per ``NumericalWellState`` attribute (TANGO Commandment:
    every ``*State`` attribute must have an analog in its ``*History``
    class).
    """

    h_inlet: list[float] = field(default_factory=list)
    T_inlet: list[float] = field(default_factory=list)
    P_inlet: list[float] = field(default_factory=list)
    mass_rate: list[float] = field(default_factory=list)
    t_d: list[float] = field(default_factory=list)
    P_cells: list[list[float]] = field(default_factory=list)
    h_cells: list[list[float]] = field(default_factory=list)
    T_cells: list[list[float]] = field(default_factory=list)
    rho_cells: list[list[float]] = field(default_factory=list)
    mu_cells: list[list[float]] = field(default_factory=list)
    u_cells: list[list[float]] = field(default_factory=list)
    h_outlet: list[float] = field(default_factory=list)
    T_outlet: list[float] = field(default_factory=list)
    P_outlet: list[float] = field(default_factory=list)
    pump_power_watts: list[float] = field(default_factory=list)
    """Pump shaft power per timestep (W). Zero for non-pump components."""

    def record(self, state: NumericalWellState) -> None:
        """Append a copy of ``state`` as one timestep entry."""
        self.h_inlet.append(state.h_inlet.get_fresh())
        self.T_inlet.append(state.T_inlet.get_fresh())
        self.P_inlet.append(state.P_inlet.get_fresh())
        self.mass_rate.append(state.mass_rate.get_fresh())
        self.t_d.append(state.t_d.get_fresh())
        self.P_cells.append(list(state.P_cells.get_fresh()))
        self.h_cells.append(list(state.h_cells.get_fresh()))
        self.T_cells.append(list(state.T_cells.get_fresh()))
        self.rho_cells.append(list(state.rho_cells.get_fresh()))
        self.mu_cells.append(list(state.mu_cells.get_fresh()))
        self.u_cells.append(list(state.u_cells.get_fresh()))
        self.h_outlet.append(state.h_outlet.get_fresh())
        self.T_outlet.append(state.T_outlet.get_fresh())
        self.P_outlet.append(state.P_outlet.get_fresh())
        self.pump_power_watts.append(state.pump_power_watts.get_fresh())


NumericalInjectionWellHistory = NumericalWellHistory
NumericalProductionWellHistory = NumericalWellHistory


# ---------------------------------------------------------------------------
# NumericalWell
# ---------------------------------------------------------------------------

TARGET_CELL_LENGTH_M = 250.0
"""Axial resolution (m) that ``NumericalWell.num_cells`` is derived from when
not given explicitly, via ``ceil(well_length / TARGET_CELL_LENGTH_M / 10) * 10``.

Holding ``cell_length`` (not ``num_cells``) constant across wells of
different lengths is the right invariant: discretization error is a function
of cell_length, so a short well and a long well resolved to the SAME
cell_length carry the same accuracy, whereas giving every well the same flat
``num_cells`` under-resolves long wells and over-resolves short ones.

250 m comes from a mesh-convergence sweep (see
``applications/demo_well_mesh_convergence/``) that found
``num_cells=15`` the smallest value keeping delivered production
temperature within 0.1% relative error of a ``num_cells=100`` baseline, on a
5000 m well -- rounded up to the nearest 10 (``num_cells=20``) gives
``5000 / 20 = 250`` m/cell. Rounding to the nearest 10 (rather than using
the raw cell count) keeps ``num_cells`` values tidy across configs without
meaningfully changing accuracy, since the error margin at 15 cells already
has headroom under the 0.1% target.
"""


_DERIVED_REL_TOL = 1e-9
"""Relative tolerance for a derived value supplied in a config to count as matching (float noise only)."""

DERIVED_FIELDS: tuple[str, ...] = ("relative_roughness", "cross_sectional_area", "t_scaling_factor", "T_r")
"""``NumericalWell`` fields computed by ``init()`` from its inputs. Not
serialized; a config should leave them out (``init()`` rejects a value that
disagrees with the computed one)."""


def default_num_cells(well_length: float) -> int:
    """``num_cells`` for a well whose config gives neither ``num_cells`` nor ``cell_length``."""
    return math.ceil(math.ceil(well_length / TARGET_CELL_LENGTH_M) / 10) * 10


def _cells_for_target(well_length: float, cell_length: float) -> int:
    """Fewest cells no longer than ``cell_length`` (the tolerance absorbs ``well_length / n`` round-trips)."""
    return max(1, math.ceil(well_length / cell_length * (1.0 - _DERIVED_REL_TOL)))


class WellLengthSideEffect(enum.StrEnum):
    """Which linked quantity absorbs a ``well_length`` change -- see ``set_well_length``."""

    KEEP_CELL_LENGTH = "keep-cell-length"
    """Keep the resolution: ``num_cells`` follows the new length."""
    KEEP_NUM_CELLS = "keep-num-cells"
    """Keep the cell count: ``cell_length`` follows the new length."""


def expunge_derived_fields(well_cfg: dict[str, Any]) -> None:
    """Remove ``DERIVED_FIELDS`` from a well's config dict so ``init()`` recomputes them.

    ``Workflow.to_dict()`` doesn't write them, so this only matters for a
    config dict that was given them explicitly.
    """
    for name in DERIVED_FIELDS:
        well_cfg.pop(name, None)


def set_well_length(well_cfg: dict[str, Any], well_length: float, side_effect: WellLengthSideEffect) -> None:
    """Set ``well_length`` in a ``NumericalWell`` config dict, keeping its discretization consistent.

    ``well_length``, ``num_cells`` and ``cell_length`` are linked, so
    changing the length means one of the other two must change too;
    ``side_effect`` says which. A config that gives neither keeps giving
    neither (the default resolution applies to the new length). Also
    removes the derived fields (``expunge_derived_fields``).
    """
    old_length = float(well_cfg["well_length"])
    num_cells: int | None = well_cfg.get("num_cells")
    cell_length: float | None = well_cfg.get("cell_length")
    if num_cells is not None or cell_length is not None:
        if cell_length is None:
            assert num_cells is not None  # noqa: S101 -- narrows for mypy; guaranteed by the branch condition
            cell_length = old_length / num_cells
        elif num_cells is None:
            num_cells = _cells_for_target(old_length, cell_length)
        if side_effect is WellLengthSideEffect.KEEP_CELL_LENGTH:
            well_cfg["cell_length"] = cell_length
            well_cfg.pop("num_cells", None)
        else:
            well_cfg["num_cells"] = num_cells
            well_cfg.pop("cell_length", None)
    well_cfg["well_length"] = float(well_length)
    expunge_derived_fields(well_cfg)


class NumericalWell(WellComponent):
    """Discretized wellbore: one marching scheme for injection, production,
    and (future) deviated/horizontal wells.

    See module docstring for governing equations, the ``angle_from_vert_deg``
    convention, and the ``T_r`` deviated-well caveat.
    """

    angle_from_vert_deg: float = Field(default=0.0, frozen=True)
    """0 = straight down (injection), 180 = straight up (production), 90 =
    horizontal. Values in between describe a deviated well."""

    # ---- YAML configuration fields ----
    common: Common = Field(frozen=True)
    """Shared fluid/rock parameters — a reference to the SAME Common
    instance every other component in the Workflow holds (Pydantic does not
    copy nested model fields on construction), not an independent copy.
    Common itself is frozen, so there is exactly one place these values can
    come from and no way for this well to silently diverge from the
    reservoir or any other well. See core/specs.py."""
    dt_years: float = Field(frozen=True)
    num_cells: PositiveInt = Field(frozen=True)
    """Axial discretization cell count. ``well_length``, ``num_cells`` and
    ``cell_length`` are linked (``well_length = num_cells * cell_length``);
    a config may give ``num_cells``, ``cell_length``, both (they must agree)
    or neither (``num_cells`` then defaults to ``TARGET_CELL_LENGTH_M`` per
    cell, rounded up to the nearest 10 -- see that constant's docstring).
    Resolved by the ``_resolve_discretization`` validator below. To change
    ``well_length`` in a config dict, use ``set_well_length``, which makes
    the caller choose which of the other two absorbs the change."""
    discretization_given: tuple[str, ...] = Field(default=(), frozen=True, exclude=True)
    """Which of ``num_cells``/``cell_length`` the config itself gave (set by
    ``_resolve_discretization``). Serialization writes only those, so a
    ``to_dict()`` copy re-derives a default cell count from its own
    ``well_length`` rather than pinning the original one."""
    cell_length: float = Field(frozen=True)
    """Flow-path length per cell (m), exactly ``well_length / num_cells``.
    Given alone in a config, it is a target: ``num_cells`` becomes the
    smallest count whose cells are no longer than it, and this field is
    then set to the exact resulting length. Used for friction and heat-loss
    geometry, deliberately *not* scaled by angle, since those depend on
    distance traveled."""
    wellhead_depth: float = Field(default=0.0, frozen=True)
    """True vertical depth (m) of the well's shallow end, whichever way the
    fluid flows: the top of an injection or production well (0 for a well
    that reaches the surface; the bottom of the upper segment for the lower
    segment of a split production well), or the depth of a horizontal well.
    The rock temperature at each cell (``T_r``) is measured from here."""
    gravity_scale_factor: float = Field(default=1.0, frozen=True)
    friction_model: FrictionModel = Field(default=FrictionModel.HAALAND, frozen=True)
    heat_transfer_model: HeatTransferModel = Field(default=HeatTransferModel.ZHANG_2011, frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _resolve_discretization(cls, data: Any) -> Any:
        """Resolve ``num_cells``/``cell_length`` from whichever of them the config gives.

        Runs before field validation, so both still come out required,
        frozen fields. See ``num_cells``'s docstring for the rules.

        Raises:
            ConfigError: ``num_cells`` and ``cell_length`` are both given but
                don't multiply out to ``well_length`` (e.g. ``well_length``
                was edited in a saved config without ``set_well_length``),
                ``num_cells`` isn't a positive integer, or ``cell_length``
                isn't positive.
        """
        if not isinstance(data, dict):
            return data
        well_length = float(data["well_length"])
        num_cells, cell_length = data.get("num_cells"), data.get("cell_length")
        if num_cells is not None and (
            isinstance(num_cells, bool) or not isinstance(num_cells, int) or num_cells <= 0
        ):
            raise ConfigError(f"num_cells must be a positive integer, got {num_cells!r}")
        data["discretization_given"] = tuple(
            key
            for key, value in (("num_cells", num_cells), ("cell_length", cell_length))
            if value is not None
        )
        if num_cells is not None and cell_length is not None:
            if not math.isclose(num_cells * cell_length, well_length, rel_tol=_DERIVED_REL_TOL):
                raise ConfigError(
                    f"num_cells ({num_cells}) x cell_length ({cell_length} m) = "
                    f"{num_cells * cell_length} m, but well_length is {well_length} m. Give only one "
                    "of num_cells/cell_length, or change well_length with set_well_length().",
                )
        elif cell_length is not None:
            if cell_length <= 0:
                raise ConfigError(f"cell_length must be positive, got {cell_length}")
            num_cells = _cells_for_target(well_length, cell_length)
        elif num_cells is None:
            num_cells = default_num_cells(well_length)
        data["num_cells"] = num_cells
        data["cell_length"] = well_length / num_cells
        return data

    @model_serializer(mode="wrap")
    def _omit_derived_discretization(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Leave out whichever of ``num_cells``/``cell_length`` the config didn't give (see ``discretization_given``)."""
        data: dict[str, Any] = handler(self)
        for key in ("num_cells", "cell_length"):
            if key not in self.discretization_given:
                data.pop(key, None)
        return data

    # ---- Derived quantities (computed by init()) ----
    # Deliberately NOT frozen — init() computes relative_roughness/
    # cross_sectional_area/t_scaling_factor/T_r via direct assignment; see
    # Component's class docstring for why fields like this stay mutable.
    # Excluded from serialization: they are pure functions of the inputs and
    # recomputed by every init(), so a serialized copy could only go stale
    # when a saved config's inputs are edited. A config that supplies one
    # anyway is checked against the computed value; a mismatch raises
    # instead of being silently overwritten.
    relative_roughness: float = Field(default=0.0, exclude=True)
    cross_sectional_area: float = Field(default=0.0, exclude=True)
    t_scaling_factor: float = Field(default=0.0, exclude=True)
    T_r: list[float] = Field(default_factory=list, exclude=True)
    """Rock temperature profile along well axis (K), one value per cell."""

    # ---- Runtime state / history ----
    state: NumericalWellState = Field(default_factory=NumericalWellState)
    history: NumericalWellHistory = Field(default_factory=NumericalWellHistory)

    def init(self) -> None:
        """Pre-compute geometry constants from validated input fields.

        Raises:
            ConfigError: The config supplied a derived value (see
                ``DERIVED_FIELDS``) that disagrees with what this well's
                inputs give. Remove it (``expunge_derived_fields``) so it is
                recomputed.
        """
        self._set_derived(**dict(zip(DERIVED_FIELDS, self._compute_derived(), strict=True)))

    def _compute_derived(self) -> tuple[float, float, float, list[float]]:
        """Compute geometry-derived constants from this well's validated input fields.

        Returns:
            Tuple in ``DERIVED_FIELDS`` order. ``T_r`` is the rock temperature (K) at each cell's true vertical
            depth — ``num_cells`` entries, ONE PER CELL (not per node —
            ``_march`` uses ``T_r[i - 1]`` for marching step ``i``, i.e. the
            cell that step falls within) — computed by projecting flow-path
            position onto true vertical depth (via ``cos(angle_from_vert_deg)``)
            before applying ``thermal_gradient`` (a per-vertical-meter
            quantity), so ``T_r`` tracks actual rock temperature rather than
            distance traveled. Cells are ordered along the flow: for a well
            whose flow runs upward (``angle_from_vert_deg`` above 90°, e.g. a
            production well), the first cell is the deepest one, so depth is
            measured back from the far (bottom) end of the well rather than
            down from ``wellhead_depth``.

        """
        relative_roughness = self.pipe_roughness / self.diameter
        cross_sectional_area = 0.25 * math.pi * self.diameter**2
        t_scaling_factor = (
            4.0 * self.common.rock_k / (self.common.rock_density * self.common.rock_cp * self.diameter**2)
        )
        zspace = np.linspace(0.0, self.well_length, self.num_cells + 1)
        zspace = (zspace[1:] + zspace[:-1]) * 0.5  # cell midpoints, along the flow
        if self.angle_from_vert_deg > 90.0:
            zspace = self.well_length - zspace  # upward flow: distance from the shallow end is L - z
        vertical_depth = self.wellhead_depth + zspace * abs(math.cos(math.radians(self.angle_from_vert_deg)))
        T_r = (self.common.surface_temperature + vertical_depth * self.common.thermal_gradient).tolist()
        return relative_roughness, cross_sectional_area, t_scaling_factor, T_r

    def _march(
        self,
        h_in: float,
        P_in: float,
        mdot: float,
        t_d: float,
    ) -> tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
    ]:
        """Pure cell-by-cell march from a given starting state — no state writes.

        Takes the starting (specific enthalpy, pressure, mass rate) and
        dimensionless time explicitly, rather than reading ``solve()``'s
        ``inlet`` parameter/``self.state.t_d`` directly, so it can be called repeatedly with a
        TRIAL starting state (e.g. a candidate pump-discharge condition in
        ``NumericalProductionWellWithPump.solve()``) without mutating any
        ``LockedState`` field. ``solve()`` below is the only place that
        commits a march's result to ``state``/``outlet``.

        Returns:
            ``(P, h, T_f, rho, mu, u)`` — ``num_cells + 1`` entries each, one
            value per axial NODE (not per cell — see module docstring).
            Index 0 is the starting (inlet) state; index ``num_cells`` is
            the outlet.

        """
        n = self.num_cells
        # initialize nodes (two nodes for each cell, with each inner node being
        # shared by two adjacent cells)
        P = np.zeros(n + 1)
        h = np.zeros(n + 1)
        T_f = np.zeros(n + 1)
        rho = np.zeros(n + 1)
        mu = np.zeros(n + 1)
        u = np.zeros(n + 1)

        inlet_state = FluidState.with_HP(self.common.fluid_name, h_in, P_in, self.common.coolprop_backend)
        P[0] = inlet_state.P
        h[0] = inlet_state.H
        T_f[0] = inlet_state.T
        rho[0] = inlet_state.rho
        mu[0] = inlet_state.mu
        u[0] = mdot / self.cross_sectional_area / rho[0]

        A = self.cross_sectional_area
        g = self.gravity * self.gravity_scale_factor
        dz = self.cell_length  # flow-path length per cell (friction, heat-loss)
        # -cos(...) so this matches the upward_component convention in the
        # module docstring exactly at the endpoints (-1 straight down /
        # injection, +1 straight up / production) while interpolating through
        # 0 at 90 degrees (horizontal).
        upward_component = -math.cos(math.radians(self.angle_from_vert_deg))
        # specific potential-energy gain per cell (J/kg); constant along the
        # well, so computed once here rather than per cell
        potential_energy_per_cell = upward_component * g * dz
        T_r = np.asarray(self.T_r)

        for i in range(1, n + 1):
            Re = reynolds_number(mdot, self.diameter, mu[i - 1])
            ff = compute_friction_factor(self.friction_model, Re, self.diameter, self.pipe_roughness)
            dP_loss = 0.5 * ff * dz * rho[i - 1] * u[i - 1] ** 2 / self.diameter
            Q_loss = compute_heat_loss(
                self.heat_transfer_model,
                dL=self.cell_length,
                rock_k=self.common.rock_k,
                t_d=t_d,
                delta_T=T_f[i - 1] - T_r[i - 1],
            )
            dp_grav = potential_energy_per_cell * rho[i - 1]
            P[i] = P[i - 1] - dp_grav - dP_loss
            h[i] = h[i - 1] - potential_energy_per_cell - Q_loss / mdot

            cell_state = FluidState.with_HP(self.common.fluid_name, h[i], P[i], self.common.coolprop_backend)
            rho[i] = cell_state.rho
            mu[i] = cell_state.mu
            T_f[i] = cell_state.T
            u[i] = mdot / A / rho[i]

        return P, h, T_f, rho, mu, u

    def solve(self, inlet: Stream) -> Stream:
        """March the discretized wellbore from inlet to outlet conditions."""
        s = self.state

        s.h_inlet.update(inlet.h.get_fresh())
        s.P_inlet.update(inlet.P.get_fresh())
        s.mass_rate.update(inlet.mass_rate.get_fresh())

        del_t = self.t_scaling_factor * self.dt_years * YEAR_TO_SECOND
        t_d = s.t_d.get_stale() + del_t
        s.t_d.update(t_d)

        h_in = s.h_inlet.get_fresh()
        P_in = s.P_inlet.get_fresh()
        mdot = s.mass_rate.get_fresh()

        P, h, T_f, rho, mu, u = self._march(h_in, P_in, mdot, t_d)
        s.T_inlet.update(T_f[0])

        s.P_cells.update(P.tolist())
        s.h_cells.update(h.tolist())
        s.T_cells.update(T_f.tolist())
        s.rho_cells.update(rho.tolist())
        s.mu_cells.update(mu.tolist())
        s.u_cells.update(u.tolist())
        s.P_outlet.update(P[-1])
        s.h_outlet.update(h[-1])
        s.T_outlet.update(T_f[-1])
        s.pump_power_watts.update(0.0)

        self.outlet.h.update(h[-1])
        self.outlet.P.update(P[-1])
        self.outlet.mass_rate.update(mdot)
        return self.outlet


# ---------------------------------------------------------------------------
# NumericalInjectionWell / NumericalProductionWell
# ---------------------------------------------------------------------------


class NumericalInjectionWell(NumericalWell):
    """Discretized injection wellbore: surface → reservoir bottom.

    Thin ``NumericalWell`` subclass — only sets the ``angle_from_vert_deg``
    default (straight down). See module docstring for the shared marching
    scheme.
    """

    angle_from_vert_deg: float = 0.0


class NumericalProductionWell(NumericalWell):
    """Discretized production wellbore: reservoir bottom → surface.

    Thin ``NumericalWell`` subclass — only sets the ``angle_from_vert_deg``
    default (straight up). See module docstring for the shared marching
    scheme.

    The hot brine enters at the bottom (cell 0, reservoir pressure/temperature)
    and exits at the top (cell n-1, lower P and slightly lower T due to Zhang
    heat-loss to the cooler rock above).
    """

    angle_from_vert_deg: float = 180.0


# ---------------------------------------------------------------------------
# NumericalProductionWellWithPump
# ---------------------------------------------------------------------------


class NumericalProductionWellWithPump(NumericalProductionWell):
    """Upper production wellbore with numerical heat loss and an optional pump.

    Inherits the full Zhang 2011 marching heat-loss model from
    ``NumericalProductionWell``.  After the wellbore solve, a pump boost is
    applied to ``P_outlet`` if ``target_extraction_pressure`` exceeds the
    wellbore outlet pressure.

    Use this for the upper production well segment in a split (lower/upper)
    production wellbore configuration.
    Assumptions:
        - All of the pump's losses heat the produced fluid. The actual
          enthalpy rise is the isentropic rise divided by
          ``pump_efficiency``, and the pump's electricity draw is
          ``mass_rate`` times that same rise. This is right for losses in
          the pump and its fluid-cooled downhole motor. It is not quite right
          when ``pump_efficiency`` is an overall pump-string figure that also
          covers surface equipment (cable, transformer, frequency
          converter), whose losses heat the surroundings rather than the
          fluid: the electricity draw is still correct, but the discharge
          enthalpy is slightly overstated (about 1 kJ/kg for a 50 bar boost
          of hot brine at an overall efficiency of 0.55).
    """

    pump_efficiency: float = 1.0
    """Pump efficiency (dimensionless): the isentropic enthalpy rise divided by
    the actual one, which is also the electricity drawn per unit mass. Defaults
    to 1.0 (ideal pump). The example configs use **0.55**, the overall
    electric submersible pump (ESP) string efficiency of van 't Spijker &
    Ungemach (2016) (see ``docs/SOURCES.md#vantspijker2016``): pump 70% ×
    motor 90% × cable 97% × transformer 99% × frequency converter 94%. The
    overall figure is used, not the 70% pump-only one, because downhole pump
    power is billed as electricity drawn at the surface. See the class's
    Assumptions section for what this means for the fluid's enthalpy, and
    ``solve()``'s docstring for the pump model this scales."""
    target_extraction_pressure: float = 0.0
    """Target outlet pressure after pump boost (Pa). 0 = no active pump.
    Sourced from ``sim_config.target_extraction_pressure`` — the SAME
    single value ``SurfaceComponent`` uses, threaded in by
    ``_build_components`` (see that field's docstring in ``core/specs.py``
    for the duplicated-value bug this replaced)."""

    def solve(self, inlet: Stream) -> Stream:
        """March wellbore heat loss, then apply a pump boost if needed.

        If the natural (un-boosted) march already reaches
        ``target_extraction_pressure``, this is identical to
        ``NumericalWell.solve()``. Otherwise, the pump-discharge pressure is
        found by ITERATING (Secant method) rather than tacking a closed-form
        correction onto the already-completed natural march: this segment's
        own friction/gravity loss depends on fluid density, which in turn
        depends on the (boosted) pressure profile — a genuine fixed-point
        problem. Concretely: guess a discharge pressure at the pump, re-run
        the ENTIRE march (``_march()``) from that boosted starting state,
        compare the resulting outlet pressure to the target, and refine —
        because the density used for friction/heat-loss over the whole
        segment must reflect the boosted pressure, not the natural
        (lower-pressure) one a pump sitting anywhere below the very last
        cell would actually see.

        Pump work uses a standard isentropic-efficiency model — entropy at
        the true inlet state, isentropic enthalpy at the candidate discharge
        pressure, efficiency-derated to the actual enthalpy rise, then
        handed to the march as enthalpy directly — rather than assuming the compression
        is perfectly isothermal. The gap between an isothermal and an
        isentropic-efficiency result is driven by TEMPERATURE, not pressure
        level or the size of the pressure rise: ``dH|_S - dH|_T =
        T*alpha*V*dP``, where ``alpha`` is the fluid's thermal expansion
        coefficient. Because ``alpha`` grows as temperature rises toward
        the fluid's own critical point, the same pressure boost applied at
        a higher temperature produces a larger isothermal/isentropic
        divergence than the identical boost applied near ambient
        temperature — the effect is set by how warm the fluid runs relative
        to its own critical point, not by the absolute pressure level.
        """
        s = self.state

        s.h_inlet.update(inlet.h.get_fresh())
        s.P_inlet.update(inlet.P.get_fresh())
        s.mass_rate.update(inlet.mass_rate.get_fresh())

        del_t = self.t_scaling_factor * self.dt_years * YEAR_TO_SECOND
        t_d = s.t_d.get_stale() + del_t

        h_in = s.h_inlet.get_fresh()
        P_in = s.P_inlet.get_fresh()
        mdot = s.mass_rate.get_fresh()
        target_Pa = self.target_extraction_pressure

        before = FluidState.with_HP(self.common.fluid_name, h_in, P_in, self.common.coolprop_backend)
        s.T_inlet.update(before.T)
        P, h, T_f, rho, mu, u = self._march(h_in, P_in, mdot, t_d)

        if target_Pa <= P[-1]:
            pump_pwr = 0.0
        else:

            def _discharge_enthalpy(P_pump_out: float) -> float:
                """Isentropic-efficiency pump model: discharge pressure -> actual discharge enthalpy."""
                h_isentropic = FluidState.with_PS(
                    self.common.fluid_name,
                    P_pump_out,
                    before.S,
                    self.common.coolprop_backend,
                ).H
                return before.H + (h_isentropic - before.H) / self.pump_efficiency

            def _residual(P_pump_out: float) -> float:
                p_trial, *_ = self._march(_discharge_enthalpy(P_pump_out), P_pump_out, mdot, t_d)
                return p_trial[-1] - target_Pa

            P_pump_out = secant_solve(
                _residual,
                x0=P_in,
                x1=P_in + (target_Pa - P[-1]),
                tol=PUMP_BOOST_TOL_PA,
                max_iter=PUMP_BOOST_MAX_ITER,
                error_context=f"well component_idx={self.component_idx}: pump-boost pressure convergence",
            )
            h_actual = _discharge_enthalpy(P_pump_out)
            P, h, T_f, rho, mu, u = self._march(h_actual, P_pump_out, mdot, t_d)
            pump_pwr = mdot * (h_actual - before.H)
            if pump_pwr < 0:
                raise InvalidPowerStateError(
                    f"well component_idx={self.component_idx}: pump_power_watts={pump_pwr:.1f} W "
                    f"is negative despite boosting to P_pump_out={P_pump_out:.1f} Pa (target "
                    f"P_outlet={target_Pa:.1f} Pa) -- a passive pump cannot report negative power "
                    "draw. This happens when the isentropic enthalpy rise used for pump work goes "
                    "negative even though pressure increases (dH/dP|_S can be negative for a liquid "
                    "whose thermal expansivity term dominates).",
                )

        s.t_d.update(t_d)
        s.P_cells.update(P.tolist())
        s.h_cells.update(h.tolist())
        s.T_cells.update(T_f.tolist())
        s.rho_cells.update(rho.tolist())
        s.mu_cells.update(mu.tolist())
        s.u_cells.update(u.tolist())
        s.P_outlet.update(P[-1])
        s.h_outlet.update(h[-1])
        s.T_outlet.update(T_f[-1])
        s.pump_power_watts.update(pump_pwr)

        self.outlet.h.update(h[-1])
        self.outlet.P.update(P[-1])
        self.outlet.mass_rate.update(mdot)
        return self.outlet
