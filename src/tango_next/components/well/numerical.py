"""Discretized (numerically-integrated) wellbore components for tango_next.

``NumericalWell`` replicates ``src/tango/units/native/well/base.py``'s
``WellUnitNative.process_stream()`` marching scheme: the wellbore is split
into ``num_cells`` axial segments, and pressure + enthalpy are integrated
cell-by-cell with real CoolProp fluid-property lookups at each step.

Governing equations (per cell):

- Pressure:  P[i] = P[i-1] - f_dir·ρ·g·dz - ΔP_friction   (Darcy-Weisbach)
- Enthalpy:  h[i] = h[i-1] - f_dir·g·dz - Q_loss / ṁ       (Adams 2015 heat-loss)

A single class covers injection, production, and (future) deviated wells,
distinguished only by ``angle_from_vert_deg``: 0° = straight down
(injection), 180° = straight up (production), values in between describe a
deviated well, 90° a horizontal one. ``f_dir = -cos(radians(angle))`` so it
matches the legacy convention above exactly at the two endpoints
(``f_dir = -1`` for straight-down injection, ``+1`` for straight-up
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

Default physics selections match ``src/tango/`` exactly:
  FrictionModel.HAALAND, HeatTransferModel.ADAMS_2015.
See ``core/physics_models.py`` to add or select a different variant.

**Phase 1 simplification (flag for Phase 2):** dimensionless time (``t_d``) only
advances correctly when ``solve()`` is called exactly once per timestep — true
today because only ``InjectionPolicy.MANUAL`` is implemented. Once AUTO_* policies
add multi-pass outer loops (Phase 2), ``t_d`` must be split between a per-pass
update and a per-timestep commit — see ``src/tango/`` lines ~223-235.

**History:** each spatially-distributed quantity is one state variable whose value
is a vector along the well axis; recorded as one entry per timestep.
See ``save_interval`` on the base ``Component`` class.

**Serialization:** cell arrays are stored as ``list[float]`` so they serialize
natively via Pydantic.  The inner solve loop uses local numpy arrays for
performance; results are converted to lists before storing in state.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field

import numpy as np
from pydantic import Field

from tango_next.components.well.base import WellComponent
from tango_next.core.constants import GRAVITY, YEAR_TO_SECOND
from tango_next.core.fluid_state import FluidState
from tango_next.core.fluid_utils import reynolds_number
from tango_next.core.locked_state import LockedState
from tango_next.core.physics_models import (
    FrictionModel,
    HeatTransferModel,
    compute_friction_factor,
    compute_heat_loss,
)
from tango_next.core.specs import Common

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
class NumericalWellState:
    """Full discretized simulation state for one numerical-well solve step.

    All scalar fields are ``LockedState[float]`` and cell arrays are
    ``LockedState[list[float]]``, each writable exactly once per timestep.
    Call ``mark_all_stale()`` at the start of each ``solve()``.
    """

    T_inlet: LockedState[float] = field(default_factory=_ls_nan)
    P_inlet: LockedState[float] = field(default_factory=_ls_nan)
    mass_rate: LockedState[float] = field(default_factory=_ls_nan)
    t_d: LockedState[float] = field(default_factory=_ls_zero)
    """Dimensionless time at the end of this solve step (see module docstring)."""
    P_cells: LockedState[list[float]] = field(default_factory=_ls_cells)
    h_cells: LockedState[list[float]] = field(default_factory=_ls_cells)
    T_cells: LockedState[list[float]] = field(default_factory=_ls_cells)
    rho_cells: LockedState[list[float]] = field(default_factory=_ls_cells)
    mu_cells: LockedState[list[float]] = field(default_factory=_ls_cells)
    u_cells: LockedState[list[float]] = field(default_factory=_ls_cells)
    T_outlet: LockedState[float] = field(default_factory=_ls_nan)
    P_outlet: LockedState[float] = field(default_factory=_ls_nan)
    pump_power_watts: LockedState[float] = field(default_factory=_ls_zero)
    """Pump shaft power (W). Non-zero only for pump-equipped well components."""

    def mark_all_stale(self) -> None:
        """Mark every field stale — call at the start of each ``solve()``."""
        for f in dataclasses.fields(self):
            getattr(self, f.name).mark_stale()


# Back-compat aliases so existing code that references the old specific names works.
NumericalInjectionWellState = NumericalWellState
NumericalProductionWellState = NumericalWellState


@dataclass
class NumericalWellHistory:
    """Per-timestep history of spatially-distributed well state.

    Shape: ``history.T_cells[timestep]`` is the full axial temperature
    list for that timestep — one entry per timestep, each entry holds
    the complete spatial list.
    """

    t_d: list[float] = field(default_factory=list)
    P_cells: list[list[float]] = field(default_factory=list)
    h_cells: list[list[float]] = field(default_factory=list)
    T_cells: list[list[float]] = field(default_factory=list)
    rho_cells: list[list[float]] = field(default_factory=list)
    mu_cells: list[list[float]] = field(default_factory=list)
    u_cells: list[list[float]] = field(default_factory=list)
    T_outlet: list[float] = field(default_factory=list)
    P_outlet: list[float] = field(default_factory=list)
    pump_power_watts: list[float] = field(default_factory=list)
    """Pump shaft power per timestep (W). Zero for non-pump components."""

    def record(self, state: NumericalWellState) -> None:
        """Append a copy of ``state`` as one timestep entry."""
        self.t_d.append(state.t_d.get_fresh())
        self.P_cells.append(list(state.P_cells.get_fresh()))
        self.h_cells.append(list(state.h_cells.get_fresh()))
        self.T_cells.append(list(state.T_cells.get_fresh()))
        self.rho_cells.append(list(state.rho_cells.get_fresh()))
        self.mu_cells.append(list(state.mu_cells.get_fresh()))
        self.u_cells.append(list(state.u_cells.get_fresh()))
        self.T_outlet.append(state.T_outlet.get_fresh())
        self.P_outlet.append(state.P_outlet.get_fresh())
        self.pump_power_watts.append(state.pump_power_watts.get_fresh())


NumericalInjectionWellHistory = NumericalWellHistory
NumericalProductionWellHistory = NumericalWellHistory


# ---------------------------------------------------------------------------
# Shared derived-geometry helper
# ---------------------------------------------------------------------------


def _compute_derived(
    well_length: float,
    wellhead_depth: float,
    num_cells: int,
    diameter: float,
    pipe_roughness: float,
    rock_k: float,
    rock_density: float,
    rock_cp: float,
    surface_temperature: float,
    thermal_gradient: float,
    angle_from_vert_deg: float,
) -> tuple[float, float, float, float, list[float]]:
    """Compute geometry-derived constants shared by both well types.

    Args:
        well_length: Total wellbore flow-path length (m), wellhead to bottom
            — the distance the fluid actually travels, not a vertical depth.
        wellhead_depth: Flow-path position of the wellhead (m); 0 for a well
            modeled starting at the surface. Same axis as ``well_length``.
        num_cells: Axial discretization resolution (number of marching cells).
        diameter: Wellbore inner diameter (m).
        pipe_roughness: Absolute pipe wall roughness (m), used to form the
            Darcy-Weisbach relative roughness ratio.
        rock_k: Surrounding rock thermal conductivity (W/(m*K)).
        rock_density: Surrounding rock density (kg/m^3).
        rock_cp: Surrounding rock specific heat capacity (J/(kg*K)).
        surface_temperature: Ambient surface temperature (K) — the T0 for the
            rock temperature profile at zero vertical depth.
        thermal_gradient: Geothermal temperature gradient (K per vertical
            meter). Always per *true vertical* meter, regardless of well
            path — rock temperature depends on depth, not distance traveled.
        angle_from_vert_deg: 0 = straight down, 180 = straight up, 90 =
            horizontal; values in between describe a deviated well. Used to
            project flow-path position down to true vertical depth (via
            ``cos``) before applying ``thermal_gradient``, so ``T_r`` tracks
            actual rock temperature rather than distance traveled. ``abs()``
            is applied because depth increases away from the wellhead
            regardless of flow direction — the separate ``f_dir`` sign in
            ``solve()`` already handles the injection-vs-production gravity
            direction, so this must stay a positive magnitude.

    Returns:
        Tuple of ``(cell_length, relative_roughness, cross_sectional_area,
        t_scaling_factor, T_r)``. ``cell_length`` is flow-path length per
        cell (m) — used for friction and heat-loss geometry, deliberately
        *not* scaled by angle, since those depend on distance traveled.
        ``T_r`` is the rock temperature (K) at each cell's true vertical
        depth, one value per cell.

    """
    cell_length = well_length / num_cells
    relative_roughness = pipe_roughness / diameter
    cross_sectional_area = 0.25 * math.pi * diameter**2
    t_scaling_factor = 4.0 * rock_k / (rock_density * rock_cp * diameter**2)
    zspace = np.linspace(wellhead_depth, well_length, num_cells + 1)
    zspace = (zspace[1:] + zspace[:-1]) * 0.5
    vertical_depth = zspace * abs(math.cos(math.radians(angle_from_vert_deg)))
    T_r = (surface_temperature + vertical_depth * thermal_gradient).tolist()
    return cell_length, relative_roughness, cross_sectional_area, t_scaling_factor, T_r


# ---------------------------------------------------------------------------
# NumericalWell
# ---------------------------------------------------------------------------


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
    num_cells: int = Field(default=100, frozen=True)
    wellhead_depth: float = Field(default=0.0, frozen=True)
    gravity_scale_factor: float = Field(default=1.0, frozen=True)
    friction_model: FrictionModel = Field(default=FrictionModel.HAALAND, frozen=True)
    heat_transfer_model: HeatTransferModel = Field(default=HeatTransferModel.ADAMS_2015, frozen=True)

    # ---- Derived quantities (computed by init(), serialized for save/restore) ----
    # Deliberately NOT frozen — init() computes cell_length/relative_roughness/
    # cross_sectional_area/t_scaling_factor/T_r via direct assignment, and
    # solve() reassigns t_d_old every timestep; see Component's class
    # docstring for why fields like this stay mutable.
    cell_length: float = 0.0
    relative_roughness: float = 0.0
    cross_sectional_area: float = 0.0
    t_scaling_factor: float = 0.0
    T_r: list[float] = Field(default_factory=list)
    """Rock temperature profile along well axis (K), one value per cell."""
    t_d_old: float = 0.0
    """Dimensionless time carried over from the previous timestep."""

    # ---- Runtime state / history ----
    state: NumericalWellState = Field(default_factory=NumericalWellState)
    history: NumericalWellHistory = Field(default_factory=NumericalWellHistory)

    def init(self) -> None:
        """Pre-compute geometry constants from validated input fields."""
        (
            self.cell_length,
            self.relative_roughness,
            self.cross_sectional_area,
            self.t_scaling_factor,
            self.T_r,
        ) = _compute_derived(
            self.well_length,
            self.wellhead_depth,
            self.num_cells,
            self.diameter,
            self.pipe_roughness,
            self.common.rock_k,
            self.common.rock_density,
            self.common.rock_cp,
            self.common.surface_temperature,
            self.common.thermal_gradient,
            self.angle_from_vert_deg,
        )
        self.t_d_old = 0.0

    def record(self, timestep: int) -> None:
        """Append state to history if save_interval permits."""
        if self.save_interval is None:
            return
        if timestep % self.save_interval == 0:
            self.history.record(self.state)

    def solve(self) -> None:
        """March the discretized wellbore from inlet to outlet conditions."""
        s = self.state
        s.mark_all_stale()
        n = self.num_cells

        s.T_inlet.update(self.inlet.T)
        s.P_inlet.update(self.inlet.P)
        s.mass_rate.update(self.inlet.mass_rate)

        del_t = self.t_scaling_factor * self.dt_years * YEAR_TO_SECOND
        t_d = self.t_d_old + del_t
        s.t_d.update(t_d)
        self.t_d_old = t_d

        T_in = s.T_inlet.get_fresh()
        P_in = s.P_inlet.get_fresh()
        mdot = s.mass_rate.get_fresh()

        P = np.zeros(n)
        h = np.zeros(n)
        T_f = np.zeros(n)
        rho = np.zeros(n)
        mu = np.zeros(n)
        u = np.zeros(n)

        inlet_state = FluidState.with_PT(self.common.fluid_name, P_in, T_in)
        P[0] = inlet_state.P
        h[0] = inlet_state.H
        T_f[0] = inlet_state.T
        rho[0] = inlet_state.rho
        mu[0] = inlet_state.mu
        u[0] = mdot / self.cross_sectional_area / rho[0]

        A = self.cross_sectional_area
        g = GRAVITY * self.gravity_scale_factor
        dz = self.cell_length  # flow-path length per cell (friction, heat-loss)
        # -cos(...) so this matches the legacy f_dir convention exactly at the
        # endpoints (-1 straight down / injection, +1 straight up / production)
        # while interpolating through 0 at 90 degrees (horizontal).
        f_dir = -math.cos(math.radians(self.angle_from_vert_deg))
        T_r = np.asarray(self.T_r)

        for i in range(1, n):
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
            dp_grav = f_dir * rho[i - 1] * g * dz
            P[i] = P[i - 1] - dp_grav - dP_loss
            h[i] = h[i - 1] - f_dir * g * dz - Q_loss / mdot

            cell_state = FluidState.with_HP(self.common.fluid_name, h[i], P[i])
            rho[i] = cell_state.rho
            mu[i] = cell_state.mu
            T_f[i] = cell_state.T
            u[i] = mdot / A / rho[i]

        s.P_cells.update(P.tolist())
        s.h_cells.update(h.tolist())
        s.T_cells.update(T_f.tolist())
        s.rho_cells.update(rho.tolist())
        s.mu_cells.update(mu.tolist())
        s.u_cells.update(u.tolist())
        s.P_outlet.update(P[-1])
        s.T_outlet.update(T_f[-1])
        s.pump_power_watts.update(0.0)

        self.outlet.T = T_f[-1]
        self.outlet.P = P[-1]
        self.outlet.mass_rate = mdot
        self.outlet.rho = rho[-1]
        self.outlet.mu = mu[-1]
        self.outlet.fluid_name = self.common.fluid_name


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
    scheme; matches ``src/tango/units/native/well/production_well.py``'s
    ``ProductionWellUnitNative``.

    The hot brine enters at the bottom (cell 0, reservoir pressure/temperature)
    and exits at the top (cell n-1, lower P and slightly lower T due to Adams
    heat-loss to the cooler rock above).
    """

    angle_from_vert_deg: float = 180.0


