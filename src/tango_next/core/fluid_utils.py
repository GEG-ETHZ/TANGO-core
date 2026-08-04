"""Shared hydraulic and fluid-property utilities for tango_next.

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

from tango_next.core.constants import GRAVITY
from tango_next.core.fluid_state import FluidState

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
    Colebrook, C.F. (1939). Turbulent flow in pipes, with particular reference
    to the transition region between smooth and rough pipe laws.
    J. Institution of Civil Engineers, 11(4), 133–156.
    https://doi.org/10.1680/ijoti.1939.13150

    Swamee, P.K. & Jain, A.K. (1976). Explicit equations for pipe-flow problems.
    J. Hydraulics Division ASCE, 102(5), 657–664.
    https://doi.org/10.1061/JYCEAJ.0004542
    (Error < 3 % vs. iterative Colebrook–White for Re 5×10³–10⁸, ε/D 10⁻⁶–10⁻².)

    **Human review needed**: this formula is not present in the original
    ``src/tango/`` codebase.  Before using results that depend on this
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

    This matches ``src/tango/units/native/well/base.py::WellUnitNative._compute_friction_factor``
    exactly (same formula, same inputs) — use this (not ``friction_factor_darcy``'s
    Swamee–Jain approximation) wherever parity with the original implementation matters,
    e.g. the discretized wellbore models.

    Reference:
    ---------
    Haaland, S.E. (1983). Simple and explicit formulas for the friction factor in
    turbulent pipe flow. J. Fluids Engineering, 105(1), 89-90.
    https://doi.org/10.1115/1.3240948

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


def heat_loss_adams_2015(dL: float, rock_k: float, t_d: float, delta_T: float) -> float:
    r"""Adams et al. (2015) transient conductive heat loss for one wellbore cell (W).

    Q_loss = 2π · dL · k_rock · β(t_d) · ΔT

    where β is a dimensionless coefficient based on dimensionless time t_d:

        β = (π·t_d)^-0.5 + 0.5 - 0.25·(t_d/π)^0.5 + 0.125·t_d,   t_d ≤ 2.8
        β = 2 / (ln(4·t_d) - 1.16) - 1.16 / (ln(4·t_d) - 1.16)²,  t_d > 2.8

    Matches ``src/tango/units/native/well/base.py::WellUnitNative._compute_Q_loss``
    exactly (same beta correlation, same formula).

    Reference:
    ---------
    Adams, B.M. et al. (2015). A comparison of electric power output of CO2
    Plume Geothermal (CPG) and brine geothermal systems for varying reservoir
    conditions. Applied Energy, 140, 365-377.
    https://doi.org/10.1016/j.apenergy.2014.11.043

    Args:
        dL: Axial cell length (m).
        rock_k: Surrounding rock thermal conductivity (W/(m·K)).
        t_d: Dimensionless time (dimensionless).
        delta_T: Temperature difference, fluid minus far-field rock (K).

    """
    if t_d <= 2.8:
        beta = (math.pi * t_d) ** -0.5 + 0.5 - 0.25 * (t_d / math.pi) ** 0.5 + 0.125 * t_d
    else:
        ln_term = math.log(4.0 * t_d) - 1.16
        beta = 2.0 / ln_term - 1.16 / ln_term**2
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
# wrong properties for any non-water fluid (see docs/tango_next_tasks.md's
# fluid-identity review). Callers must pass ``common.fluid_name``, not a
# literal fluid string, so every component using a shared Common instance
# stays consistent by construction.


def fluid_density(fluid_name: str, T: float, P: float) -> float:
    """Fluid density (kg/m³) via CoolProp.

    Args:
        fluid_name: CoolProp fluid name (e.g. ``"Water"``, ``"CO2"``).
        T: Temperature (K).
        P: Pressure (Pa).

    """
    return FluidState.with_PT(fluid_name, P, T).rho


def fluid_viscosity(fluid_name: str, T: float, P: float) -> float:
    """Fluid dynamic viscosity (Pa·s) via CoolProp.

    Args:
        fluid_name: CoolProp fluid name (e.g. ``"Water"``, ``"CO2"``).
        T: Temperature (K).
        P: Pressure (Pa).

    """
    return FluidState.with_PT(fluid_name, P, T).mu


def fluid_enthalpy(fluid_name: str, T: float, P: float) -> float:
    """Fluid specific enthalpy (J/kg) via CoolProp.

    Args:
        fluid_name: CoolProp fluid name (e.g. ``"Water"``, ``"CO2"``).
        T: Temperature (K).
        P: Pressure (Pa).

    """
    return FluidState.with_PT(fluid_name, P, T).H


def fluid_cp(fluid_name: str, T: float, P: float) -> float:
    """Fluid isobaric specific heat capacity (J/(kg·K)) via CoolProp.

    Args:
        fluid_name: CoolProp fluid name (e.g. ``"Water"``, ``"CO2"``).
        T: Temperature (K).
        P: Pressure (Pa).

    """
    return FluidState.with_PT(fluid_name, P, T).cp
