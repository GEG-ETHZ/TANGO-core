"""Lumped-parameter wellbore components for tango_next.

LumpedInjectionWell and LumpedProductionWell model a single-segment wellbore
as a 1-D pipe with:
  - Darcy–Weisbach frictional pressure drop
  - Hydrostatic pressure change (positive going down, negative going up)
  - Linear geothermal temperature profile (no wellbore heat-transfer model)

LumpedProductionWellWithPump adds a pump pressure boost at the wellhead.

**Design intent**: The ``Lumped*`` prefix marks 0-D / lumped-parameter models.
These are permanent optional variants to be kept alongside higher-fidelity
numerical-integration models once those are implemented.  Do NOT deprecate or
remove them when adding e.g. ``NumericalInjectionWell``.

Simplified-physics TODOs are marked throughout; upgrade path for each is noted.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from pydantic import Field

from tango_next.components.well.base import WellComponent
from tango_next.core.fluid_utils import (
    fluid_density,
    fluid_viscosity,
    friction_factor_darcy,
    hydrostatic_pressure,
    mean_velocity,
    pressure_drop_friction,
    reynolds_number,
)
from tango_next.core.locked_state import LockedState
from tango_next.core.specs import Common

# ---------------------------------------------------------------------------
# State dataclasses
# ---------------------------------------------------------------------------


def _ls(v: float = float("nan")) -> LockedState[float]:
    """Convenience: LockedState[float] starting stale with value ``v``."""
    ls: LockedState[float] = LockedState(v)
    ls.mark_stale()
    return ls


@dataclass(frozen=True)
class WellboreState:
    """Full simulation state for one wellbore solve step.

    All fields are ``LockedState[float]`` so that each is writable exactly once
    per timestep.  The dataclass is ``frozen=True`` to prevent replacing the
    wrapper objects themselves (the LockedState invariant is enforced on the
    value inside).  Call ``mark_all_stale()`` at the start of each ``solve()``
    to open the write slot for the new timestep.
    """

    T_inlet: LockedState[float] = field(default_factory=_ls)
    P_inlet: LockedState[float] = field(default_factory=_ls)
    mass_rate: LockedState[float] = field(default_factory=_ls)
    rho: LockedState[float] = field(default_factory=_ls)
    mu: LockedState[float] = field(default_factory=_ls)
    velocity: LockedState[float] = field(default_factory=_ls)
    Re: LockedState[float] = field(default_factory=_ls)
    friction_factor: LockedState[float] = field(default_factory=_ls)
    delta_p_friction: LockedState[float] = field(default_factory=_ls)
    delta_p_hydrostatic: LockedState[float] = field(default_factory=_ls)
    T_outlet: LockedState[float] = field(default_factory=_ls)
    P_outlet: LockedState[float] = field(default_factory=_ls)

    def mark_all_stale(self) -> None:
        """Mark every field stale — call at the start of each ``solve()``."""
        for f in dataclasses.fields(self):
            getattr(self, f.name).mark_stale()


@dataclass(frozen=True)
class ProductionWellWithPumpState(WellboreState):
    """Wellbore state extended with pump data for LumpedProductionWellWithPump."""

    pump_delta_p: LockedState[float] = field(default_factory=_ls)
    pump_power_watts: LockedState[float] = field(default_factory=_ls)


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
        self.T_inlet.append(state.T_inlet.get_fresh())
        self.T_outlet.append(state.T_outlet.get_fresh())
        self.P_inlet.append(state.P_inlet.get_fresh())
        self.P_outlet.append(state.P_outlet.get_fresh())


@dataclass
class ProductionWellWithPumpHistory(WellboreHistory):
    """Extends WellboreHistory with pump power for LumpedProductionWellWithPump."""

    pump_power_watts: list[float] = field(default_factory=list)

    def record(self, state: WellboreState) -> None:  # type: ignore[override]
        """Append one timestep snapshot, including pump power."""
        super().record(state)
        pump_state = state if isinstance(state, ProductionWellWithPumpState) else None
        self.pump_power_watts.append(pump_state.pump_power_watts.get_fresh() if pump_state else 0.0)


# ---------------------------------------------------------------------------
# LumpedInjectionWell
# ---------------------------------------------------------------------------


class LumpedInjectionWell(WellComponent):
    """Single-segment injection wellbore: surface → reservoir bottom.

    Simplified physics:
    - P_bottom = P_top + ρ·g·depth − ΔP_friction      (down → +hydrostatic)
    - T_bottom = T_top  + thermal_gradient · depth     (linear geotherm)

    TODO: replace linear T profile with transient conductive model.
    TODO: replace constant ρ, μ with CoolProp lookups.
    """

    common: Common = Field(frozen=True)
    """Shared fluid/rock parameters — a reference to the SAME Common
    instance every other component in the Workflow holds, not an
    independent copy. See core/specs.py."""

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
        s.mark_all_stale()

        s.T_inlet.update(self.inlet.T)
        s.P_inlet.update(self.inlet.P)
        s.mass_rate.update(self.inlet.mass_rate)

        rho = fluid_density(self.common.fluid_name, s.T_inlet.get_fresh(), s.P_inlet.get_fresh())
        mu = fluid_viscosity(self.common.fluid_name, s.T_inlet.get_fresh(), s.P_inlet.get_fresh())
        s.rho.update(rho)
        s.mu.update(mu)

        vel = mean_velocity(s.mass_rate.get_fresh(), rho, self.diameter)
        re = reynolds_number(s.mass_rate.get_fresh(), self.diameter, mu)
        ff = friction_factor_darcy(re, self.diameter, self.pipe_roughness)
        dp_f = pressure_drop_friction(ff, self.well_length, self.diameter, rho, vel)
        dp_h = hydrostatic_pressure(rho, self.well_length)
        s.velocity.update(vel)
        s.Re.update(re)
        s.friction_factor.update(ff)
        s.delta_p_friction.update(dp_f)
        s.delta_p_hydrostatic.update(dp_h)

        s.P_outlet.update(s.P_inlet.get_fresh() + dp_h - dp_f)
        s.T_outlet.update(s.T_inlet.get_fresh() + self.common.thermal_gradient * self.well_length)

        self.outlet.T = s.T_outlet.get_fresh()
        self.outlet.P = s.P_outlet.get_fresh()
        self.outlet.mass_rate = s.mass_rate.get_fresh()
        self.outlet.rho = rho
        self.outlet.mu = mu


# ---------------------------------------------------------------------------
# LumpedProductionWell
# ---------------------------------------------------------------------------


class LumpedProductionWell(WellComponent):
    """Single-segment production wellbore: reservoir bottom → surface.

    Simplified physics:
    - P_top = P_bottom − ρ·g·depth − ΔP_friction   (up → −hydrostatic)
    - T_top = T_inlet   (perfectly insulated — a more detailed thermal model is future work)

    TODO: implement Adams et al. (2015) transient conduction model.
    TODO: replace constant ρ, μ with CoolProp lookups.
    """

    common: Common = Field(frozen=True)
    """Shared fluid/rock parameters — a reference to the SAME Common
    instance every other component in the Workflow holds, not an
    independent copy. See core/specs.py."""

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
        s.mark_all_stale()

        s.T_inlet.update(self.inlet.T)
        s.P_inlet.update(self.inlet.P)
        s.mass_rate.update(self.inlet.mass_rate)

        rho = fluid_density(self.common.fluid_name, s.T_inlet.get_fresh(), s.P_inlet.get_fresh())
        mu = fluid_viscosity(self.common.fluid_name, s.T_inlet.get_fresh(), s.P_inlet.get_fresh())
        s.rho.update(rho)
        s.mu.update(mu)

        vel = mean_velocity(s.mass_rate.get_fresh(), rho, self.diameter)
        re = reynolds_number(s.mass_rate.get_fresh(), self.diameter, mu)
        ff = friction_factor_darcy(re, self.diameter, self.pipe_roughness)
        dp_f = pressure_drop_friction(ff, self.well_length, self.diameter, rho, vel)
        dp_h = hydrostatic_pressure(rho, self.well_length)
        s.velocity.update(vel)
        s.Re.update(re)
        s.friction_factor.update(ff)
        s.delta_p_friction.update(dp_f)
        s.delta_p_hydrostatic.update(dp_h)

        s.P_outlet.update(s.P_inlet.get_fresh() - dp_h - dp_f)
        s.T_outlet.update(s.T_inlet.get_fresh())  # perfectly insulated; Phase 2: Adams 2015

        self.outlet.T = s.T_outlet.get_fresh()
        self.outlet.P = s.P_outlet.get_fresh()
        self.outlet.mass_rate = s.mass_rate.get_fresh()
        self.outlet.rho = rho
        self.outlet.mu = mu


# ---------------------------------------------------------------------------
# LumpedProductionWellWithPump
# ---------------------------------------------------------------------------


class LumpedProductionWellWithPump(WellComponent):
    """Upper production wellbore segment with an optional pump.

    TODO: replace with TESPy Compressor or explicit pump curve.
    TODO: track pump electricity consumption in EconomicComponent.
    """

    common: Common = Field(frozen=True)
    """Shared fluid/rock parameters — a reference to the SAME Common
    instance every other component in the Workflow holds, not an
    independent copy. See core/specs.py."""
    pump_efficiency: float = Field(default=0.75, frozen=True)
    """Pump isentropic efficiency (dimensionless)."""
    pump_target_pressure_megapascals: float = Field(default=0.0, frozen=True)
    """Target outlet pressure from the pump (MPa). 0 means no active pump."""

    state: ProductionWellWithPumpState = Field(default_factory=ProductionWellWithPumpState)
    history: ProductionWellWithPumpHistory = Field(default_factory=ProductionWellWithPumpHistory)

    def record(self, timestep: int) -> None:
        """Append state to history if save_interval permits."""
        if self.save_interval is None:
            return
        if timestep % self.save_interval == 0:
            self.history.record(self.state)

    def solve(self) -> None:
        """Compute wellhead T and P including wellbore losses and pump boost."""
        s = self.state
        s.mark_all_stale()

        s.T_inlet.update(self.inlet.T)
        s.P_inlet.update(self.inlet.P)
        s.mass_rate.update(self.inlet.mass_rate)

        rho = fluid_density(self.common.fluid_name, s.T_inlet.get_fresh(), s.P_inlet.get_fresh())
        mu = fluid_viscosity(self.common.fluid_name, s.T_inlet.get_fresh(), s.P_inlet.get_fresh())
        s.rho.update(rho)
        s.mu.update(mu)

        vel = mean_velocity(s.mass_rate.get_fresh(), rho, self.diameter)
        re = reynolds_number(s.mass_rate.get_fresh(), self.diameter, mu)
        ff = friction_factor_darcy(re, self.diameter, self.pipe_roughness)
        dp_f = pressure_drop_friction(ff, self.well_length, self.diameter, rho, vel)
        dp_h = hydrostatic_pressure(rho, self.well_length)
        s.velocity.update(vel)
        s.Re.update(re)
        s.friction_factor.update(ff)
        s.delta_p_friction.update(dp_f)
        s.delta_p_hydrostatic.update(dp_h)

        P_after_wellbore = s.P_inlet.get_fresh() - dp_h - dp_f
        target_Pa = self.pump_target_pressure_megapascals * 1e6
        if target_Pa > P_after_wellbore:
            pump_dp = target_Pa - P_after_wellbore
            pump_pwr = s.mass_rate.get_fresh() * pump_dp / rho
        else:
            pump_dp = 0.0
            pump_pwr = 0.0
        s.pump_delta_p.update(pump_dp)
        s.pump_power_watts.update(pump_pwr)

        s.P_outlet.update(P_after_wellbore + pump_dp)
        s.T_outlet.update(s.T_inlet.get_fresh())  # simplified: insulated + no pump T rise (Phase 2)

        self.outlet.T = s.T_outlet.get_fresh()
        self.outlet.P = s.P_outlet.get_fresh()
        self.outlet.mass_rate = s.mass_rate.get_fresh()
        self.outlet.rho = rho
        self.outlet.mu = mu
