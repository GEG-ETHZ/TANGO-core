"""Stream — fluid connection between tango_next components."""

from __future__ import annotations

from pydantic import BaseModel


class Stream(BaseModel):
    """Carries thermodynamic state and mass flow rate between components.

    SI units throughout: pressures in Pa, temperatures in K,
    enthalpies in J/kg, mass flow rates in kg/s.

    Deliberately does NOT carry a ``fluid_name`` (or any other fluid-identity
    field): every component that needs one already holds a reference to the
    Workflow's single shared ``Common`` instance (``core/specs.py``), which
    is where ``fluid_name`` lives. Duplicating it here as per-timestep,
    per-stream state would just be a second, unvalidated copy that could
    drift from ``Common`` — exactly the risk this design avoids (see
    docs/tango_next_tasks.md's fluid-identity review). If a future component
    needs to represent a genuine fluid *boundary* (e.g. a secondary/ORC loop
    physically separate from the geofluid loop), that calls for an explicit
    typed marker on the boundary component, not a field here.

    A future update will integrate FluidState as a Pydantic model and add
    property-lookup helpers via CoolProp.
    """

    mass_rate: float = 0.0
    P: float = 0.0
    T: float = 0.0
    H: float = 0.0
    rho: float = 0.0
    mu: float = 0.0
    port: str = ""
    """Port label: 'inlet', 'outlet', 'vapor_outlet', 'liquid_outlet', etc."""
