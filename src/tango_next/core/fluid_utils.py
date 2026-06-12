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
    Turbulent (Re ≥ 4000)       : Swamee–Jain (explicit Colebrook–White)
    Transition (2300 ≤ Re < 4000): laminar value used conservatively.

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

    TODO (Phase 2): implement proper laminar–turbulent blending in transition regime.

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


def hydrostatic_pressure(rho: float, delta_depth: float) -> float:
    """Hydrostatic pressure difference over a vertical depth interval (Pa).

    ΔP_hydro = ρ · g · Δdepth    (positive for downward Δdepth)

    This is a *change* in depth, not an absolute depth from surface.
    Pass the well-segment length for a single-segment wellbore model.

    Args:
        rho: Fluid density (kg/m³).
        delta_depth: Vertical depth interval (m), positive downward.

    """
    return rho * GRAVITY * delta_depth


# ---------------------------------------------------------------------------
# Simplified fluid property stubs
# Replace each with CoolProp lookups in Phase 2.
# ---------------------------------------------------------------------------


def water_density(T: float, P: float) -> float:  # noqa: ARG001
    """Liquid water density (kg/m³) — simplified constant.

    TODO (Phase 2): CoolProp.PropsSI("D", "T", T, "P", P, "Water")

    Args:
        T: Temperature (K).
        P: Pressure (Pa).

    """
    return 1000.0


def water_viscosity(T: float, P: float) -> float:  # noqa: ARG001
    """Liquid water dynamic viscosity (Pa·s) — simplified constant.

    TODO (Phase 2): CoolProp.PropsSI("V", "T", T, "P", P, "Water")

    Args:
        T: Temperature (K).
        P: Pressure (Pa).

    """
    return 1.0e-3
