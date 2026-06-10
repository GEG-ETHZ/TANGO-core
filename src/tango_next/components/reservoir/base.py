"""Abstract base for reservoir components in tango_next."""

from __future__ import annotations

from abc import abstractmethod

from pydantic import ConfigDict

from tango_next.core.component import Component, ComponentSpec


class ReservoirSpec(ComponentSpec):
    """Base specification for all reservoir components.

    Concrete implementations may represent: native 1D Darcy model,
    or external-simulator adapters (CMG, MOOSE, TOUGH2).
    """

    model_config = ConfigDict(frozen=True)

    prev: int
    next: int
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


class ReservoirComponent(Component):
    """Abstract base for all reservoir components.

    External simulators (CMG, MOOSE) implement this interface as adapters.
    The native implementation assumes incompressible 1D Darcy flow;
    external simulators may relax this assumption during transients.
    """

    @property
    @abstractmethod
    def spec(self) -> ReservoirSpec:
        """The typed reservoir specification."""
        ...

    @abstractmethod
    def solve(self) -> None:
        """Compute reservoir outlet state from injection inlet state."""
        ...
