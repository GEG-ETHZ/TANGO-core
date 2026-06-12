"""Lumped-parameter reservoir component for tango_next.

LumpedReservoir models the subsurface as a single pressure-drop element
using linear Darcy flow (injection bottom → production bottom) and assumes
the produced fluid equilibrates to the current reservoir temperature.

This is a 0-D / lumped model — no spatial variation, no thermal depletion.
It serves as a placeholder that demonstrates the framework and gives
ballpark pressure drops.

Simplified-physics TODOs are marked throughout.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ConfigDict

from tango_next.components.reservoir.base import ReservoirComponent, ReservoirSpec
from tango_next.core.fluid_utils import water_density, water_viscosity

# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------


@dataclass
class LumpedReservoirState:
    """Full simulation state for one reservoir solve step.

    Stores inlet conditions, bulk reservoir properties, Darcy flow
    intermediates, and outlet conditions for post-processing and analysis.
    NaN defaults make un-computed fields visible during debugging.
    """

    # Inlet conditions (from injection well outlet)
    T_inlet: float = field(default=float("nan"))
    """Fluid temperature at reservoir inlet (K)."""
    P_inlet: float = field(default=float("nan"))
    """Fluid pressure at reservoir inlet (Pa)."""
    mass_rate: float = field(default=float("nan"))
    """Mass flow rate (kg/s)."""

    # Reservoir properties used this timestep
    T_reservoir: float = field(default=float("nan"))
    """Bulk reservoir temperature (K) — simplified from geothermal gradient."""
    P_reservoir: float = field(default=float("nan"))
    """Bulk reservoir pressure (Pa) — hydrostatic + overpressure."""

    # Fluid properties at reservoir conditions
    rho: float = field(default=float("nan"))
    """Fluid density at reservoir conditions (kg/m³)."""
    mu: float = field(default=float("nan"))
    """Dynamic viscosity at reservoir conditions (Pa·s)."""

    # Darcy flow
    delta_p_darcy: float = field(default=float("nan"))
    """Darcy pressure drop from injector to producer (Pa)."""

    # Outlet conditions (production bottom)
    T_outlet: float = field(default=float("nan"))
    """Fluid temperature at reservoir outlet (K)."""
    P_outlet: float = field(default=float("nan"))
    """Fluid pressure at reservoir outlet (Pa)."""


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------


class LumpedReservoirSpec(ReservoirSpec):
    """Specification for the lumped Darcy reservoir model."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    thermal_gradient: float
    """Geothermal temperature gradient (K/m) — from common: block."""
    surface_temperature: float
    """Ambient surface temperature (K) — used to compute T_reservoir."""
    well_spacing: float = 707.0
    """Injector-to-producer horizontal distance (m) — from schedule: block.
    Used as the Darcy flow path length.
    """


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


class LumpedReservoir(ReservoirComponent):
    """0-D lumped Darcy reservoir: linear flow between injector and producer.

    Pressure model (linear 1-D Darcy):
        ΔP_darcy = ṁ · μ / (ρ · k · h)
        Derived from Q = k·A·ΔP/(μ·L) with A = h·L, Q = ṁ/ρ.

    **Deviation from original ``src/tango/``**: the original uses a radial
    (Dupuit-Thiem) flow model — ``q = 2πhkΔP / (μ ln(rₑ/rw))`` — which
    accounts for the logarithmic pressure profile around each well.  This
    linear approximation overestimates ΔP for large well spacing and
    underestimates it for small spacing relative to the radial model.
    Human review is needed before using reservoir pressure-drop results from
    this component for engineering decisions.

    Reference for Darcy's law:
    Bear, J. (1972). Dynamics of Fluids in Porous Media. Elsevier.
    https://doi.org/10.1097/00010694-197508000-00022

    Reference for radial flow (original tango model, for comparison):
    Craft, B.C., Hawkins, M. & Terry, R.E. (1991). Applied Petroleum
    Reservoir Engineering, 2nd ed. Prentice Hall. ISBN 978-0131035614.

    Temperature model:
        T_outlet = T_reservoir  (fluid fully equilibrates to reservoir T)

    Thermal depletion is NOT modelled here.
    TODO (Phase 2): replace linear Darcy with radial Dupuit-Thiem flow to
                    match original tango (see BC_calculator.fracing_flow).
    TODO (Phase 2): implement Adams et al. (2015) 1-D thermal depletion model.
    TODO (Phase 2): replace constant ρ, μ with CoolProp lookups.
    TODO (Phase 2): support external reservoir simulators (CMG, MOOSE) via
                    the component-adapter pattern (see vision doc design note).
    """

    def __init__(self, spec: LumpedReservoirSpec) -> None:
        """Initialise reservoir with frozen spec and blank state."""
        super().__init__()
        self._spec = spec
        self.state = LumpedReservoirState()

    @classmethod
    def from_config(cls, config: dict) -> LumpedReservoir:
        """Build from a merged component + common + schedule config dict."""
        return cls(LumpedReservoirSpec(**config))

    @property
    def spec(self) -> LumpedReservoirSpec:
        """Return the frozen reservoir specification."""
        return self._spec

    def solve(self) -> None:
        """Compute reservoir outlet (T, P) from Darcy flow and geothermal gradient."""
        s = self.state
        s.T_inlet = self.inlet.T
        s.P_inlet = self.inlet.P
        s.mass_rate = self.inlet.mass_rate

        # Reservoir bulk conditions
        s.T_reservoir = (
            self._spec.surface_temperature + self._spec.thermal_gradient * self._spec.reservoir_depth
        )
        overpressure_fraction = 1.0 + self._spec.over_pressure_percentage / 100.0
        s.P_reservoir = self._spec.hydro_static_pressure * overpressure_fraction

        # Fluid properties at reservoir T, P — TODO (Phase 2): CoolProp
        s.rho = water_density(s.T_reservoir, s.P_reservoir)
        s.mu = water_viscosity(s.T_reservoir, s.P_reservoir)

        # Linear 1-D Darcy pressure drop — see class docstring for deviation note
        s.delta_p_darcy = s.mass_rate * s.mu / (s.rho * self._spec.permeability * self._spec.thickness)

        # Outlet: fluid exits at production bottom pressure and reservoir temperature
        s.P_outlet = s.P_reservoir - s.delta_p_darcy
        s.T_outlet = s.T_reservoir  # full thermal equilibration assumed

        self.outlet.T = s.T_outlet
        self.outlet.P = s.P_outlet
        self.outlet.mass_rate = s.mass_rate
        self.outlet.rho = s.rho
        self.outlet.mu = s.mu
        self.outlet.fluid_name = self.inlet.fluid_name
