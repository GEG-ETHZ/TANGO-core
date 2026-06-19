"""Lumped-parameter reservoir component for tango_next.

LumpedReservoir models the subsurface as a single pressure-drop element
using the doublet radial-flow impedance formula (Adams et al. 2020) and
tracks thermal depletion via the Adams et al. (2015) cumulative-energy model.

Pressure model (doublet impedance — parity with src/tango/):
    Z = μ · [ln(L / (e · D)) + D / L] / (ρ · k · b_eff · π)
    ΔP = ṁ · Z

Temperature model (thermal depletion — parity with src/tango/):
    E += ṁ · (h_out − h_in) · Δt          (cumulative energy extracted)
    ψ  = E / (V_rock · ρ_rock · Cp_rock · (T₀ − T_inj))
    γ  = depletion_curve(ψ, p1, p2, p3)   (Adams 2015 fitting function)
    T_outlet = T_inj + γ · (T₀ − T_inj)

where T₀ = initial reservoir temperature, T_inj = current injection temperature.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from pydantic import Field
from scipy.special import erfc  # type: ignore[import-untyped]

from tango_next.components.reservoir.base import ReservoirComponent
from tango_next.core.constants import YEAR_TO_SECOND
from tango_next.core.fluid_utils import (
    water_cp,
    water_density,
    water_enthalpy,
    water_viscosity,
)

# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------


@dataclass
class LumpedReservoirState:
    """Full simulation state for one reservoir solve step."""

    T_inlet: float = field(default=float("nan"))
    P_inlet: float = field(default=float("nan"))
    mass_rate: float = field(default=float("nan"))
    T_reservoir_initial: float = field(default=float("nan"))
    """Un-depleted geothermal temperature at reservoir depth (K)."""
    P_reservoir: float = field(default=float("nan"))
    rho: float = field(default=float("nan"))
    mu: float = field(default=float("nan"))
    impedance: float = field(default=float("nan"))
    """Doublet radial-flow impedance Z (Pa·s/kg). ΔP = ṁ·Z."""
    delta_p_darcy: float = field(default=float("nan"))
    h_inlet: float = field(default=float("nan"))
    """Specific enthalpy at inlet (J/kg)."""
    h_outlet: float = field(default=float("nan"))
    """Specific enthalpy at outlet (J/kg) — computed at T_outlet, P_outlet."""
    psi: float = field(default=float("nan"))
    """Fractional energy extraction ψ = E_extracted / E_reservoir."""
    gamma: float = field(default=float("nan"))
    """Depletion factor γ ∈ [0, 1]. T_outlet = T_inj + γ·(T₀ − T_inj)."""
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
    psi: list[float] = field(default_factory=list)
    gamma: list[float] = field(default_factory=list)

    def record(self, state: LumpedReservoirState) -> None:
        """Append one timestep snapshot."""
        self.T_inlet.append(state.T_inlet)
        self.T_outlet.append(state.T_outlet)
        self.P_inlet.append(state.P_inlet)
        self.P_outlet.append(state.P_outlet)
        self.psi.append(state.psi)
        self.gamma.append(state.gamma)


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


class LumpedReservoir(ReservoirComponent):
    """0-D lumped reservoir: doublet radial-flow impedance + Adams 2015 thermal depletion.

    Matches src/tango/units/native/reservoir.py for the DOUBLET well pattern.

    TODO (Phase 2): add 5-spot and inverted-5-spot impedance variants.
    """

    # ---- YAML configuration fields ----
    thermal_gradient: float
    """Geothermal temperature gradient (K/m) — from common: block."""
    surface_temperature: float
    """Ambient surface temperature (K) — used to compute T₀."""
    rock_density: float
    """Rock bulk density (kg/m³) — from common: block."""
    rock_cp: float
    """Rock specific heat capacity (J/(kg·K)) — from common: block."""
    rock_k: float
    """Rock thermal conductivity (W/(m·K)) — from common: block."""
    dt_years: float
    """Simulation timestep duration (years) — from sim_config.time.dt_years."""
    well_spacing: float = 707.0
    """Injector-to-producer horizontal distance (m) — from layout: block."""
    well_eff_diameter: float = 0.41
    """Effective well diameter for impedance calculation (m).
    Old tango computes this as the average of injection and production well
    diameters; set explicitly here for transparency.
    """
    net_to_gross_ratio: float = 1.0
    """Net-to-gross ratio for effective reservoir thickness (dimensionless)."""

    # ---- Derived constants (computed by init(), serialized for save/restore) ----
    T_initial: float = 0.0
    """Un-depleted reservoir temperature = surface_T + gradient × depth (K)."""
    rock_volume: float = 0.0
    """Rock (non-fluid) volume = thickness × area × (1 − porosity) (m³)."""
    rock_C_v: float = 0.0  # noqa: N815
    """Volumetric heat capacity of rock = rock_density × rock_cp (J/(m³·K))."""
    p1: float = 0.0
    """Adams 2015 depletion curve coefficient p1."""
    p2: float = 0.0
    """Adams 2015 depletion curve coefficient p2."""
    p3: float = 0.0
    """Adams 2015 depletion curve coefficient p3."""

    # ---- Persistent across timesteps ----
    energy_extracted: float = 0.0
    """Cumulative thermal energy extracted from the reservoir (J)."""

    # ---- Runtime state / history ----
    state: LumpedReservoirState = Field(default_factory=LumpedReservoirState)
    history: LumpedReservoirHistory = Field(default_factory=LumpedReservoirHistory)

    def init(self) -> None:
        """Pre-compute geometry and depletion coefficients from validated fields."""
        self.T_initial = self.surface_temperature + self.thermal_gradient * self.reservoir_depth
        area = 0.5 * self.well_spacing**2  # DOUBLET area approximation
        volume = self.thickness * area
        fluid_volume = self.porosity * volume
        self.rock_volume = volume - fluid_volume
        self.rock_C_v = self.rock_density * self.rock_cp
        self.energy_extracted = 0.0
        self._recompute_depletion_coeffs(
            m_dot=self.inlet.mass_rate if self.inlet.mass_rate > 0 else 50.0,
            rho_fluid=water_density(
                self.T_initial,
                self.hydro_static_pressure * (1 + self.over_pressure_percentage / 100.0),
            ),
            cp_fluid=water_cp(
                self.T_initial,
                self.hydro_static_pressure * (1 + self.over_pressure_percentage / 100.0),
            ),
        )

    def _recompute_depletion_coeffs(self, m_dot: float, rho_fluid: float, cp_fluid: float) -> None:
        """Update Adams 2015 depletion coefficients from current fluid properties."""
        b = self.thickness
        k_rock = self.rock_k
        rho_rock = self.rock_density
        cp_rock = self.rock_cp
        R = self.well_spacing

        coeff1 = b * k_rock * rho_fluid / m_dot / rho_rock / cp_rock
        coeff2 = k_rock * R * rho_fluid / rho_rock / cp_fluid / m_dot

        self.p1 = min(-890.97 * coeff1 - 1.30, -1.3)
        self.p2 = 0.4095 * math.exp(-0.7815 * self.p1)
        self.p3 = float(np.clip(1.0 - 1.4646 * math.exp(-377.3 * coeff2), 0.0, 1.0))

    def _depletion_curve(self, psi: float) -> float:
        """Adams 2015 γ(ψ): fraction of (T₀ − T_inj) remaining in produced fluid."""
        p1, p2, p3 = self.p1, self.p2, self.p3
        if psi <= -p1 / p2:
            return 1.0 - (1.0 - p3) * (1.0 - 0.5 * float(erfc(p2 * psi + p1)))
        else:
            C = 1.13
            return 1.0 - (1.0 - p3) * (1.0 - 0.5 * math.exp(-C * (p2 * psi + p1)))

    def record(self, timestep: int) -> None:
        """Append state to history if save_interval permits."""
        if self.save_interval is None:
            return
        if timestep % self.save_interval == 0:
            self.history.record(self.state)

    def solve(self) -> None:
        """Compute reservoir outlet (T, P) from doublet impedance and thermal depletion."""
        s = self.state
        s.T_inlet = self.inlet.T
        s.P_inlet = self.inlet.P
        s.mass_rate = self.inlet.mass_rate

        s.T_reservoir_initial = self.T_initial
        overpressure_fraction = 1.0 + self.over_pressure_percentage / 100.0
        s.P_reservoir = self.hydro_static_pressure * overpressure_fraction

        # Fluid properties: average of inlet (current) and outlet (previous timestep).
        # Matches src/tango/ which uses average_mu = 0.5*(inlet_fluid.mu + outlet_fluid.mu).
        # On the first solve, s.T_outlet / s.P_outlet are NaN — fall back to T_initial.
        T_out_prev = self.T_initial if math.isnan(s.T_outlet) else s.T_outlet
        P_out_prev = s.P_reservoir if math.isnan(s.P_outlet) else s.P_outlet
        s.rho = 0.5 * (water_density(s.T_inlet, s.P_inlet) + water_density(T_out_prev, P_out_prev))
        s.mu = 0.5 * (water_viscosity(s.T_inlet, s.P_inlet) + water_viscosity(T_out_prev, P_out_prev))

        # Doublet impedance (Adams et al. 2020)
        L = self.well_spacing
        D = self.well_eff_diameter
        b_eff = self.thickness * self.net_to_gross_ratio
        s.impedance = (
            s.mu * (math.log(L / (math.e * D)) + D / L) / (s.rho * self.permeability * b_eff * math.pi)
        )
        s.delta_p_darcy = s.mass_rate * s.impedance
        # Pressure reference: injection well bottom P (src/tango/ uses inlet_fluid.P directly).
        s.P_outlet = s.P_inlet - s.delta_p_darcy

        # Thermal depletion (Adams 2015 — parity with src/tango/)
        T_inj = s.T_inlet
        dT = self.T_initial - T_inj
        s.h_inlet = water_enthalpy(T_inj, s.P_inlet)

        # Use previous timestep's actual outlet enthalpy (src/tango/ uses outlet_fluid.H, not
        # T_initial).  On the very first call, s.T_outlet is NaN — fall back to T_initial.
        T_out_prev = self.T_initial if math.isnan(s.T_outlet) else s.T_outlet
        P_out_prev = s.P_reservoir if math.isnan(s.P_outlet) else s.P_outlet
        h_prod_prev = water_enthalpy(T_out_prev, P_out_prev)

        # Depletion curve coefficients: use average fluid properties between inlet and previous outlet
        # (matches src/tango/ which uses average_rho, average_mu for impedance calc, and outlet_fluid
        # for energy accumulation).
        rho_avg = 0.5 * (water_density(T_inj, s.P_inlet) + water_density(T_out_prev, P_out_prev))
        cp_avg = 0.5 * (water_cp(T_inj, s.P_inlet) + water_cp(T_out_prev, P_out_prev))

        # Update depletion coefficients with current fluid properties (matches src/tango/ bc_iteration path)
        self._recompute_depletion_coeffs(s.mass_rate, rho_avg, cp_avg)

        dt_seconds = self.dt_years * YEAR_TO_SECOND
        delta_E = s.mass_rate * (h_prod_prev - s.h_inlet) * dt_seconds
        self.energy_extracted += delta_E

        E_reservoir = self.rock_volume * self.rock_C_v * dT if dT > 0 else 1.0
        s.psi = self.energy_extracted / E_reservoir if dT > 0 else 0.0
        s.gamma = self._depletion_curve(s.psi) if dT > 0 else 1.0

        s.T_outlet = T_inj + s.gamma * dT
        s.h_outlet = water_enthalpy(s.T_outlet, s.P_outlet)

        self.outlet.T = s.T_outlet
        self.outlet.P = s.P_outlet
        self.outlet.mass_rate = s.mass_rate
        self.outlet.rho = water_density(s.T_outlet, s.P_outlet)
        self.outlet.mu = water_viscosity(s.T_outlet, s.P_outlet)
        self.outlet.fluid_name = self.inlet.fluid_name
