"""Abstract base for well components in tango_next."""

from __future__ import annotations

from abc import abstractmethod

from tango_next.core.component import Component


class WellComponent(Component):
    """Abstract base for all wellbore components (injection and production).

    Concrete implementations: LumpedInjectionWell, NumericalInjectionWell,
    LumpedProductionWell, NumericalProductionWell, LumpedProductionWellPump.

    All wellbore geometry fields live here — subclasses add fluid/physics fields.
    """

    prev: int
    """Circuit index of the upstream component."""
    next: int
    """Circuit index of the downstream component."""
    well_length: float
    """Total wellbore length from wellhead to bottom (m)."""
    diameter: float
    """Wellbore inner diameter (m)."""
    pipe_roughness: float
    """Absolute pipe wall roughness for Darcy-Weisbach friction (m)."""

    @abstractmethod
    def solve(self) -> None:
        """Compute outlet fluid state from inlet state through the wellbore."""