# ---------------------------------------------------------------------------
# NumericalProductionWellPump
# ---------------------------------------------------------------------------


class NumericalProductionWellPump(NumericalProductionWell):
    """Upper production wellbore with numerical heat loss and an optional pump.

    Inherits the full Adams 2015 marching heat-loss model from
    ``NumericalProductionWell``.  After the wellbore solve, a pump boost is
    applied to ``P_outlet`` if ``pump_target_pressure_megapascals`` exceeds the
    wellbore outlet pressure.

    Use this for the upper production well segment in a split (lower/upper)
    production wellbore configuration.
    """

    pump_efficiency: float = 0.75
    """Pump isentropic efficiency (dimensionless)."""
    pump_target_pressure_megapascals: float = 0.0
    """Target outlet pressure after pump boost (MPa). 0 = no active pump."""

    def solve(self) -> None:
        """March wellbore heat loss, then apply pump pressure boost."""
        super().solve()

        s = self.state
        # super().solve() already marked all fields stale then updated them;
        # pump_power_watts was set to 0.0. Override P_outlet and pump_power_watts
        # if a pump boost is needed — use update_unchecked equivalent: mark stale first.
        target_Pa = self.pump_target_pressure_megapascals * 1e6
        P_wellbore = s.P_outlet.get_fresh()
        if target_Pa > P_wellbore:
            pump_delta_p = target_Pa - P_wellbore
            rho_out = self.outlet.rho  # set by super().solve() via CoolProp
            pump_pwr = (
                s.mass_rate.get_fresh() * pump_delta_p / rho_out / self.pump_efficiency
                if rho_out > 0.0
                else 0.0
            )
            s.P_outlet.mark_stale()
            s.P_outlet.update(target_Pa)
            s.pump_power_watts.mark_stale()
            s.pump_power_watts.update(pump_pwr)
            self.outlet.P = target_Pa
        # T_outlet is unchanged — isentropic enthalpy rise is negligible for
        # liquid water at these pressures (~0.05 K per 10 MPa boost).
