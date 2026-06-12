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

from pydantic import ConfigDict

from tango_next.components.well.base import WellComponent, WellSpec
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
# State dataclasses — carry the full simulation state for each component.
# All variables (inlet conditions, fluid properties, hydraulic intermediates,
# outlet conditions) are stored for post-processing, plotting, and diagnostics.
# NaN defaults flag any field that was not reached during a solve.
# ---------------------------------------------------------------------------


@dataclass
class WellboreState:
    """Full simulation state for one wellbore solve step.

    Stores the complete set of variables — inlet conditions, fluid properties,
    hydraulic intermediates, and outlet conditions — so that the full state
    history is available for post-processing and analysis.  NaN defaults make
    un-computed fields visible during debugging.
    """

    # Inlet conditions (copied from inlet Stream)
    T_inlet: float = field(default=float("nan"))
    """Inlet fluid temperature (K)."""
    P_inlet: float = field(default=float("nan"))
    """Inlet fluid pressure (Pa)."""
    mass_rate: float = field(default=float("nan"))
    """Inlet mass flow rate (kg/s)."""

    # Fluid properties at inlet conditions
    rho: float = field(default=float("nan"))
    """Fluid density at inlet (kg/m³)."""
    mu: float = field(default=float("nan"))
    """Dynamic viscosity at inlet (Pa·s)."""

    # Hydraulic intermediates
    velocity: float = field(default=float("nan"))
    """Mean flow velocity (m/s)."""
    Re: float = field(default=float("nan"))
    """Reynolds number (dimensionless)."""
    friction_factor: float = field(default=float("nan"))
    """Darcy friction factor (dimensionless)."""
    delta_p_friction: float = field(default=float("nan"))
    """Frictional pressure loss (Pa), always ≥ 0."""
    delta_p_hydrostatic: float = field(default=float("nan"))
    """Hydrostatic pressure change magnitude (Pa), always ≥ 0."""

    # Outlet conditions
    T_outlet: float = field(default=float("nan"))
    """Outlet fluid temperature (K)."""
    P_outlet: float = field(default=float("nan"))
    """Outlet fluid pressure (Pa)."""


@dataclass
class ProductionWellPumpState(WellboreState):
    """Wellbore state extended with pump data for LumpedProductionWellPump."""

    pump_delta_p: float = field(default=float("nan"))
    """Pump pressure boost (Pa)."""
    pump_power_watts: float = field(default=float("nan"))
    """Pump shaft power (W)."""


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------


class LumpedInjectionWellSpec(WellSpec):
    """Specification for a lumped single-segment injection wellbore."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    thermal_gradient: float
    """Geothermal temperature gradient (K/m) — from common: block."""


class LumpedProductionWellSpec(WellSpec):
    """Specification for a lumped single-segment production wellbore."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    thermal_gradient: float
    """Geothermal temperature gradient (K/m) — from common: block."""


