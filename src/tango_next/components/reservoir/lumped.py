"""Lumped-parameter reservoir component for tango_next.

LumpedReservoir models the subsurface as a single pressure-drop element
using linear Darcy flow (injection bottom → production bottom) and assumes
the produced fluid equilibrates to the current reservoir temperature.

This is a 0-D / lumped model — no spatial variation, no thermal depletion.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import Field

from tango_next.components.reservoir.base import ReservoirComponent
from tango_next.core.fluid_utils import water_density, water_viscosity

# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------


@dataclass
class LumpedReservoirState:
    """Full simulation state for one reservoir solve step."""

    T_inlet: float = field(default=float("nan"))
    P_inlet: float = field(default=float("nan"))
    mass_rate: float = field(default=float("nan"))
    T_reservoir: float = field(default=float("nan"))
    P_reservoir: float = field(default=float("nan"))
    rho: float = field(default=float("nan"))
    mu: float = field(default=float("nan"))
    delta_p_darcy: float = field(default=float("nan"))
    T_outlet: float = field(default=float("nan"))
    P_outlet: float = field(default=float("nan"))


# ---------------------------------------------------------------------------
# History dataclass
# ---------------------------------------------------------------------------


@dataclass
class LumpedReservoirHistory:
    """Per-timestep history of lumped reservoir scalar state."""

    T_inlet: list[float] = field(default_factory=list)
    T_outlet: list[float] = field(default_factory=list)
    P_inlet: list[float] = field(default_factory=list)
    P_outlet: list[float] = field(default_factory=list)

    def record(self, state: LumpedReservoirState) -> None:
        """Append one timestep snapshot."""
        self.T_inlet.append(state.T_inlet)
        self.T_outlet.append(state.T_outlet)
        self.P_inlet.append(state.P_inlet)
        self.P_outlet.append(state.P_outlet)


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


class LumpedReservoir(ReservoirComponent):
    """0-D lumped Darcy reservoir: linear flow between injector and producer.

    Pressure model (linear 1-D Darcy):
        ΔP_darcy = ṁ · μ / (ρ · k · h)

    **Deviation from original ``src/tango/``**: the original uses a radial
    (Dupuit-Thiem) flow model.  This linear approximation deviates for large
    well spacing.  Human review is needed before using reservoir pressure-drop
    results from this component for engineering decisions.

    Temperature model:
        T_outlet = T_reservoir  (fluid fully equilibrates to reservoir T)

    TODO (Phase 2): replace linear Darcy with radial Dupuit-Thiem flow.
    TODO (Phase 2): implement Adams et al. (2015) 1-D thermal depletion model.
    TODO (Phase 2): replace constant ρ, μ with CoolProp lookups.
    """

    # ---- YAML configuration fields ----
    thermal_gradient: float
    """Geothermal temperature gradient (K/m) — from common: block."""
    surface_temperature: float
    """Ambient surface temperature (K) — used to compute T_reservoir."""
    well_spacing: float = 707.0
    """Injector-to-producer horizontal distance (m) — from layout: block."""

    # ---- Runtime state / history ----
    state: LumpedReservoirState = Field(default_factory=LumpedReservoirState)
    history: LumpedReservoirHistory = Field(default_factory=LumpedReservoirHistory)

    def record(self, timestep: int) -> None:
        """Append state to history if save_interval permits."""
        if self.save_interval is None:
            return
        if timestep % self.save_interval == 0:
            self.history.record(self.state)

    def solve(self) -> None:
        """Compute reservoir outlet (T, P) from Darcy flow and geothermal gradient."""
        s = self.state
        s.T_inlet = self.inlet.T
        s.P_inlet = self.inlet.P
        s.mass_rate = self.inlet.mass_rate

        s.T_reservoir = self.surface_temperature + self.thermal_gradient * self.reservoir_depth
        overpressure_fraction = 1.0 + self.over_pressure_percentage / 100.0
        s.P_reservoir = self.hydro_static_pressure * overpressure_fraction

        s.rho = water_density(s.T_reservoir, s.P_reservoir)
        s.mu = water_viscosity(s.T_reservoir, s.P_reservoir)

        s.delta_p_darcy = s.mass_rate * s.mu / (s.rho * self.permeability * self.thickness)

        s.P_outlet = s.P_reservoir - s.delta_p_darcy
        s.T_outlet = s.T_reservoir  # full thermal equilibration assumed

        self.outlet.T = s.T_outlet
        self.outlet.P = s.P_outlet
        self.outlet.mass_rate = s.mass_rate
        self.outlet.rho = s.rho
        self.outlet.mu = s.mu
        self.outlet.fluid_name = self.inlet.fluid_name
