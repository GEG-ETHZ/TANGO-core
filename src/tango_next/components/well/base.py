"""Abstract base for well components in tango_next."""

from __future__ import annotations

from abc import abstractmethod

from pydantic import ConfigDict

from tango_next.core.component import Component, ComponentSpec


class WellSpec(ComponentSpec):
    """Base specification for all wellbore components."""

    model_config = ConfigDict(frozen=True)

    prev: int
    next: int
    well_length: float
    """Total wellbore length (m)."""
    diameter: float
    """Wellbore inner diameter (m)."""
    pipe_roughness: float
    """Absolute pipe wall roughness for Darcy-Weisbach friction (m)."""


class WellComponent(Component):
    """Abstract base for all wellbore components (injection and production).

    Concrete implementations: InjectionWell, ProductionWell,
    ProductionWellPump (Phase 3+).
    """

    @property
    @abstractmethod
    def spec(self) -> WellSpec:
        """The typed well specification."""
        ...

    @abstractmethod
    def solve(self) -> None:
        """Compute outlet fluid state from inlet state through the wellbore."""
        ...
