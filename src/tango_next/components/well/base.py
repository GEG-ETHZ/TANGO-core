"""Abstract base for well components in tango_next."""

from __future__ import annotations

from abc import abstractmethod

from pydantic import Field

from tango_next.core.component import Component
from tango_next.core.constants import GRAVITY


class WellComponent(Component):
    """Abstract base for all wellbore components (injection and production).

    Concrete implementations: LumpedInjectionWell, NumericalInjectionWell,
    LumpedProductionWell, NumericalProductionWell, LumpedProductionWellWithPump.

    All wellbore geometry fields live here — subclasses add fluid/physics fields.
    """

    prev: int = Field(frozen=True)
    """Circuit index of the upstream component."""
    next: int = Field(frozen=True)
    """Circuit index of the downstream component."""
    well_length: float = Field(frozen=True)
    """Total wellbore length from wellhead to bottom (m)."""
    diameter: float = Field(frozen=True)
    """Wellbore inner diameter (m)."""
    pipe_roughness: float = Field(frozen=True)
    """Absolute pipe wall roughness for Darcy-Weisbach friction (m)."""
    gravity: float = Field(default=GRAVITY, frozen=True)
    """Gravitational acceleration (m/s²) — defaults to core/constants.py's
    GRAVITY, overridable per well since gravity varies regionally."""

    @abstractmethod
    def solve(self) -> None:
        """Compute outlet fluid state from inlet state through the wellbore."""
