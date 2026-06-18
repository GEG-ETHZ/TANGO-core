"""Lumped-parameter wellbore components for tango_next.

LumpedInjectionWell and LumpedProductionWell model a single-segment wellbore
as a 1-D pipe with:
  - Darcy–Weisbach frictional pressure drop
  - Hydrostatic pressure change (positive going down, negative going up)
  - Linear geothermal temperature profile (no wellbore heat-transfer model)

LumpedProductionWellPump adds a pump pressure boost at the wellhead.

**Design intent**: The ``Lumped*`` prefix marks 0-D / lumped-parameter models.
These are permanent optional variants to be kept alongside higher-fidelity
numerical-integration models once those are implemented.  Do NOT deprecate or
remove them when adding e.g. ``NumericalInjectionWell``.

Simplified-physics TODOs are marked throughout; upgrade path for each is noted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import Field

from tango_next.components.well.base import WellComponent
from tango_next.core.fluid_utils import (
    friction_factor_darcy,
    hydrostatic_pressure,
    mean_velocity,
    pressure_drop_friction,
    reynolds_number,
    water_density,
    water_viscosity,
)

# ---------------------------------------------------------------------------
# State dataclasses
# ---------------------------------------------------------------------------


@dataclass
class WellboreState:
    """Full simulation state for one wellbore solve step."""

    T_inlet: float = field(default=float("nan"))
    P_inlet: float = field(default=float("nan"))
    mass_rate: float = field(default=float("nan"))
    rho: float = field(default=float("nan"))
    mu: float = field(default=float("nan"))
    velocity: float = field(default=float("nan"))
    Re: float = field(default=float("nan"))
    friction_factor: float = field(default=float("nan"))
    delta_p_friction: float = field(default=float("nan"))
    delta_p_hydrostatic: float = field(default=float("nan"))
    T_outlet: float = field(default=float("nan"))
    P_outlet: float = field(default=float("nan"))


@dataclass
class ProductionWellPumpState(WellboreState):
    """Wellbore state extended with pump data for LumpedProductionWellPump."""

    pump_delta_p: float = field(default=float("nan"))
    pump_power_watts: float = field(default=float("nan"))


# ---------------------------------------------------------------------------
# History dataclasses
# ---------------------------------------------------------------------------


@dataclass
class WellboreHistory:
    """Per-timestep history of scalar wellbore state (inlet → outlet)."""

    T_inlet: list[float] = field(default_factory=list)
    T_outlet: list[float] = field(default_factory=list)
    P_inlet: list[float] = field(default_factory=list)
    P_outlet: list[float] = field(default_factory=list)

    def record(self, state: WellboreState) -> None:
        """Append one timestep snapshot."""
        self.T_inlet.append(state.T_inlet)
        self.T_outlet.append(state.T_outlet)
        self.P_inlet.append(state.P_inlet)
        self.P_outlet.append(state.P_outlet)


@dataclass
class ProductionWellPumpHistory(WellboreHistory):
    """Extends WellboreHistory with pump power for LumpedProductionWellPump."""

    pump_power_watts: list[float] = field(default_factory=list)

    def record(self, state: WellboreState) -> None:  # type: ignore[override]
        """Append one timestep snapshot, including pump power."""
        super().record(state)
        pump_state = state if isinstance(state, ProductionWellPumpState) else None
        self.pump_power_watts.append(pump_state.pump_power_watts if pump_state else 0.0)


# ---------------------------------------------------------------------------
# LumpedInjectionWell
# ---------------------------------------------------------------------------


class LumpedInjectionWell(WellComponent):
    """Single-segment injection wellbore: surface → reservoir bottom.

    Simplified physics:
    - P_bottom = P_top + ρ·g·depth − ΔP_friction      (down → +hydrostatic)
    - T_bottom = T_top  + thermal_gradient · depth     (linear geotherm)

    TODO (Phase 2): replace linear T profile with transient conductive model.
    TODO (Phase 2): replace constant ρ, μ with CoolProp lookups.
    """

    thermal_gradient: float
    """Geothermal temperature gradient (K/m) — from common: block."""

    state: WellboreState = Field(default_factory=WellboreState)
    history: WellboreHistory = Field(default_factory=WellboreHistory)

    def record(self, timestep: int) -> None:
        """Append state to history if save_interval permits."""
        if self.save_interval is None:
            return
        if timestep % self.save_interval == 0:
            self.history.record(self.state)

    def solve(self) -> None:
        """Compute bottom-hole T and P from surface injection conditions."""
        s = self.state
        s.T_inlet = self.inlet.T
        s.P_inlet = self.inlet.P
        s.mass_rate = self.inlet.mass_rate

        s.rho = water_density(s.T_inlet, s.P_inlet)
        s.mu = water_viscosity(s.T_inlet, s.P_inlet)

        s.velocity = mean_velocity(s.mass_rate, s.rho, self.diameter)
        s.Re = reynolds_number(s.mass_rate, self.diameter, s.mu)
        s.friction_factor = friction_factor_darcy(s.Re, self.diameter, self.pipe_roughness)
        s.delta_p_friction = pressure_drop_friction(
            s.friction_factor,
            self.well_length,
            self.diameter,
            s.rho,
            s.velocity,
        )
        s.delta_p_hydrostatic = hydrostatic_pressure(s.rho, self.well_length)

        s.P_outlet = s.P_inlet + s.delta_p_hydrostatic - s.delta_p_friction
        s.T_outlet = s.T_inlet + self.thermal_gradient * self.well_length

        self.outlet.T = s.T_outlet
        self.outlet.P = s.P_outlet
        self.outlet.mass_rate = s.mass_rate
        self.outlet.rho = s.rho
        self.outlet.mu = s.mu
        self.outlet.fluid_name = self.inlet.fluid_name


# ---------------------------------------------------------------------------
# LumpedProductionWell
# ---------------------------------------------------------------------------


class LumpedProductionWell(WellComponent):
    """Single-segment production wellbore: reservoir bottom → surface.

    Simplified physics:
    - P_top = P_bottom − ρ·g·depth − ΔP_friction   (up → −hydrostatic)
    - T_top = T_inlet   (perfectly insulated — thermal model is Phase 2)

    TODO (Phase 2): implement Adams et al. (2015) transient conduction model.
    TODO (Phase 2): replace constant ρ, μ with CoolProp lookups.
    """

    thermal_gradient: float
    """Geothermal temperature gradient (K/m) — from common: block."""

    state: WellboreState = Field(default_factory=WellboreState)
    history: WellboreHistory = Field(default_factory=WellboreHistory)

    def record(self, timestep: int) -> None:
        """Append state to history if save_interval permits."""
        if self.save_interval is None:
            return
        if timestep % self.save_interval == 0:
            self.history.record(self.state)

    def solve(self) -> None:
        """Compute wellhead T and P from reservoir outlet conditions."""
        s = self.state
        s.T_inlet = self.inlet.T
        s.P_inlet = self.inlet.P
        s.mass_rate = self.inlet.mass_rate

        s.rho = water_density(s.T_inlet, s.P_inlet)
        s.mu = water_viscosity(s.T_inlet, s.P_inlet)

        s.velocity = mean_velocity(s.mass_rate, s.rho, self.diameter)
        s.Re = reynolds_number(s.mass_rate, self.diameter, s.mu)
        s.friction_factor = friction_factor_darcy(s.Re, self.diameter, self.pipe_roughness)
        s.delta_p_friction = pressure_drop_friction(
            s.friction_factor,
            self.well_length,
            self.diameter,
            s.rho,
            s.velocity,
        )
        s.delta_p_hydrostatic = hydrostatic_pressure(s.rho, self.well_length)

        s.P_outlet = s.P_inlet - s.delta_p_hydrostatic - s.delta_p_friction
        s.T_outlet = s.T_inlet  # perfectly insulated; Phase 2: Adams 2015

        self.outlet.T = s.T_outlet
        self.outlet.P = s.P_outlet
        self.outlet.mass_rate = s.mass_rate
        self.outlet.rho = s.rho
        self.outlet.mu = s.mu
        self.outlet.fluid_name = self.inlet.fluid_name


# ---------------------------------------------------------------------------
# LumpedProductionWellPump
# ---------------------------------------------------------------------------


class LumpedProductionWellPump(WellComponent):
    """Upper production wellbore segment with an optional pump.

    TODO (Phase 2): replace with TESPy Compressor or explicit pump curve.
    TODO (Phase 2): track pump electricity consumption in EconomicComponent.
    """

    thermal_gradient: float
    """Geothermal temperature gradient (K/m) — from common: block."""
    pump_efficiency: float = 0.75
    """Pump isentropic efficiency (dimensionless)."""
    pump_target_pressure_megapascals: float = 0.0
    """Target outlet pressure from the pump (MPa). 0 means no active pump."""

    state: ProductionWellPumpState = Field(default_factory=ProductionWellPumpState)
    history: ProductionWellPumpHistory = Field(default_factory=ProductionWellPumpHistory)

    def record(self, timestep: int) -> None:
        """Append state to history if save_interval permits."""
        if self.save_interval is None:
            return
        if timestep % self.save_interval == 0:
            self.history.record(self.state)

    def solve(self) -> None:
        """Compute wellhead T and P including wellbore losses and pump boost."""
        s = self.state
        s.T_inlet = self.inlet.T
        s.P_inlet = self.inlet.P
        s.mass_rate = self.inlet.mass_rate

        s.rho = water_density(s.T_inlet, s.P_inlet)
        s.mu = water_viscosity(s.T_inlet, s.P_inlet)

        s.velocity = mean_velocity(s.mass_rate, s.rho, self.diameter)
        s.Re = reynolds_number(s.mass_rate, self.diameter, s.mu)
        s.friction_factor = friction_factor_darcy(s.Re, self.diameter, self.pipe_roughness)
        s.delta_p_friction = pressure_drop_friction(
            s.friction_factor,
            self.well_length,
            self.diameter,
            s.rho,
            s.velocity,
        )
        s.delta_p_hydrostatic = hydrostatic_pressure(s.rho, self.well_length)

        P_after_wellbore = s.P_inlet - s.delta_p_hydrostatic - s.delta_p_friction

        target_Pa = self.pump_target_pressure_megapascals * 1e6
        if target_Pa > P_after_wellbore:
            s.pump_delta_p = target_Pa - P_after_wellbore
            s.pump_power_watts = s.mass_rate * s.pump_delta_p / s.rho
        else:
            s.pump_delta_p = 0.0
            s.pump_power_watts = 0.0

        s.P_outlet = P_after_wellbore + s.pump_delta_p
        s.T_outlet = s.T_inlet  # simplified: insulated + no pump T rise (Phase 2)

        self.outlet.T = s.T_outlet
        self.outlet.P = s.P_outlet
        self.outlet.mass_rate = s.mass_rate
        self.outlet.rho = s.rho
        self.outlet.mu = s.mu
        self.outlet.fluid_name = self.inlet.fluid_name
