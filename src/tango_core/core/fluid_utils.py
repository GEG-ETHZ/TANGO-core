# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Shared hydraulic and fluid-property utilities for tango.

All functions are stateless, SI units throughout, and intentionally
single-purpose so they can be reused across well, reservoir, and surface
components without copy-pasting formulas.

Unit conventions
----------------
- Pressures   : Pa
- Temperatures: K
- Lengths     : m
- Mass flows  : kg/s
- Densities   : kg/m³
- Viscosities : Pa·s
- Velocities  : m/s
"""

from __future__ import annotations

import math

from tango_core.core.constants import EULER_CONSTANT_X2, GRAVITY
from tango_core.core.fluid_state import COOLPROP_BACKEND, FluidState

# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def pipe_area(diameter: float) -> float:
    """Cross-sectional flow area of a circular pipe (m²).

    Args:
        diameter: Inner diameter (m).

    """
    return math.pi * (diameter / 2.0) ** 2


# ---------------------------------------------------------------------------
# Hydraulics
# ---------------------------------------------------------------------------


def mean_velocity(mass_rate: float, rho: float, diameter: float) -> float:
    """Mean flow velocity in a full circular pipe (m/s).

    v = ṁ / (ρ · A)

    Args:
        mass_rate: Mass flow rate (kg/s).
        rho: Fluid density (kg/m³).
        diameter: Pipe inner diameter (m).

    """
    return mass_rate / (rho * pipe_area(diameter))


def reynolds_number(mass_rate: float, diameter: float, mu: float) -> float:
    """Reynolds number for internal pipe flow (dimensionless).

    Re = 4ṁ / (π·D·μ)

    Args:
        mass_rate: Mass flow rate (kg/s).
        diameter: Pipe inner diameter (m).
        mu: Dynamic viscosity (Pa·s).

    """
    return (4.0 * mass_rate) / (math.pi * diameter * mu)


def friction_factor_darcy(Re: float, diameter: float, roughness: float) -> float:
    """Darcy–Weisbach friction factor via Swamee–Jain explicit approximation.

    Laminar   (Re < 2300)       : f = 64 / Re
    Transition (2300 ≤ Re < 4000): laminar value used conservatively
    Turbulent (Re ≥ 4000)       : Swamee–Jain (explicit Colebrook–White)

    References:
    ----------
    Colebrook (1939) and Swamee & Jain (1976); see docs/SOURCES.md#colebrook1939
    and docs/SOURCES.md#swameejain1976. (Error < 3 % vs. iterative
    Colebrook–White for Re 5×10³–10⁸, ε/D 10⁻⁶–10⁻².)

    **Human review needed**: before using results that depend on this
    function for engineering decisions, verify against a trusted reference
    implementation or published table.

    TODO: implement proper laminar–turbulent blending in transition regime.

    Args:
        Re: Reynolds number (dimensionless).
        diameter: Pipe inner diameter (m).
        roughness: Absolute pipe-wall roughness (m).

    """
    if Re <= 0.0:
        return 64.0
    if Re < 4000.0:
        # Laminar / transition: f = 64/Re (conservative in transition)
        return 64.0 / Re
    # Turbulent: Swamee–Jain explicit approximation to Colebrook–White
    rel_rough = roughness / diameter
    return 0.25 / (math.log10(rel_rough / 3.7 + 5.74 / Re**0.9)) ** 2


def friction_factor_haaland(Re: float, diameter: float, roughness: float) -> float:
    """Darcy–Weisbach friction factor via the Haaland explicit approximation.

    1/sqrt(f) = -1.8 log10[ (r/3.7)^1.11 + 6.9/Re ],  r = roughness / diameter

    Use this (not ``friction_factor_darcy``'s Swamee–Jain approximation)
    for the discretized wellbore models, which are pinned to this variant.

    Reference:
    ---------
    Haaland (1983); see docs/SOURCES.md#haaland1983.

    Args:
        Re: Reynolds number (dimensionless).
        diameter: Pipe inner diameter (m).
        roughness: Absolute pipe-wall roughness (m).

    """
    r = roughness / diameter
    return (-1.8 * math.log10((r / 3.7) ** 1.11 + 6.9 / Re)) ** -2.0


def pressure_drop_friction(
    friction_factor: float,
    length: float,
    diameter: float,
    rho: float,
    velocity: float,
) -> float:
    """Frictional pressure loss via Darcy–Weisbach (Pa), always ≥ 0.

    ΔP_f = f · (L/D) · (ρ·v²/2)

    Args:
        friction_factor: Darcy friction factor (dimensionless).
        length: Pipe segment length (m).
        diameter: Pipe inner diameter (m).
        rho: Fluid density (kg/m³).
        velocity: Mean flow velocity (m/s).

    """
    return friction_factor * (length / diameter) * (rho * velocity**2 / 2.0)


def hydrostatic_pressure(rho: float, delta_depth: float, gravity: float = GRAVITY) -> float:
    """Hydrostatic pressure difference over a vertical depth interval (Pa).

    ΔP_hydro = ρ · g · Δdepth    (positive for downward Δdepth)

    This is a *change* in depth, not an absolute depth from surface.
    Pass the well-segment length for a single-segment wellbore model.

    Args:
        rho: Fluid density (kg/m³).
        delta_depth: Vertical depth interval (m), positive downward.
        gravity: Gravitational acceleration (m/s²) — defaults to
            core/constants.py's GRAVITY; pass the calling component's own
            `gravity` field to respect a per-component override.

    """
    return rho * gravity * delta_depth


def heat_loss_zhang_2011(dL: float, rock_k: float, t_d: float, delta_T: float) -> float:
    r"""Transient conductive heat loss for one wellbore cell (W).

    Q_loss = 2π · dL · k_rock · β(t_d) · ΔT

    where β is a dimensionless heat-transfer-efficiency coefficient for
    the surrounding rock — large at small t_d (only the rock immediately
    at the wellbore wall has been thermally disturbed, so it still
    conducts heat to/from the wellbore readily) and shrinking as t_d
    grows (the thermally-disturbed zone widens, so further exchange must
    conduct through progressively more already-equilibrated, effectively
    more insulating rock), based on dimensionless time t_d:

        β = (π·t_d)^-0.5 + 0.5 - 0.25·(t_d/π)^0.5 + 0.125·t_d,   t_d ≤ 2.8
        β = 2 / (ln(4·t_d) - 2γ) - 2γ / (ln(4·t_d) - 2γ)²,  t_d > 2.8

    where γ is the Euler-Mascheroni constant (``core/constants.py``'s
    ``EULER_CONSTANT`` — ``EULER_CONSTANT_X2`` is ``2γ``). (Zhang et al.'s
    own Eq. 2 shows ``γ``, not ``2γ``, in the second term's numerator —
    not a discrepancy: they keep a ``2k/r₀`` prefactor outside their
    ``f2``, whereas β here already folds that factor of 2 in, since
    ``Q_loss = 2π·k_rock·β·ΔT`` applies it directly. Algebraically
    identical, just factored differently.)

    References:
    ----------
    β and its two-regime piecewise form (Eqs. 1–2) originate with Zhang et al.
    (2011); see docs/SOURCES.md#zhang2011. This implementation's exact form
    matches Eqs. S65–S66 of Adams et al. (2021), Supplemental Information §S6;
    see docs/SOURCES.md#adams2021gengeo.

    Args:
        dL: Axial cell length (m).
        rock_k: Surrounding rock thermal conductivity (W/(m·K)).
        t_d: Dimensionless time (dimensionless).
        delta_T: Temperature difference, fluid minus far-field rock (K).

    """
    if t_d <= 2.8:
        beta = (math.pi * t_d) ** -0.5 + 0.5 - 0.25 * (t_d / math.pi) ** 0.5 + 0.125 * t_d
    else:
        ln_term = math.log(4.0 * t_d) - EULER_CONSTANT_X2
        beta = 2.0 / ln_term - EULER_CONSTANT_X2 / ln_term**2
    return 2.0 * dL * math.pi * rock_k * beta * delta_T


# ---------------------------------------------------------------------------
# Fluid properties via CoolProp
# ---------------------------------------------------------------------------
#
# Every lookup takes ``fluid_name`` explicitly and goes through FluidState
# (core/fluid_state.py) — the same CoolProp wrapper the numerical well model
# uses — rather than assuming water. These four used to be hardcoded against
# a single module-level "Water" AbstractState regardless of what fluid a
# component's Common.fluid_name actually declared; that silently computed
# wrong properties for any non-water fluid (see docs/tango_tasks.md's
# fluid-identity review). Callers must pass ``common.fluid_name``, not a
# literal fluid string, so every component using a shared Common instance
# stays consistent by construction.


def fluid_density(fluid_name: str, T: float, P: float, backend: str = COOLPROP_BACKEND) -> float:
    """Fluid density (kg/m³) via CoolProp.

    Args:
        fluid_name: CoolProp fluid name (e.g. ``"Water"``, ``"CO2"``).
        T: Temperature (K).
        P: Pressure (Pa).
        backend: CoolProp backend (see ``core/fluid_state.py``'s
            ``CoolPropBackend`` — pass ``common.coolprop_backend``).

    """
    return FluidState.with_PT(fluid_name, P, T, backend).rho


def fluid_viscosity(fluid_name: str, T: float, P: float, backend: str = COOLPROP_BACKEND) -> float:
    """Fluid dynamic viscosity (Pa·s) via CoolProp.

    Args:
        fluid_name: CoolProp fluid name (e.g. ``"Water"``, ``"CO2"``).
        T: Temperature (K).
        P: Pressure (Pa).
        backend: CoolProp backend (see ``core/fluid_state.py``'s
            ``CoolPropBackend`` — pass ``common.coolprop_backend``).

    """
    return FluidState.with_PT(fluid_name, P, T, backend).mu


def fluid_enthalpy(fluid_name: str, T: float, P: float, backend: str = COOLPROP_BACKEND) -> float:
    """Fluid specific enthalpy (J/kg) via CoolProp.

    Args:
        fluid_name: CoolProp fluid name (e.g. ``"Water"``, ``"CO2"``).
        T: Temperature (K).
        P: Pressure (Pa).
        backend: CoolProp backend (see ``core/fluid_state.py``'s
            ``CoolPropBackend`` — pass ``common.coolprop_backend``).

    """
    return FluidState.with_PT(fluid_name, P, T, backend).H


def fluid_cp(fluid_name: str, T: float, P: float, backend: str = COOLPROP_BACKEND) -> float:
    """Fluid isobaric specific heat capacity (J/(kg·K)) via CoolProp.

    Args:
        fluid_name: CoolProp fluid name (e.g. ``"Water"``, ``"CO2"``).
        T: Temperature (K).
        P: Pressure (Pa).
        backend: CoolProp backend (see ``core/fluid_state.py``'s
            ``CoolPropBackend`` — pass ``common.coolprop_backend``).

    """
    return FluidState.with_PT(fluid_name, P, T, backend).cp


# ---------------------------------------------------------------------------
# Fracking thresholds
# ---------------------------------------------------------------------------
#
# Two independent mechanisms — see InjectionPolicy's class docstring
# (core/policies.py) for the full physical explanation. These two functions
# each compute one side's threshold; callers (SystemBCIteration) compare the
# actual mass rate / wellhead pressure against them and raise
# FrackingViolationError on violation, rather than silently correcting —
# see FrackingViolationError's docstring for why.


def target_reservoir_pressure(hydro_static_pressure: float, over_pressure_percentage: float) -> float:
    """Pressure-induced fracking threshold at the reservoir inlet (Pa).

    target_reservoir_P = hydro_static_pressure × (1 + over_pressure_percentage / 100)

    Args:
        hydro_static_pressure: Nominal hydrostatic pressure at reservoir
            depth (Pa) — ``ReservoirComponent.hydro_static_pressure``.
        over_pressure_percentage: Allowed over-pressure as a percentage of
            hydrostatic pressure (%) — ``ReservoirComponent.over_pressure_percentage``.

    """
    return hydro_static_pressure * (1.0 + over_pressure_percentage / 100.0)


def fracking_flow(
    thickness: float,
    permeability: float,
    hydro_static_pressure: float,
    over_pressure_percentage: float,
    well_spacing: float,
    wellbore_diameter: float,
    mu: float,
    rho: float,
) -> float:
    """Flow-induced fracking threshold mass rate (kg/s).

    q = 2·π·h·k·ΔP / (μ · ln(r_res / r_well))     (volumetric flow, m³/s)
    ΔP = over_pressure_percentage / 100 × hydro_static_pressure
    r_res  = well_spacing / 2                     (effective reservoir radius)
    r_well = wellbore_diameter / 2                (wellbore radius)
    m  = ρ · q                                    (mass flow, kg/s)

    Args:
        thickness: Reservoir thickness (m) — ``ReservoirComponent.thickness``.
        permeability: Reservoir permeability (m²) —
            ``ReservoirComponent.permeability``.
        hydro_static_pressure: Nominal hydrostatic pressure at reservoir
            depth (Pa) — ``ReservoirComponent.hydro_static_pressure``.
        over_pressure_percentage: Allowed over-pressure as a percentage of
            hydrostatic pressure (%) —
            ``ReservoirComponent.over_pressure_percentage``.
        well_spacing: Injector-to-producer spacing (m) — half of this is
            used as the effective reservoir radius ``re``.
        wellbore_diameter: Injection well diameter (m) —
            ``WellComponent.diameter``.
        mu: Fluid dynamic viscosity (Pa·s) at the injection well outlet —
            see ``fluid_viscosity`` above.
        rho: Fluid density (kg/m³) at the injection well outlet — see
            ``fluid_density`` above.

    """
    r_res = well_spacing / 2.0
    r_well = wellbore_diameter / 2.0
    delta_p = over_pressure_percentage / 100.0 * hydro_static_pressure
    q = (2 * math.pi * thickness * permeability * delta_p) / (mu * math.log(r_res / r_well))
    return rho * q
