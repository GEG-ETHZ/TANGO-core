"""Discretized (numerically-integrated) wellbore components for tango_next.

``NumericalInjectionWell`` and ``NumericalProductionWell`` replicate
``src/tango/units/native/well/base.py``'s ``WellUnitNative.process_stream()``
marching scheme: the wellbore is split into ``num_cells`` axial segments, and
pressure + enthalpy are integrated cell-by-cell with real CoolProp
fluid-property lookups at each step.

Governing equations (per cell):

- Pressure:  P[i] = P[i-1] - f_dir·ρ·g·dz - ΔP_friction   (Darcy-Weisbach)
- Enthalpy:  h[i] = h[i-1] - f_dir·g·dz - Q_loss / ṁ       (Adams 2015 heat-loss)

``f_dir = -1`` for injection (downward): gravity raises P, rock heats cold fluid.
``f_dir = +1`` for production (upward): gravity reduces P, hot fluid cools upward.

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

import math
from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np
from pydantic import Field

from tango_next.components.well.base import WellComponent
from tango_next.core.constants import GRAVITY, YEAR_TO_SECOND
from tango_next.core.fluid_state import FluidState
from tango_next.core.fluid_utils import reynolds_number
from tango_next.core.physics_models import (
    FrictionModel,
    HeatTransferModel,
    compute_friction_factor,
    compute_heat_loss,
)

# ---------------------------------------------------------------------------
# Shared state / history types (injection and production use same shape)
# ---------------------------------------------------------------------------


@dataclass
class NumericalWellState:
    """Full discretized simulation state for one numerical-well solve step.

    Cell arrays are ``list[float]`` for native Pydantic serialization.
    """

    T_inlet: float = field(default=float("nan"))
    P_inlet: float = field(default=float("nan"))
    mass_rate: float = field(default=float("nan"))
    t_d: float = field(default=0.0)
    """Dimensionless time at the end of this solve step (see module docstring)."""
    P_cells: list[float] = field(default_factory=list)
    h_cells: list[float] = field(default_factory=list)
    T_cells: list[float] = field(default_factory=list)
    rho_cells: list[float] = field(default_factory=list)
    mu_cells: list[float] = field(default_factory=list)
    u_cells: list[float] = field(default_factory=list)
    T_outlet: float = field(default=float("nan"))
    P_outlet: float = field(default=float("nan"))
    pump_power_watts: float = field(default=0.0)
    """Pump shaft power (W). Non-zero only for pump-equipped well components."""


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
        self.t_d.append(state.t_d)
        self.P_cells.append(list(state.P_cells))
        self.h_cells.append(list(state.h_cells))
        self.T_cells.append(list(state.T_cells))
        self.rho_cells.append(list(state.rho_cells))
        self.mu_cells.append(list(state.mu_cells))
        self.u_cells.append(list(state.u_cells))
        self.T_outlet.append(state.T_outlet)
        self.P_outlet.append(state.P_outlet)
        self.pump_power_watts.append(state.pump_power_watts)


NumericalInjectionWellHistory = NumericalWellHistory
NumericalProductionWellHistory = NumericalWellHistory


# ---------------------------------------------------------------------------
# Shared configuration fields (mixin via composition)
# ---------------------------------------------------------------------------

# These are declared on both NumericalInjectionWell and NumericalProductionWell
# because Pydantic does not support field-only mixins cleanly. They must be
# defined directly on the concrete class, not on a shared base.

_NUMERICAL_WELL_DOC = {
    "fluid_name": "CoolProp fluid name (e.g. ``'H2O'``) — from common: block.",
    "thermal_gradient": "Geothermal temperature gradient (K/m) — from common: block.",
    "surface_temperature": "Ambient surface temperature (K), used as far-field T0 at wellhead.",
    "rock_density": "Surrounding rock density (kg/m³) — from common: block.",
    "rock_cp": "Surrounding rock specific heat capacity (J/(kg·K)) — from common: block.",
    "rock_k": "Surrounding rock thermal conductivity (W/(m·K)) — from common: block.",
    "dt_years": "Simulation timestep duration (years) — used to advance dimensionless time.",
    "num_cells": "Axial discretization resolution. Matches src/tango/'s WellSpecsNative default.",
    "wellhead_depth": "Wellhead measured depth (m), matching src/tango/'s WellSpecsNative default.",
    "gravity_scale_factor": "Multiplier on standard gravity, matching src/tango/'s default.",
    "friction_model": "Darcy-Weisbach friction-factor correlation. Default matches src/tango/.",
    "heat_transfer_model": "Wellbore radial heat-loss correlation. Default matches src/tango/.",
}


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
) -> tuple[float, float, float, float, list[float]]:
    """Compute geometry-derived constants shared by both well types."""
    cell_length = well_length / num_cells
    relative_roughness = pipe_roughness / diameter
    cross_sectional_area = 0.25 * math.pi * diameter**2
    t_scaling_factor = 4.0 * rock_k / (rock_density * rock_cp * diameter**2)
    zspace = np.linspace(wellhead_depth, well_length, num_cells + 1)
    zspace = (zspace[1:] + zspace[:-1]) * 0.5
    T_r = (surface_temperature + zspace * thermal_gradient).tolist()
    return cell_length, relative_roughness, cross_sectional_area, t_scaling_factor, T_r


# ---------------------------------------------------------------------------
# NumericalInjectionWell
# ---------------------------------------------------------------------------


class NumericalInjectionWell(WellComponent):
    """Discretized injection wellbore: surface → reservoir bottom.

    See module docstring for governing equations and Phase 1 t_d caveat.
    """

    # ClassVar keeps Pydantic from treating this as a model field.
    # -1.0: downward flow (injection).
    F_DIR: ClassVar[float] = -1.0

    # ---- YAML configuration fields ----
    fluid_name: str
    thermal_gradient: float
    surface_temperature: float
    rock_density: float
    rock_cp: float
    rock_k: float
    dt_years: float
    num_cells: int = 100
    wellhead_depth: float = 0.0
    gravity_scale_factor: float = 1.0
    friction_model: FrictionModel = FrictionModel.HAALAND
    heat_transfer_model: HeatTransferModel = HeatTransferModel.ADAMS_2015

    # ---- Derived quantities (computed by init(), serialized for save/restore) ----
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
            self.rock_k,
            self.rock_density,
            self.rock_cp,
            self.surface_temperature,
            self.thermal_gradient,
        )
        self.t_d_old = 0.0

    def record(self, timestep: int) -> None:
        """Append state to history if save_interval permits."""
        if self.save_interval is None:
            return
        if timestep % self.save_interval == 0:
            self.history.record(self.state)

    def solve(self) -> None:
        """March the discretized wellbore from inlet to bottom-hole conditions."""
        s = self.state
        n = self.num_cells

        s.T_inlet = self.inlet.T
        s.P_inlet = self.inlet.P
        s.mass_rate = self.inlet.mass_rate

        del_t = self.t_scaling_factor * self.dt_years * YEAR_TO_SECOND
        s.t_d = self.t_d_old + del_t
        self.t_d_old = s.t_d

        P = np.zeros(n)
        h = np.zeros(n)
        T_f = np.zeros(n)
        rho = np.zeros(n)
        mu = np.zeros(n)
        u = np.zeros(n)

        inlet_state = FluidState.with_PT(self.fluid_name, s.P_inlet, s.T_inlet)
        P[0] = inlet_state.P
        h[0] = inlet_state.H
        T_f[0] = inlet_state.T
        rho[0] = inlet_state.rho
        mu[0] = inlet_state.mu
        u[0] = s.mass_rate / self.cross_sectional_area / rho[0]

        mdot = s.mass_rate
        A = self.cross_sectional_area
        g = GRAVITY * self.gravity_scale_factor
        dz = self.cell_length
        f_dir = self.F_DIR
        T_r = np.asarray(self.T_r)

        for i in range(1, n):
            Re = reynolds_number(mdot, self.diameter, mu[i - 1])
            ff = compute_friction_factor(self.friction_model, Re, self.diameter, self.pipe_roughness)
            dP_loss = 0.5 * ff * dz * rho[i - 1] * u[i - 1] ** 2 / self.diameter
            Q_loss = compute_heat_loss(
                self.heat_transfer_model,
                dL=self.cell_length,
                rock_k=self.rock_k,
                t_d=s.t_d,
                delta_T=T_f[i - 1] - T_r[i - 1],
            )
            dp_grav = f_dir * rho[i - 1] * g * dz
            P[i] = P[i - 1] - dp_grav - dP_loss
            h[i] = h[i - 1] - f_dir * g * dz - Q_loss / mdot

            cell_state = FluidState.with_HP(self.fluid_name, h[i], P[i])
            rho[i] = cell_state.rho
            mu[i] = cell_state.mu
            T_f[i] = cell_state.T
            u[i] = mdot / A / rho[i]

        s.P_cells = P.tolist()
        s.h_cells = h.tolist()
        s.T_cells = T_f.tolist()
        s.rho_cells = rho.tolist()
        s.mu_cells = mu.tolist()
        s.u_cells = u.tolist()
        s.P_outlet = P[-1]
        s.T_outlet = T_f[-1]

        self.outlet.T = s.T_outlet
        self.outlet.P = s.P_outlet
        self.outlet.mass_rate = s.mass_rate
        self.outlet.rho = rho[-1]
        self.outlet.mu = mu[-1]
        self.outlet.fluid_name = self.fluid_name


# ---------------------------------------------------------------------------
# NumericalProductionWell
# ---------------------------------------------------------------------------


class NumericalProductionWell(WellComponent):
    """Discretized production wellbore: reservoir bottom → surface.

    Identical marching scheme as ``NumericalInjectionWell`` with the sign of the
    flow direction reversed: ``F_DIR = +1.0`` (upward).  Matches
    ``src/tango/units/native/well/production_well.py``'s
    ``ProductionWellUnitNative`` which subclasses ``WellUnitNative`` with
    ``_f_dir = 1.0``.

    The hot brine enters at the bottom (cell 0, reservoir pressure/temperature)
    and exits at the top (cell n-1, lower P and slightly lower T due to Adams
    heat-loss to the cooler rock above).

    See module docstring for governing equations and Phase 1 t_d caveat.
    """

    # ClassVar keeps Pydantic from treating this as a model field.
    # +1.0: upward flow (production).
    F_DIR: ClassVar[float] = 1.0

    # ---- YAML configuration fields (mirrors NumericalInjectionWell) ----
    fluid_name: str
    thermal_gradient: float
    surface_temperature: float
    rock_density: float
    rock_cp: float
    rock_k: float
    dt_years: float
    num_cells: int = 100
    wellhead_depth: float = 0.0
    gravity_scale_factor: float = 1.0
    friction_model: FrictionModel = FrictionModel.HAALAND
    heat_transfer_model: HeatTransferModel = HeatTransferModel.ADAMS_2015

    # ---- Derived quantities (computed by init(), serialized for save/restore) ----
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
            self.rock_k,
            self.rock_density,
            self.rock_cp,
            self.surface_temperature,
            self.thermal_gradient,
        )
        self.t_d_old = 0.0

    def record(self, timestep: int) -> None:
        """Append state to history if save_interval permits."""
        if self.save_interval is None:
            return
        if timestep % self.save_interval == 0:
            self.history.record(self.state)

    def solve(self) -> None:
        """March the discretized wellbore from bottom-hole to wellhead conditions.

        Inlet (cell 0): reservoir bottom — hot, high pressure.
        Outlet (cell n-1): wellhead — slightly cooler, lower pressure.
        """
        s = self.state
        n = self.num_cells

        s.T_inlet = self.inlet.T
        s.P_inlet = self.inlet.P
        s.mass_rate = self.inlet.mass_rate

        del_t = self.t_scaling_factor * self.dt_years * YEAR_TO_SECOND
        s.t_d = self.t_d_old + del_t
        self.t_d_old = s.t_d

        P = np.zeros(n)
        h = np.zeros(n)
        T_f = np.zeros(n)
        rho = np.zeros(n)
        mu = np.zeros(n)
        u = np.zeros(n)

        inlet_state = FluidState.with_PT(self.fluid_name, s.P_inlet, s.T_inlet)
        P[0] = inlet_state.P
        h[0] = inlet_state.H
        T_f[0] = inlet_state.T
        rho[0] = inlet_state.rho
        mu[0] = inlet_state.mu
        u[0] = s.mass_rate / self.cross_sectional_area / rho[0]

        mdot = s.mass_rate
        A = self.cross_sectional_area
        g = GRAVITY * self.gravity_scale_factor
        dz = self.cell_length
        f_dir = self.F_DIR  # +1.0: upward
        T_r = np.asarray(self.T_r)

        for i in range(1, n):
            Re = reynolds_number(mdot, self.diameter, mu[i - 1])
            ff = compute_friction_factor(self.friction_model, Re, self.diameter, self.pipe_roughness)
            dP_loss = 0.5 * ff * dz * rho[i - 1] * u[i - 1] ** 2 / self.diameter
            Q_loss = compute_heat_loss(
                self.heat_transfer_model,
                dL=self.cell_length,
                rock_k=self.rock_k,
                t_d=s.t_d,
                delta_T=T_f[i - 1] - T_r[i - 1],
            )
            # Upward (f_dir = +1): gravity reduces P; enthalpy decreases as PE increases and heat lost
            dp_grav = f_dir * rho[i - 1] * g * dz
            P[i] = P[i - 1] - dp_grav - dP_loss
            h[i] = h[i - 1] - f_dir * g * dz - Q_loss / mdot

            cell_state = FluidState.with_HP(self.fluid_name, h[i], P[i])
            rho[i] = cell_state.rho
            mu[i] = cell_state.mu
            T_f[i] = cell_state.T
            u[i] = mdot / A / rho[i]

        s.P_cells = P.tolist()
        s.h_cells = h.tolist()
        s.T_cells = T_f.tolist()
        s.rho_cells = rho.tolist()
        s.mu_cells = mu.tolist()
        s.u_cells = u.tolist()
        s.P_outlet = P[-1]
        s.T_outlet = T_f[-1]

        self.outlet.T = s.T_outlet
        self.outlet.P = s.P_outlet
        self.outlet.mass_rate = s.mass_rate
        self.outlet.rho = rho[-1]
        self.outlet.mu = mu[-1]
        self.outlet.fluid_name = self.fluid_name


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
        target_Pa = self.pump_target_pressure_megapascals * 1e6
        if target_Pa > s.P_outlet:
            pump_delta_p = target_Pa - s.P_outlet
            rho_out = self.outlet.rho  # kg/m³ — set by super().solve() via CoolProp
            if rho_out > 0.0:
                s.pump_power_watts = s.mass_rate * pump_delta_p / rho_out / self.pump_efficiency
            s.P_outlet = target_Pa
            self.outlet.P = s.P_outlet
        else:
            s.pump_power_watts = 0.0
        # T_outlet is unchanged — isentropic enthalpy rise is negligible for
        # liquid water at these pressures (~0.05 K per 10 MPa boost).
