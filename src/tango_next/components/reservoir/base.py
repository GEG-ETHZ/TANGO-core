"""Abstract base for reservoir components in tango_next."""

from __future__ import annotations

from abc import abstractmethod

from pydantic import Field

from tango_next.core.component import Component
from tango_next.core.constants import GRAVITY


class ReservoirComponent(Component):
    """Abstract base for all reservoir components.

    External simulators (CMG, MOOSE) implement this interface as adapters.
    The native implementation assumes incompressible 1D Darcy flow;
    external simulators may relax this assumption during transients.
    """

    prev: int = Field(frozen=True)
    """Circuit index of the upstream component."""
    next: int = Field(frozen=True)
    """Circuit index of the downstream component."""
    reservoir_depth: float = Field(frozen=True)
    """Depth of the reservoir mid-point (m)."""
    thickness: float = Field(frozen=True)
    """Reservoir thickness (m)."""
    permeability: float = Field(frozen=True)
    """Reservoir permeability (m²)."""
    porosity: float = Field(frozen=True)
    """Reservoir porosity (dimensionless)."""
    hydro_static_pressure: float = Field(frozen=True)
    """Hydrostatic pressure at reservoir depth (Pa). User-supplied nominal
    value used only for the fracing-safety ceiling (BC-iteration target
    pressure) — NOT the reservoir's own initial/undepleted pressure; see
    ``brine_density`` below for that."""
    over_pressure_percentage: float = Field(frozen=True)
    """Over-pressure as a percentage of hydrostatic pressure (%). Combines
    with ``hydro_static_pressure`` for the fracing-safety ceiling only."""
    brine_density: float = Field(default=1000.0, frozen=True)
    """Brine density (kg/m³), used to compute the reservoir's true
    initial/undepleted pressure (``brine_density × g × reservoir_depth``) —
    matches ``src/tango/``'s ``ReservoirUnitNative._compute_initial_pressure()``.
    Deliberately a physically-derived value, distinct from
    ``hydro_static_pressure`` (a user-supplied nominal value used only for
    the fracing ceiling) — conflating the two was a real bug, see
    ``docs/tango_next_tasks.md``."""
    gravity: float = Field(default=GRAVITY, frozen=True)
    """Gravitational acceleration (m/s²) — defaults to core/constants.py's
    GRAVITY, overridable per reservoir since gravity varies regionally."""

    @abstractmethod
    def solve(self) -> None:
        """Compute reservoir outlet state from injection inlet state."""
