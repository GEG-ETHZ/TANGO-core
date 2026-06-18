"""Abstract base for reservoir components in tango_next."""

from __future__ import annotations

from abc import abstractmethod

from tango_next.core.component import Component


class ReservoirComponent(Component):
    """Abstract base for all reservoir components.

    External simulators (CMG, MOOSE) implement this interface as adapters.
    The native implementation assumes incompressible 1D Darcy flow;
    external simulators may relax this assumption during transients.
    """

    prev: int
    """Circuit index of the upstream component."""
    next: int
    """Circuit index of the downstream component."""
    reservoir_depth: float
    """Depth of the reservoir mid-point (m)."""
    thickness: float
    """Reservoir thickness (m)."""
    permeability: float
    """Reservoir permeability (m²)."""
    porosity: float
    """Reservoir porosity (dimensionless)."""
    hydro_static_pressure: float
    """Hydrostatic pressure at reservoir depth (Pa)."""
    over_pressure_percentage: float
    """Over-pressure as a percentage of hydrostatic pressure (%)."""

    @abstractmethod
    def solve(self) -> None:
        """Compute reservoir outlet state from injection inlet state."""
