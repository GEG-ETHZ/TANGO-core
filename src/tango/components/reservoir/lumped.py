"""Lumped-parameter reservoir component for tango.

LumpedReservoir models the subsurface as a single pressure-drop element
using a doublet radial-flow impedance formula and tracks thermal depletion
via a cumulative-energy model. See References below for both.

Pressure model (doublet impedance):
    Z = μ · [ln(L / (e · D)) + D / L] / (ρ · k · b_eff · π)
    ΔP = ṁ · Z

Temperature model (thermal depletion):
    E += ṁ · (h_out − h_in) · Δt          (cumulative energy extracted)
    ψ  = E / (V_rock · ρ_rock · Cp_rock · (T₀ − T_inj))
    γ  = depletion_curve(ψ, p1, p2, p3)   (Adams 2015 fitting function)
    T_outlet = T_inj + γ · (T₀ − T_inj)

where T₀ = initial reservoir temperature, T_inj = current injection temperature.

References:
Doublet impedance:
    [Adams, B.M. & Schädle, P. (2020). genGEO: coupled reservoir-electricity-cost
    geothermal simulator, v0.0.1 [Software]. Zenodo.](https://doi.org/10.5281/zenodo.4383139)

Thermal depletion (cumulative-energy / γ(ψ) fitting function):
    [Adams, B.M. et al. (2015). A comparison of electric power output of CO2
    Plume Geothermal (CPG) and brine geothermal systems for varying reservoir
    conditions. Applied Energy, 140, 365-377.](https://doi.org/10.1016/j.apenergy.2014.11.043)

"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from pydantic import Field
from scipy.special import erfc  # type: ignore[import-untyped]

from tango.components.reservoir.base import ReservoirComponent
from tango.components.reservoir.wellpattern_impedance import WellPattern
from tango.core.constants import YEAR_TO_SECOND
from tango.core.fluid_utils import (
    fluid_cp,
    fluid_density,
    fluid_enthalpy,
    fluid_viscosity,
)
from tango.core.locked_state import LockedState
from tango.core.specs import Common
from tango.core.state_methods import StateMethods
from tango.core.stream import Stream

# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------


def _ls(v: float = float("nan")) -> LockedState[float]:
    """Convenience: LockedState[float] starting stale with value ``v``."""
    ls: LockedState[float] = LockedState(v)
    ls.mark_stale()
    return ls


def _locked(value: bool) -> LockedState[bool]:  # noqa: FBT001
    """Convenience: LockedState[bool] starting stale with value ``value``."""
    ls: LockedState[bool] = LockedState(value)
    ls.mark_stale()
    return ls


@dataclass(frozen=True)
class LumpedReservoirState(StateMethods):
    """Full simulation state for one reservoir solve step.

    All fields are ``LockedState[float]`` so each is writable exactly once per
    timestep.  ``mark_all_stale()`` (inherited from ``StateMethods``) is
    called by the orchestrator (via ``Component.mark_all_stale()``)
    immediately before each ``solve()``.
    T_outlet and P_outlet start stale with NaN; use ``is_stale()`` rather than
    ``math.isnan()`` to detect "not yet solved" on the first call.
    """

    T_inlet: LockedState[float] = field(default_factory=_ls)
    """Inlet temperature from the injection well (K). TODO(docs): drafted, review."""
    P_inlet: LockedState[float] = field(default_factory=_ls)
    """Inlet pressure from the injection well (Pa). TODO(docs): drafted, review."""
    mass_rate: LockedState[float] = field(default_factory=_ls)
    """Mass flow rate through the reservoir (kg/s). TODO(docs): drafted, review."""
    T_reservoir_initial: LockedState[float] = field(default_factory=_ls)
    """Un-depleted geothermal temperature at reservoir depth (K)."""
    P_reservoir: LockedState[float] = field(default_factory=_ls)
    """Un-depleted reservoir pressure (Pa) — see ``LumpedReservoir.P_initial``."""
    rho: LockedState[float] = field(default_factory=_ls)
    """Fluid density, averaged between inlet and previous outlet (kg/m3). TODO(docs): drafted, review."""
    mu: LockedState[float] = field(default_factory=_ls)
    """Fluid dynamic viscosity, averaged between inlet and previous outlet (Pa s). TODO(docs): drafted, review."""
    impedance: LockedState[float] = field(default_factory=_ls)
    """Doublet radial-flow impedance Z (Pa·s/kg). ΔP = ṁ·Z."""
    delta_p_darcy: LockedState[float] = field(default_factory=_ls)
    """Darcy pressure drop across the reservoir, mass_rate times impedance (Pa); P_outlet = P_inlet - delta_p_darcy. TODO(docs): drafted, review."""
    h_inlet: LockedState[float] = field(default_factory=_ls)
    """Specific enthalpy at inlet (J/kg)."""
    h_outlet: LockedState[float] = field(default_factory=_ls)
    """Specific enthalpy at outlet (J/kg) — computed at T_outlet, P_outlet."""
    psi: LockedState[float] = field(default_factory=_ls)
    """Fractional energy extraction ψ = E_extracted / E_reservoir."""
    gamma: LockedState[float] = field(default_factory=_ls)
    """Depletion factor γ ∈ [0, 1]. T_outlet = T_inj + γ·(T₀ − T_inj)."""
    T_outlet: LockedState[float] = field(default_factory=_ls)
    """Outlet temperature"""
    P_outlet: LockedState[float] = field(default_factory=_ls)
    """Outlet pressure"""
    p1: LockedState[float] = field(default_factory=_ls)
    """Adams 2015 depletion curve coefficient p1 — recomputed every ``solve()``
    call from the current fluid properties (see ``_recompute_depletion_coeffs``)."""
    p2: LockedState[float] = field(default_factory=_ls)
    """Adams 2015 depletion curve coefficient p2."""
    p3: LockedState[float] = field(default_factory=_ls)
    """Adams 2015 depletion curve coefficient p3."""
    energy_extraction_rate: LockedState[float] = field(default_factory=_ls)
    """Instantaneous thermal power extracted from the reservoir this solve
    (W) — ``mdot * (h_prod_prev - h_in)``. Written by ``solve()`` before
    calling ``set_cumulative()``, which reads it back to increment
    ``energy_extracted``: the rate is a fresh, ordinary state field;
    only the accumulation step is special."""
    energy_extracted: LockedState[float] = field(default_factory=lambda: _ls(0.0))
    """Cumulative thermal energy extracted from the reservoir (J), across all
    timesteps so far. Updated via ``set_cumulative()`` (see below), not
    ``update()`` — it's a running total, not a value recomputed from scratch
    each timestep. Genuinely depends on its own value from the previous
    *converged* timestep, which is exactly why it lives in ``state``: a
    within-timestep re-solve (an injection-temperature convergence loop)
    restores the whole of ``state`` first, so this always increments from
    the last converged value, never from a discarded re-solve attempt."""
    ever_solved: LockedState[bool] = field(default_factory=lambda: _locked(value=False))
    """Whether ``solve()`` has ever completed for this component instance.

    ``solve()`` needs to know whether ``T_outlet``/``P_outlet`` hold a real
    previous-timestep value or are still at their unsolved NaN default. Read
    via the normal ``get_stale()`` (before this call) / ``update()`` (for
    the next call) cycle — not via ``is_stale()``/``is_fresh()`` directly,
    which would break across a ``Workflow.to_dict()`` → mutate →
    ``Workflow(cfg)`` sweep-point reconstruction (``LockedState``'s Pydantic
    validator always starts a reconstructed instance **fresh** — see
    ``LockedState.__get_pydantic_core_schema__``'s docstring — so the
    *status* can't be trusted as the signal post-reconstruction). The
    *value* round-trips correctly regardless of status, so reading it the
    same way every other ``LockedState`` field is read sidesteps the
    problem entirely.
    """

    def set_cumulative(self, dt_years: float) -> None:
        """Increment ``energy_extracted`` from ``energy_extraction_rate * dt``.

        No automatic derivation exists for this — every accumulator is
        hand-written physics — this is tango's one leaf implementation,
        called from ``solve()`` right where the inline
        ``energy_extracted.increment(...)`` call used to be.
        """
        dt_seconds = dt_years * YEAR_TO_SECOND
        self.energy_extracted.increment(self.energy_extraction_rate.get_fresh() * dt_seconds)
        super().set_cumulative(dt_years)

    def reset_cumulative(self) -> None:
        """Reset ``energy_extracted`` to zero (e.g. re-running from t=0 without reconstructing)."""
        self.energy_extracted.mark_stale()
        self.energy_extracted.update(0.0)
        super().reset_cumulative()


# ---------------------------------------------------------------------------
# History dataclass
# ---------------------------------------------------------------------------


@dataclass
class LumpedReservoirHistory:
    """Per-timestep history of lumped reservoir scalar state.

    One list field per ``LumpedReservoirState`` attribute (TANGO
    Commandment: every ``*State`` attribute must have an analog in its
    ``*History`` class) — see ``record()``.
    """

    T_inlet: list[float] = field(default_factory=list)
    """Per-timestep inlet temperature (K). TODO(docs): drafted, review."""
    T_outlet: list[float] = field(default_factory=list)
    """Per-timestep outlet temperature (K). TODO(docs): drafted, review."""
    P_inlet: list[float] = field(default_factory=list)
    """Per-timestep inlet pressure (Pa). TODO(docs): drafted, review."""
    P_outlet: list[float] = field(default_factory=list)
    """Per-timestep outlet pressure (Pa). TODO(docs): drafted, review."""
    mass_rate: list[float] = field(default_factory=list)
    """Per-timestep mass flow rate (kg/s). TODO(docs): drafted, review."""
    T_reservoir_initial: list[float] = field(default_factory=list)
    """Per-timestep un-depleted reservoir temperature (K). TODO(docs): drafted, review."""
    P_reservoir: list[float] = field(default_factory=list)
    """Per-timestep un-depleted reservoir pressure (Pa). TODO(docs): drafted, review."""
    rho: list[float] = field(default_factory=list)
    """Per-timestep averaged fluid density (kg/m3). TODO(docs): drafted, review."""
    mu: list[float] = field(default_factory=list)
    """Per-timestep averaged fluid dynamic viscosity (Pa s). TODO(docs): drafted, review."""
    impedance: list[float] = field(default_factory=list)
    """Per-timestep reservoir impedance (Pa s/kg). TODO(docs): drafted, review."""
    delta_p_darcy: list[float] = field(default_factory=list)
    """Per-timestep Darcy pressure drop across the reservoir (Pa). TODO(docs): drafted, review."""
    h_inlet: list[float] = field(default_factory=list)
    """Per-timestep inlet specific enthalpy (J/kg). TODO(docs): drafted, review."""
    h_outlet: list[float] = field(default_factory=list)
    """Per-timestep outlet specific enthalpy (J/kg). TODO(docs): drafted, review."""
    psi: list[float] = field(default_factory=list)
    """Per-timestep fractional energy extraction psi (dimensionless). TODO(docs): drafted, review."""
    gamma: list[float] = field(default_factory=list)
    """Per-timestep depletion factor gamma, between 0 and 1. TODO(docs): drafted, review."""
    p1: list[float] = field(default_factory=list)
    """Per-timestep depletion curve coefficient p1. TODO(docs): drafted, review."""
    p2: list[float] = field(default_factory=list)
    """Per-timestep depletion curve coefficient p2. TODO(docs): drafted, review."""
    p3: list[float] = field(default_factory=list)
    """Per-timestep depletion curve coefficient p3. TODO(docs): drafted, review."""
    energy_extraction_rate: list[float] = field(default_factory=list)
    """Per-timestep thermal power extracted from the reservoir (W). TODO(docs): drafted, review."""
    energy_extracted: list[float] = field(default_factory=list)
    """Per-timestep cumulative thermal energy extracted (J). TODO(docs): drafted, review."""
    ever_solved: list[bool] = field(default_factory=list)
    """Per-timestep flag: whether the reservoir had been solved before. TODO(docs): drafted, review."""

    def record(self, state: LumpedReservoirState) -> None:
        """Append one timestep snapshot."""
        self.T_inlet.append(state.T_inlet.get_fresh())
        self.T_outlet.append(state.T_outlet.get_fresh())
        self.P_inlet.append(state.P_inlet.get_fresh())
        self.P_outlet.append(state.P_outlet.get_fresh())
        self.mass_rate.append(state.mass_rate.get_fresh())
        self.T_reservoir_initial.append(state.T_reservoir_initial.get_fresh())
        self.P_reservoir.append(state.P_reservoir.get_fresh())
        self.rho.append(state.rho.get_fresh())
        self.mu.append(state.mu.get_fresh())
        self.impedance.append(state.impedance.get_fresh())
        self.delta_p_darcy.append(state.delta_p_darcy.get_fresh())
        self.h_inlet.append(state.h_inlet.get_fresh())
        self.h_outlet.append(state.h_outlet.get_fresh())
        self.p1.append(state.p1.get_fresh())
        self.p2.append(state.p2.get_fresh())
        self.p3.append(state.p3.get_fresh())
        self.energy_extraction_rate.append(state.energy_extraction_rate.get_fresh())
        self.energy_extracted.append(state.energy_extracted.get_fresh())
        self.ever_solved.append(state.ever_solved.get_fresh())
        self.psi.append(state.psi.get_fresh())
        self.gamma.append(state.gamma.get_fresh())


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


class LumpedReservoir(ReservoirComponent):
    """0-D lumped reservoir: doublet radial-flow impedance + Adams 2015 thermal depletion.

    Implements the DOUBLET well pattern.
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
    """Effective well diameter for impedance calculation (m) — the average
    of injection and production well diameters; set explicitly here for
    transparency.
    """
    well_pattern: WellPattern | None = Field(frozen=True)
    """Well pattern for analytic impedance solution — threaded from
    ``Layout.well_pattern`` (already validated/coerced there) via
    ``_build_components``'s ``layout_extras`` mechanism."""
    wp: WellPattern = WellPattern.Doublet
    """Resolved ``well_pattern`` object"""
    net_to_gross_ratio: float = Field(default=1.0, frozen=True)
    """Net-to-gross ratio for effective reservoir thickness (dimensionless)."""

    # ---- Derived constants (computed once by init(), never touched by solve()) ----
    # Deliberately NOT frozen — init() assigns these directly (plain floats,
    # not LockedState) once; see Component's class docstring for why fields
    # like this stay mutable rather than Field(frozen=True). Unlike p1/p2/p3
    # (now in `state` — see LumpedReservoirState), solve() never reassigns
    # these, so they have no need to live in `state` either.
    T_initial: float = 0.0
    """Un-depleted reservoir temperature = surface_T + gradient × depth (K)."""
    P_initial: float = 0.0
    """Un-depleted reservoir pressure = brine_density × g × reservoir_depth
    (Pa). Distinct from the fracking-safety ceiling
    (hydro_static_pressure × (1 + over_pressure_percentage/100))."""
    rock_volume: float = 0.0
    """Rock (non-fluid) volume = thickness × area × (1 − porosity) (m³)."""
    rock_C_v: float = 0.0  # noqa: N815
    """Volumetric heat capacity of rock = rock_density × rock_cp (J/(m³·K))."""

    # ---- Runtime state / history ----
    state: LumpedReservoirState = Field(default_factory=LumpedReservoirState)
    """Per-solve reservoir state; restored before every re-solve within a timestep. TODO(docs): drafted, review."""
    history: LumpedReservoirHistory = Field(default_factory=LumpedReservoirHistory)
    """Per-timestep record of the reservoir state. TODO(docs): drafted, review."""

    def init(self) -> None:
        """Pre-compute geometry and depletion coefficients from validated fields."""
        self.wp = self.well_pattern if self.well_pattern is not None else WellPattern.Doublet

        self.T_initial = self.common.surface_temperature + self.common.thermal_gradient * self.reservoir_depth
        self.P_initial = self.brine_density * self.gravity * self.reservoir_depth
        area = 0.5 * self.well_spacing**2  # DOUBLET area approximation
        volume = self.thickness * area
        fluid_volume = self.porosity * volume
        self.rock_volume = volume - fluid_volume
        self.rock_C_v = self.common.rock_density * self.common.rock_cp

    def _recompute_depletion_coeffs(self, m_dot: float, rho_fluid: float, cp_fluid: float) -> None:
        """Update ``state``'s thermal-depletion curve-fit coefficients p1/p2/p3 from current fluid properties.

        Writes straight to ``self.state.p1``/``p2``/``p3``. Called once per
        ``solve()`` call, so these values never persist stale across a
        within-timestep re-solve (see ``LumpedReservoirState.p1``'s
        docstring).

        Reference: [Adams, B.M. et al. (2015). A comparison of electric power
        output of CO2 Plume Geothermal (CPG) and brine geothermal systems for
        varying reservoir conditions. Applied Energy, 140, 365-377.](https://doi.org/10.1016/j.apenergy.2014.11.043)
        """
        b = self.thickness
        k_rock = self.common.rock_k
        rho_rock = self.common.rock_density
        cp_rock = self.common.rock_cp
        R = self.well_spacing

        coeff1 = b * k_rock * rho_fluid / m_dot / rho_rock / cp_rock
        coeff2 = k_rock * R * rho_fluid / rho_rock / cp_fluid / m_dot

        p1 = min(-890.97 * coeff1 - 1.30, -1.3)
        p2 = 0.4095 * math.exp(-0.7815 * p1)
        p3 = float(np.clip(1.0 - 1.4646 * math.exp(-377.3 * coeff2), 0.0, 1.0))
        self.state.p1.update(p1)
        self.state.p2.update(p2)
        self.state.p3.update(p3)

    def _depletion_curve(self, psi: float) -> float:
        """γ(ψ): fraction of (T₀ − T_inj) remaining in produced fluid.

        Reference: [Adams, B.M. et al. (2015). Applied Energy, 140, 365-377.](https://doi.org/10.1016/j.apenergy.2014.11.043)
        (same curve-fit as ``_recompute_depletion_coeffs`` above — see its
        docstring).
        """
        s = self.state
        p1, p2, p3 = s.p1.get_fresh(), s.p2.get_fresh(), s.p3.get_fresh()
        if psi <= -p1 / p2:
            return 1.0 - (1.0 - p3) * (1.0 - 0.5 * float(erfc(p2 * psi + p1)))
        else:
            C = 1.13
            return 1.0 - (1.0 - p3) * (1.0 - 0.5 * math.exp(-C * (p2 * psi + p1)))

    def solve(self, inlet: Stream) -> None:
        """Compute reservoir outlet (T, P) from doublet impedance and thermal depletion."""
        s = self.state

        # Capture previous-timestep outlet. The orchestrator already called
        # mark_all_stale() before this solve(), so T_outlet/P_outlet/
        # ever_solved are all stale, holding last cycle's value —
        # get_stale() is the canonical LockedState read for that (see
        # core/locked_state.py's lifecycle docstring), not get_fresh().
        # ever_solved is False on the very first call (never been solved,
        # even across a to_dict()/Workflow(cfg) reconstruction of an
        # unsolved base config — see its docstring for why this, not
        # s.T_outlet.is_stale()/s.P_outlet.is_stale(), is the reliable check
        # here) — fall back to T_initial / the hydrostatic guess.
        was_solved_before = s.ever_solved.get_stale()
        s.ever_solved.update(True)
        T_out_prev = self.T_initial if not was_solved_before else s.T_outlet.get_stale()
        P_out_prev = self.P_initial if not was_solved_before else s.P_outlet.get_stale()

        s.T_inlet.update(inlet.T.get_fresh())
        s.P_inlet.update(inlet.P.get_fresh())
        s.mass_rate.update(inlet.mass_rate.get_fresh())

        T_inj = s.T_inlet.get_fresh()
        P_in = s.P_inlet.get_fresh()
        mdot = s.mass_rate.get_fresh()

        s.T_reservoir_initial.update(self.T_initial)
        s.P_reservoir.update(self.P_initial)

        # Fluid properties: average of current inlet and previous-timestep outlet.
        fluid_name = self.common.fluid_name
        backend = self.common.coolprop_backend
        rho = 0.5 * (
            fluid_density(fluid_name, T_inj, P_in, backend)
            + fluid_density(fluid_name, T_out_prev, P_out_prev, backend)
        )
        mu = 0.5 * (
            fluid_viscosity(fluid_name, T_inj, P_in, backend)
            + fluid_viscosity(fluid_name, T_out_prev, P_out_prev, backend)
        )
        s.rho.update(rho)
        s.mu.update(mu)

        Z = self.wp.impedance(
            mu=mu,
            rho=rho,
            permeability=self.permeability,
            thickness=self.thickness,
            net_to_gross_ratio=self.net_to_gross_ratio,
            well_spacing=self.well_spacing,
            well_eff_diameter=self.well_eff_diameter,
        )

        dp = mdot * Z
        s.impedance.update(Z)
        s.delta_p_darcy.update(dp)
        P_out = P_in - dp
        s.P_outlet.update(P_out)

        # Thermal depletion (Adams 2015)
        dT = self.T_initial - T_inj
        h_in = fluid_enthalpy(fluid_name, T_inj, P_in, backend)
        s.h_inlet.update(h_in)

        h_prod_prev = fluid_enthalpy(fluid_name, T_out_prev, P_out_prev, backend)
        rho_avg = 0.5 * (
            fluid_density(fluid_name, T_inj, P_in, backend)
            + fluid_density(fluid_name, T_out_prev, P_out_prev, backend)
        )
        cp_avg = 0.5 * (
            fluid_cp(fluid_name, T_inj, P_in, backend) + fluid_cp(fluid_name, T_out_prev, P_out_prev, backend)
        )
        self._recompute_depletion_coeffs(mdot, rho_avg, cp_avg)

        s.energy_extraction_rate.update(mdot * (h_prod_prev - h_in))
        s.set_cumulative(self.dt_years)

        E_reservoir = self.rock_volume * self.rock_C_v * dT if dT > 0 else 1.0
        # psi = fractional energy extraction: cumulative energy pulled from the
        # reservoir so far, relative to the reservoir's total extractable
        # thermal energy at the current (T_initial - T_inj) driving delta.
        psi = s.energy_extracted.get_fresh() / E_reservoir if dT > 0 else 0.0
        gamma = self._depletion_curve(psi) if dT > 0 else 1.0
        s.psi.update(psi)
        s.gamma.update(gamma)

        T_out = T_inj + gamma * dT
        s.T_outlet.update(T_out)
        s.h_outlet.update(fluid_enthalpy(fluid_name, T_out, P_out, backend))

        self.outlet.T.update(T_out)
        self.outlet.P.update(P_out)
        self.outlet.mass_rate.update(mdot)
