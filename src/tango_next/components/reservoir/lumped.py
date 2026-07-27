"""Lumped-parameter reservoir component for tango_next.

LumpedReservoir models the subsurface as a single pressure-drop element
using a doublet radial-flow impedance formula and tracks thermal depletion
via a cumulative-energy model. See References below for both.

Pressure model (doublet impedance — parity with src/tango/):
    Z = μ · [ln(L / (e · D)) + D / L] / (ρ · k · b_eff · π)
    ΔP = ṁ · Z

Temperature model (thermal depletion — parity with src/tango/):
    E += ṁ · (h_out − h_in) · Δt          (cumulative energy extracted)
    ψ  = E / (V_rock · ρ_rock · Cp_rock · (T₀ − T_inj))
    γ  = depletion_curve(ψ, p1, p2, p3)   (Adams 2015 fitting function)
    T_outlet = T_inj + γ · (T₀ − T_inj)

where T₀ = initial reservoir temperature, T_inj = current injection temperature.

References
----------
Doublet impedance:
    Adams, B.M. & Schädle, P. (2020). genGEO: coupled reservoir-electricity-cost
    geothermal simulator, v0.0.1 [Software]. Zenodo.
    https://doi.org/10.5281/zenodo.4383139

Thermal depletion (cumulative-energy / γ(ψ) fitting function):
    Adams, B.M. et al. (2015). A comparison of electric power output of CO2
    Plume Geothermal (CPG) and brine geothermal systems for varying reservoir
    conditions. Applied Energy, 140, 365-377.
    https://doi.org/10.1016/j.apenergy.2014.11.043

"""

from __future__ import annotations

import dataclasses
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
from tango_next.core.locked_state import LockedState
from tango_next.core.specs import Common

# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------


def _ls(v: float = float("nan")) -> LockedState[float]:
    """Convenience: LockedState[float] starting stale with value ``v``."""
    ls: LockedState[float] = LockedState(v)
    ls.mark_stale()
    return ls


@dataclass(frozen=True)
class LumpedReservoirState:
    """Full simulation state for one reservoir solve step.

    All fields are ``LockedState[float]`` so each is writable exactly once per
    timestep.  Call ``mark_all_stale()`` at the start of each ``solve()``.
    T_outlet and P_outlet start stale with NaN; use ``is_stale()`` rather than
    ``math.isnan()`` to detect "not yet solved" on the first call.
    """

    T_inlet: LockedState[float] = field(default_factory=_ls)
    P_inlet: LockedState[float] = field(default_factory=_ls)
    mass_rate: LockedState[float] = field(default_factory=_ls)
    T_reservoir_initial: LockedState[float] = field(default_factory=_ls)
    """Un-depleted geothermal temperature at reservoir depth (K)."""
    P_reservoir: LockedState[float] = field(default_factory=_ls)
    rho: LockedState[float] = field(default_factory=_ls)
    mu: LockedState[float] = field(default_factory=_ls)
    impedance: LockedState[float] = field(default_factory=_ls)
    """Doublet radial-flow impedance Z (Pa·s/kg). ΔP = ṁ·Z."""
    delta_p_darcy: LockedState[float] = field(default_factory=_ls)
    h_inlet: LockedState[float] = field(default_factory=_ls)
    """Specific enthalpy at inlet (J/kg)."""
    h_outlet: LockedState[float] = field(default_factory=_ls)
    """Specific enthalpy at outlet (J/kg) — computed at T_outlet, P_outlet."""
    psi: LockedState[float] = field(default_factory=_ls)
    """Fractional energy extraction ψ = E_extracted / E_reservoir."""
    gamma: LockedState[float] = field(default_factory=_ls)
    """Depletion factor γ ∈ [0, 1]. T_outlet = T_inj + γ·(T₀ − T_inj)."""
    T_outlet: LockedState[float] = field(default_factory=_ls)
    P_outlet: LockedState[float] = field(default_factory=_ls)

    def mark_all_stale(self) -> None:
        """Mark every field stale — call at the start of each ``solve()``."""
        for f in dataclasses.fields(self):
            getattr(self, f.name).mark_stale()


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
        self.T_inlet.append(state.T_inlet.get_fresh())
        self.T_outlet.append(state.T_outlet.get_fresh())
        self.P_inlet.append(state.P_inlet.get_fresh())
        self.P_outlet.append(state.P_outlet.get_fresh())
        self.psi.append(state.psi.get_fresh())
        self.gamma.append(state.gamma.get_fresh())


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