class LumpedProductionWellPumpSpec(WellSpec):
    """Specification for the upper production wellbore segment with a pump."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    thermal_gradient: float
    """Geothermal temperature gradient (K/m) — from common: block."""
    pump_efficiency: float = 0.75
    """Pump isentropic efficiency (dimensionless).
    TODO (Phase 2): wire to actual pump curve or TESPy Compressor.
    """
    pump_target_pressure_megapascals: float = 0.0
    """Target outlet pressure from the pump (MPa).  0 means no active pump.
    TODO (Phase 2): compute from injection pressure requirement.
    """


# ---------------------------------------------------------------------------
# Concrete components
# ---------------------------------------------------------------------------


class LumpedInjectionWell(WellComponent):
    """Single-segment injection wellbore: surface → reservoir bottom.

    Simplified physics:
    - P_bottom = P_top + ρ·g·depth − ΔP_friction      (down → +hydrostatic)
    - T_bottom = T_top  + thermal_gradient · depth     (linear geotherm)

    TODO (Phase 2): replace linear T profile with transient conductive model.
    TODO (Phase 2): replace constant ρ, μ with CoolProp lookups (see fluid_utils).
    """

    def __init__(self, spec: LumpedInjectionWellSpec) -> None:
        """Initialise wellbore with frozen spec and blank state."""
        super().__init__()
        self._spec = spec
        self.state = WellboreState()

    @classmethod
    def from_config(cls, config: dict) -> LumpedInjectionWell:
        """Build from a merged component + common config dict."""
        return cls(LumpedInjectionWellSpec(**config))

    @property
    def spec(self) -> LumpedInjectionWellSpec:
        """Return the frozen injection well specification."""
        return self._spec

    def solve(self) -> None:
        """Compute bottom-hole T and P from surface injection conditions."""
        s = self.state
        s.T_inlet = self.inlet.T
        s.P_inlet = self.inlet.P
        s.mass_rate = self.inlet.mass_rate

        # Fluid properties — TODO (Phase 2): CoolProp
        s.rho = water_density(s.T_inlet, s.P_inlet)
        s.mu = water_viscosity(s.T_inlet, s.P_inlet)

        # Hydraulics
        s.velocity = mean_velocity(s.mass_rate, s.rho, self._spec.diameter)
        s.Re = reynolds_number(s.mass_rate, self._spec.diameter, s.mu)
        s.friction_factor = friction_factor_darcy(
            s.Re,
            self._spec.diameter,
            self._spec.pipe_roughness,
        )
        s.delta_p_friction = pressure_drop_friction(
            s.friction_factor,
            self._spec.well_length,
            self._spec.diameter,
            s.rho,
            s.velocity,
        )
        s.delta_p_hydrostatic = hydrostatic_pressure(s.rho, self._spec.well_length)

        # Downward flow: hydrostatic raises P, friction lowers P
        s.P_outlet = s.P_inlet + s.delta_p_hydrostatic - s.delta_p_friction

        # Linear temperature increase with depth
        # TODO (Phase 2): replace with transient heat-conduction model
        s.T_outlet = s.T_inlet + self._spec.thermal_gradient * self._spec.well_length

        self.outlet.T = s.T_outlet
        self.outlet.P = s.P_outlet
        self.outlet.mass_rate = s.mass_rate
        self.outlet.rho = s.rho
        self.outlet.mu = s.mu
        self.outlet.fluid_name = self.inlet.fluid_name


class LumpedProductionWell(WellComponent):
    """Single-segment production wellbore: reservoir bottom → surface.

    Simplified physics:
    - P_top = P_bottom − ρ·g·depth − ΔP_friction   (up → −hydrostatic)
    - T_top = T_bottom − thermal_gradient · depth   (linear geotherm)

    TODO (Phase 2): replace linear T profile with transient conductive model.
    TODO (Phase 2): replace constant ρ, μ with CoolProp lookups.
    """

    def __init__(self, spec: LumpedProductionWellSpec) -> None:
        """Initialise wellbore with frozen spec and blank state."""
        super().__init__()
        self._spec = spec
        self.state = WellboreState()

    @classmethod
    def from_config(cls, config: dict) -> LumpedProductionWell:
        """Build from a merged component + common config dict."""
        return cls(LumpedProductionWellSpec(**config))

    @property
    def spec(self) -> LumpedProductionWellSpec:
        """Return the frozen production well specification."""
        return self._spec

    def solve(self) -> None:
        """Compute wellhead T and P from reservoir outlet conditions."""
        s = self.state
        s.T_inlet = self.inlet.T
        s.P_inlet = self.inlet.P
        s.mass_rate = self.inlet.mass_rate

        # Fluid properties — TODO (Phase 2): CoolProp
        s.rho = water_density(s.T_inlet, s.P_inlet)
        s.mu = water_viscosity(s.T_inlet, s.P_inlet)

        # Hydraulics
        s.velocity = mean_velocity(s.mass_rate, s.rho, self._spec.diameter)
        s.Re = reynolds_number(s.mass_rate, self._spec.diameter, s.mu)
        s.friction_factor = friction_factor_darcy(
            s.Re,
            self._spec.diameter,
            self._spec.pipe_roughness,
        )
        s.delta_p_friction = pressure_drop_friction(
            s.friction_factor,
            self._spec.well_length,
            self._spec.diameter,
            s.rho,
            s.velocity,
        )
        s.delta_p_hydrostatic = hydrostatic_pressure(s.rho, self._spec.well_length)

        # Upward flow: hydrostatic lowers P, friction also lowers P (opposes flow)
        s.P_outlet = s.P_inlet - s.delta_p_hydrostatic - s.delta_p_friction

        # Simplified thermal model: perfectly insulated well — fluid stays at
        # inlet temperature.  The injection well correctly heats the cold fluid
        # against the geothermal gradient; for the production well the dominant
        # effect is that hot fluid rises faster than it loses heat.
        # TODO (Phase 2): implement Adams et al. (2015) transient conduction model,
        #                 which gives T_outlet between T_inlet and T_surface depending
        #                 on flow rate, wellbore insulation, and elapsed time.
        s.T_outlet = s.T_inlet

        self.outlet.T = s.T_outlet
        self.outlet.P = s.P_outlet
        self.outlet.mass_rate = s.mass_rate
        self.outlet.rho = s.rho
        self.outlet.mu = s.mu
        self.outlet.fluid_name = self.inlet.fluid_name


class LumpedProductionWellPump(WellComponent):
    """Upper production wellbore segment with an optional pump.

    Extends LumpedProductionWell with a pump stage that boosts P_outlet.
    If pump_target_pressure_megapascals == 0, no boost is applied.

    TODO (Phase 2): replace with TESPy Compressor or explicit pump curve.
    TODO (Phase 2): track pump electricity consumption in EconomicComponent.
    """

    def __init__(self, spec: LumpedProductionWellPumpSpec) -> None:
        """Initialise wellbore+pump with frozen spec and blank state."""
        super().__init__()
        self._spec = spec
        self.state = ProductionWellPumpState()

    @classmethod
    def from_config(cls, config: dict) -> LumpedProductionWellPump:
        """Build from a merged component + common config dict."""
        return cls(LumpedProductionWellPumpSpec(**config))

    @property
    def spec(self) -> LumpedProductionWellPumpSpec:
        """Return the frozen production well + pump specification."""
        return self._spec

    def solve(self) -> None:
        """Compute wellhead T and P including wellbore losses and pump boost.

        NOTE: This component models the upper production wellbore segment AND
        the wellhead pump as a single unit, matching the structure of the
        original TANGO implementation.
        TODO (Phase 2): split into separate LumpedProductionWell and
        LumpedWellheadPump components to allow independent configuration and
        cleaner energy accounting.
        NOTE: pump electricity consumption is currently NOT tracked
        (pump_power_watts is computed but not wired to an EconomicComponent).
        TODO (Phase 2): wire pump_power_watts to EconomicComponent parasitic
        load accounting (injection pump same issue — see vision doc).
        """
        s = self.state
        s.T_inlet = self.inlet.T
        s.P_inlet = self.inlet.P
        s.mass_rate = self.inlet.mass_rate

        # Fluid properties — TODO (Phase 2): CoolProp
        s.rho = water_density(s.T_inlet, s.P_inlet)
        s.mu = water_viscosity(s.T_inlet, s.P_inlet)

        # Hydraulics (wellbore segment, same as production well)
        s.velocity = mean_velocity(s.mass_rate, s.rho, self._spec.diameter)
        s.Re = reynolds_number(s.mass_rate, self._spec.diameter, s.mu)
        s.friction_factor = friction_factor_darcy(
            s.Re,
            self._spec.diameter,
            self._spec.pipe_roughness,
        )
        s.delta_p_friction = pressure_drop_friction(
            s.friction_factor,
            self._spec.well_length,
            self._spec.diameter,
            s.rho,
            s.velocity,
        )
        s.delta_p_hydrostatic = hydrostatic_pressure(s.rho, self._spec.well_length)

        # Wellbore pressure change (upward)
        P_after_wellbore = s.P_inlet - s.delta_p_hydrostatic - s.delta_p_friction

        # Pump stage
        target_Pa = self._spec.pump_target_pressure_megapascals * 1e6
        if target_Pa > P_after_wellbore:
            s.pump_delta_p = target_Pa - P_after_wellbore
            # Ideal pump work; TODO (Phase 2): account for isentropic efficiency
            s.pump_power_watts = s.mass_rate * s.pump_delta_p / s.rho
        else:
            s.pump_delta_p = 0.0
            s.pump_power_watts = 0.0

        s.P_outlet = P_after_wellbore + s.pump_delta_p

        # Simplified: perfectly insulated, pump enthalpy rise ignored.
        # TODO (Phase 2): T_outlet = T_inlet + pump_delta_p / (rho * Cp)
        # TODO (Phase 2): implement Adams et al. (2015) wellbore heat-loss model.
        s.T_outlet = s.T_inlet

        self.outlet.T = s.T_outlet
        self.outlet.P = s.P_outlet
        self.outlet.mass_rate = s.mass_rate
        self.outlet.rho = s.rho
        self.outlet.mu = s.mu
        self.outlet.fluid_name = self.inlet.fluid_name
