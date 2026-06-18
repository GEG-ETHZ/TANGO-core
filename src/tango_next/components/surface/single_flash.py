"""Simplified Single-Flash surface / power-plant component.

SingleFlashSurface is a heavily simplified placeholder for the full TESPy-based
Single-Flash cycle. It:
  - Estimates gross thermal power from the enthalpy drop of the brine.
  - Resets the injection stream to surface temperature + approach temperature.
  - Exposes the BC variable (injection_pressure) so SystemBCIteration can
    update it each convergence iteration.

All thermodynamic cycle details (valve, separator, turbine, condenser, pumps)
are collapsed into a single efficiency parameter.

TODO (Phase 2): replace this stub with a full TESPy power-plant sub-graph.
TODO (Phase 2): implement flash-fraction calculation via CoolProp saturation.
TODO (Phase 2): compute parasitic loads (pumps, cooling tower fans) and net power.
TODO (Phase 2): wire to EconomicComponent for LCOE / NPV computation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import Field

from tango_next.components.surface.base import SurfaceComponent
from tango_next.core.fluid_utils import water_density, water_viscosity

# Specific heat capacity of liquid water (J/(kg·K)) — simplified constant.
# TODO (Phase 2): replace with CoolProp PropsSI("C", ...) at actual T, P.
_CP_WATER: float = 4182.0


# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------


@dataclass
class SingleFlashSurfaceState:
    """Full simulation state for one surface plant solve step.

    Stores inlet conditions, power-plant intermediates, and outlet conditions
    for post-processing and analysis.  NaN defaults make un-computed fields
    visible during debugging.
    """

    # Inlet conditions (hot production fluid from production well)
    T_inlet: float = field(default=float("nan"))
    """Production fluid temperature at surface inlet (K)."""
    P_inlet: float = field(default=float("nan"))
    """Production fluid pressure at surface inlet (Pa)."""
    mass_rate: float = field(default=float("nan"))
    """Mass flow rate (kg/s)."""

    # Power plant
    T_rejection: float = field(default=float("nan"))
    """Temperature at which heat is rejected to cooling (K)."""
    delta_h_brine: float = field(default=float("nan"))
    """Specific enthalpy drop of brine through the plant (J/kg).
    TODO (Phase 2): compute from CoolProp enthalpy difference.
    """
    gross_power_watts: float = field(default=float("nan"))
    """Gross thermal power extracted from brine (W).
    TODO (Phase 2): separate into turbine output and pump parasitic loads.
    """

    # Outlet conditions (cold injection fluid delivered to injection well)
    T_outlet: float = field(default=float("nan"))
    """Injection fluid temperature (K)."""
    P_outlet: float = field(default=float("nan"))
    """Injection fluid pressure (Pa) — the BC variable."""
    rho: float = field(default=float("nan"))
    """Injection fluid density (kg/m³)."""
    mu: float = field(default=float("nan"))
    """Injection fluid viscosity (Pa·s)."""


# ---------------------------------------------------------------------------
# History dataclass
# ---------------------------------------------------------------------------


@dataclass
class SingleFlashSurfaceHistory:
    """Per-timestep history of surface-plant scalar state."""

    T_inlet: list[float] = field(default_factory=list)
    """Production fluid temperature at surface inlet (K)."""
    T_outlet: list[float] = field(default_factory=list)
    """Injection fluid temperature leaving the surface (K)."""
    P_outlet: list[float] = field(default_factory=list)
    """Injection pressure BC variable (Pa)."""
    gross_power_watts: list[float] = field(default_factory=list)
    """Gross thermal power extracted from brine (W)."""

    def record(self, state: SingleFlashSurfaceState) -> None:
        """Append a snapshot of ``state`` as one timestep entry."""
        self.T_inlet.append(state.T_inlet)
        self.T_outlet.append(state.T_outlet)
        self.P_outlet.append(state.P_outlet)
        self.gross_power_watts.append(state.gross_power_watts)


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


class SingleFlashSurface(SurfaceComponent):
    """Simplified Single-Flash surface / power plant.

    The BC variable is ``injection_pressure``, which SystemBCIteration
    updates each iteration via ``set_injection_pressure()``.  The component
    exposes it explicitly so the orchestrator never has to reach into internals.

    Simplified physics:
        gross_power = mass_rate · Cp · (T_inlet − T_rejection) · cycle_efficiency
        T_outlet    = surface_temperature + approach_temperature
        P_outlet    = current injection_pressure (BC variable)

    **Deviation from original ``src/tango/``**: the original uses a full
    TESPy thermodynamic network (turbine, separator, condenser, pump nodes)
    to compute power output from first principles.  This component replaces
    that with a single lumped-efficiency first-law estimate:
        W_gross = ṁ · Cp · ΔT · η_cycle
    which ignores flash fraction, steam quality, condenser pinch, and all
    internal cycle irreversibilities.  Results will differ from the full
    TESPy model, particularly at low resource temperatures or high ambient
    temperatures where cycle efficiency is far from the assumed constant.
    Human review is needed before comparing power outputs from this component
    against original tango results.

    TODO (Phase 2): replace with full TESPy Single-Flash sub-graph
                    (see flexible_pp.py in src/tango/).
    TODO (Phase 2): compute net power (subtract pump and fan parasitics).
    TODO (Phase 2): track power time-series for LCOE calculation.
    """

    cycle_efficiency: float = 0.10
    """Fraction of brine enthalpy drop converted to gross electricity.
    Typical Single-Flash range: 0.08–0.12.  Does NOT account for pump or
    fan parasitic loads — those must be subtracted separately for net power.
    TODO (Phase 2): replace with TESPy cycle model; split into gross and
    parasitic components so net power is computed explicitly.
    """

    # ---- Runtime state / history ----
    state: SingleFlashSurfaceState = Field(default_factory=SingleFlashSurfaceState)
    history: SingleFlashSurfaceHistory = Field(default_factory=SingleFlashSurfaceHistory)

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

    def record(self, timestep: int) -> None:
        """Append state to history if save_interval permits."""
        if self.save_interval is None:
            return
        if timestep % self.save_interval == 0:
            self.history.record(self.state)

    def solve(self) -> None:
        """Compute gross power and injection stream from production fluid inlet."""
        s = self.state
        s.T_inlet = self.inlet.T
        s.P_inlet = self.inlet.P
        s.mass_rate = self.inlet.mass_rate

        # Heat rejection temperature: surface + approach temperature
        s.T_rejection = self.surface_temperature + self.approach_temperature

        # Gross power from brine enthalpy drop — simplified Cp model
        # TODO (Phase 2): delta_h_brine = CoolProp.H(T_inlet, P_inlet) − CoolProp.H(T_rejection, P_cond)
        s.delta_h_brine = _CP_WATER * (s.T_inlet - s.T_rejection)
        s.gross_power_watts = s.mass_rate * s.delta_h_brine * self.cycle_efficiency

        # Injection conditions: cool brine reinjected at surface temperature + approach
        s.T_outlet = s.T_rejection
        s.P_outlet = self.injection_pressure

        # Fluid properties for injection stream
        s.rho = water_density(s.T_outlet, s.P_outlet)
        s.mu = water_viscosity(s.T_outlet, s.P_outlet)

        self.outlet.T = s.T_outlet
        self.outlet.P = s.P_outlet
        self.outlet.mass_rate = s.mass_rate
        self.outlet.rho = s.rho
        self.outlet.mu = s.mu
        self.outlet.fluid_name = self.inlet.fluid_name