class LumpedReservoir(ReservoirComponent):
    """0-D lumped reservoir: doublet radial-flow impedance + Adams 2015 thermal depletion.

    Matches src/tango/units/native/reservoir.py for the DOUBLET well pattern.

    TODO (Phase 2): add 5-spot and inverted-5-spot impedance variants.
    """

    # ---- YAML configuration fields ----
    common: Common = Field(frozen=True)
    """Shared fluid/rock parameters — a reference to the SAME Common
    instance every other component in the Workflow holds, not an
    independent copy. See core/specs.py."""
    dt_years: float = Field(frozen=True)
    """Simulation timestep duration (years) — from sim_config.time.dt_years."""
    well_spacing: float = Field(default=707.0, frozen=True)
    """Injector-to-producer horizontal distance (m) — from layout: block."""
    well_eff_diameter: float = Field(default=0.41, frozen=True)
    """Effective well diameter for impedance calculation (m).
    Old tango computes this as the average of injection and production well
    diameters; set explicitly here for transparency.
    """
    net_to_gross_ratio: float = Field(default=1.0, frozen=True)
    """Net-to-gross ratio for effective reservoir thickness (dimensionless)."""

    # ---- Derived constants (computed by init(), serialized for save/restore) ----
    # Deliberately NOT frozen — init()/_recompute_depletion_coeffs() reassign
    # these directly (plain floats, not LockedState) each call; see
    # Component's class docstring for why fields like this stay mutable.
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
        self.T_initial = self.common.surface_temperature + self.common.thermal_gradient * self.reservoir_depth
        area = 0.5 * self.well_spacing**2  # DOUBLET area approximation
        volume = self.thickness * area
        fluid_volume = self.porosity * volume
        self.rock_volume = volume - fluid_volume
        self.rock_C_v = self.common.rock_density * self.common.rock_cp
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
        """Update the thermal-depletion curve-fit coefficients p1/p2/p3 from current fluid properties.

        Reference: Adams, B.M. et al. (2015). A comparison of electric power
        output of CO2 Plume Geothermal (CPG) and brine geothermal systems for
        varying reservoir conditions. Applied Energy, 140, 365-377.
        https://doi.org/10.1016/j.apenergy.2014.11.043
        """
        b = self.thickness
        k_rock = self.common.rock_k
        rho_rock = self.common.rock_density
        cp_rock = self.common.rock_cp
        R = self.well_spacing

        coeff1 = b * k_rock * rho_fluid / m_dot / rho_rock / cp_rock
        coeff2 = k_rock * R * rho_fluid / rho_rock / cp_fluid / m_dot

        self.p1 = min(-890.97 * coeff1 - 1.30, -1.3)
        self.p2 = 0.4095 * math.exp(-0.7815 * self.p1)
        self.p3 = float(np.clip(1.0 - 1.4646 * math.exp(-377.3 * coeff2), 0.0, 1.0))

    def _depletion_curve(self, psi: float) -> float:
        """γ(ψ): fraction of (T₀ − T_inj) remaining in produced fluid.

        Reference: Adams, B.M. et al. (2015). Applied Energy, 140, 365-377.
        https://doi.org/10.1016/j.apenergy.2014.11.043 (same curve-fit as
        ``_recompute_depletion_coeffs`` above — see its docstring).
        """
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

        # Capture previous-timestep outlet before marking stale.
        # is_stale() is True on the very first call (never been solved) — fall back to T_initial.
        T_out_prev = self.T_initial if s.T_outlet.is_stale() else s.T_outlet.get_fresh()
        P_reservoir_guess = self.hydro_static_pressure * (1.0 + self.over_pressure_percentage / 100.0)
        P_out_prev = P_reservoir_guess if s.P_outlet.is_stale() else s.P_outlet.get_fresh()

        s.mark_all_stale()

        s.T_inlet.update(self.inlet.T)
        s.P_inlet.update(self.inlet.P)
        s.mass_rate.update(self.inlet.mass_rate)

        T_inj = s.T_inlet.get_fresh()
        P_in = s.P_inlet.get_fresh()
        mdot = s.mass_rate.get_fresh()

        s.T_reservoir_initial.update(self.T_initial)
        s.P_reservoir.update(P_reservoir_guess)

        # Fluid properties: average of current inlet and previous-timestep outlet.
        rho = 0.5 * (water_density(T_inj, P_in) + water_density(T_out_prev, P_out_prev))
        mu = 0.5 * (water_viscosity(T_inj, P_in) + water_viscosity(T_out_prev, P_out_prev))
        s.rho.update(rho)
        s.mu.update(mu)

        # Doublet impedance (Adams et al. 2020)
        L = self.well_spacing
        D = self.well_eff_diameter
        b_eff = self.thickness * self.net_to_gross_ratio
        Z = mu * (math.log(L / (math.e * D)) + D / L) / (rho * self.permeability * b_eff * math.pi)
        dp = mdot * Z
        s.impedance.update(Z)
        s.delta_p_darcy.update(dp)
        P_out = P_in - dp
        s.P_outlet.update(P_out)

        # Thermal depletion (Adams 2015)
        dT = self.T_initial - T_inj
        h_in = water_enthalpy(T_inj, P_in)
        s.h_inlet.update(h_in)

        h_prod_prev = water_enthalpy(T_out_prev, P_out_prev)
        rho_avg = 0.5 * (water_density(T_inj, P_in) + water_density(T_out_prev, P_out_prev))
        cp_avg = 0.5 * (water_cp(T_inj, P_in) + water_cp(T_out_prev, P_out_prev))
        self._recompute_depletion_coeffs(mdot, rho_avg, cp_avg)

        dt_seconds = self.dt_years * YEAR_TO_SECOND
        self.energy_extracted += mdot * (h_prod_prev - h_in) * dt_seconds

        E_reservoir = self.rock_volume * self.rock_C_v * dT if dT > 0 else 1.0
        psi = self.energy_extracted / E_reservoir if dT > 0 else 0.0
        gamma = self._depletion_curve(psi) if dT > 0 else 1.0
        s.psi.update(psi)
        s.gamma.update(gamma)

        T_out = T_inj + gamma * dT
        s.T_outlet.update(T_out)
        s.h_outlet.update(water_enthalpy(T_out, P_out))

        self.outlet.T = T_out
        self.outlet.P = P_out
        self.outlet.mass_rate = mdot
        self.outlet.rho = water_density(T_out, P_out)
        self.outlet.mu = water_viscosity(T_out, P_out)
        self.outlet.fluid_name = self.inlet.fluid_name
