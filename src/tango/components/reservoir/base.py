"""Abstract base for reservoir components in tango."""

from __future__ import annotations

from abc import abstractmethod

from pydantic import Field, PositiveFloat

from tango.core.component import FlowComponent
from tango.core.constants import GRAVITY
from tango.core.stream import Stream


class ReservoirComponent(FlowComponent):
    """Abstract base for all reservoir components.

    External simulators (CMG, MOOSE) are meant to implement this interface
    as adapters; none exists yet, so ``LumpedReservoir`` is the only
    implementation. The native implementation assumes incompressible 1D
    Darcy flow;
    external simulators may relax this assumption during transients.
    """

    prev: int = Field(frozen=True)
    """Circuit index of the upstream component."""
    next: int = Field(frozen=True)
    """Circuit index of the downstream component."""
    reservoir_depth: PositiveFloat = Field(frozen=True)
    """Depth of the reservoir mid-point (m)."""
    thickness: PositiveFloat = Field(frozen=True)
    """Reservoir thickness (m)."""
    permeability: PositiveFloat = Field(frozen=True)
    """Reservoir permeability (m²)."""
    porosity: PositiveFloat = Field(frozen=True)
    """Reservoir porosity (dimensionless)."""
    hydro_static_pressure: PositiveFloat = Field(frozen=True)
    """Hydrostatic pressure at reservoir depth (Pa). User-supplied nominal
    value used only for the fracking-safety ceiling (BC-iteration target
    pressure) — NOT the reservoir's own initial/undepleted pressure; see
    ``brine_density`` below for that."""
    over_pressure_percentage: PositiveFloat = Field(frozen=True)
    """Over-pressure as a percentage of hydrostatic pressure (%). Combines
    with ``hydro_static_pressure`` for the fracking-safety ceiling only."""
    brine_density: PositiveFloat = Field(default=1000.0, frozen=True)
    """Brine density (kg/m³), used to compute the reservoir's true
    initial/undepleted pressure (``brine_density × g × reservoir_depth``).
    Deliberately a physically-derived value, distinct from
    ``hydro_static_pressure`` (a user-supplied nominal value used only for
    the fracking ceiling) — conflating the two was a real bug, see
    ``docs/tango_tasks.md``."""
    gravity: PositiveFloat = Field(default=GRAVITY, frozen=True)
    """Gravitational acceleration (m/s²) — defaults to core/constants.py's
    GRAVITY, overridable per reservoir since gravity varies regionally."""

    @abstractmethod
    def solve(self, inlet: Stream) -> Stream:
        """Compute and return the reservoir outlet state from the injection inlet state."""
