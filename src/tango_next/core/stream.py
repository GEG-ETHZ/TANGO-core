"""Stream — fluid connection between tango_next components."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Stream:
    """Carries thermodynamic state and mass flow rate between components.

    SI units throughout: pressures in Pa, temperatures in K,
    enthalpies in J/kg, mass flow rates in kg/s.

    Phase 2 will integrate FluidState as a Pydantic model and add
    property-lookup helpers via CoolProp.
    """

    mass_rate: float = 0.0
    P: float = 0.0
    T: float = 0.0
    H: float = 0.0
    rho: float = 0.0
    mu: float = 0.0
    fluid_name: str = ""
    port: str = field(default="")
    """Port label: 'inlet', 'outlet', 'vapor_outlet', 'liquid_outlet', etc."""
