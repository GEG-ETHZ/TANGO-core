"""Abstract base for well components in tango, and the well sections the economic model costs."""

from __future__ import annotations

import enum
from abc import abstractmethod
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import Field, PositiveFloat

from tango_core.core.component import FlowComponent
from tango_core.core.constants import GRAVITY
from tango_core.core.stream import Stream

HORIZONTAL_ANGLE_DEG: float = 90.0
"""``angle_from_vert_deg`` of a horizontal well (0 = straight down, 180 =
straight up -- see components/well/numerical.py's module docstring)."""


class WellRole(enum.StrEnum):
    """What a drilled well section is for, which decides how the economic model costs it."""

    INJECTION = "injection"
    HORIZONTAL = "horizontal"
    """A horizontal section (e.g. an AGS loop's lateral): a separate drilling
    operation, costed on its own."""
    PRODUCTION = "production"
    """A vertical production section. Several of them may make up one physical
    wellbore (e.g. a lower section plus an upper one carrying a pump)."""


@dataclass(frozen=True)
class WellSection:
    """One drilled well section, as the economic model sees it."""

    role: WellRole
    well_length: float
    """Drilled length (m)."""
    diameter: float
    """Inner diameter (m)."""
    pump_power_watts_history: tuple[float, ...] = ()
    """Downhole pump power draw (W) per recorded timestep; empty for a section without a pump."""


@runtime_checkable
class HasWellSections(Protocol):
    """A component that contains drilled well sections."""

    def well_sections(self) -> list[WellSection]:
        """Return this component's well sections, in flow order."""
        ...


class WellComponent(FlowComponent):
    """Abstract base for all wellbore components (injection and production).

    Concrete implementations: LumpedInjectionWell, NumericalInjectionWell,
    LumpedProductionWell, NumericalProductionWell, LumpedProductionWellWithPump.

    All wellbore geometry fields live here — subclasses add fluid/physics fields.
    """

    prev: int = Field(frozen=True)
    """Circuit index of the upstream component."""
    next: int = Field(frozen=True)
    """Circuit index of the downstream component."""
    well_length: PositiveFloat = Field(frozen=True)
    """Total wellbore length from wellhead to bottom (m)."""
    diameter: PositiveFloat = Field(frozen=True)
    """Wellbore inner diameter (m)."""
    pipe_roughness: PositiveFloat = Field(frozen=True)
    """Absolute pipe wall roughness for Darcy-Weisbach friction (m)."""
    gravity: PositiveFloat = Field(default=GRAVITY, frozen=True)
    """Gravitational acceleration (m/s²) — defaults to core/constants.py's
    GRAVITY, overridable per well since gravity varies regionally."""

    @abstractmethod
    def solve(self, inlet: Stream) -> Stream:
        """Compute and return the outlet fluid state from the inlet state through the wellbore."""

    def well_sections(self) -> list[WellSection]:
        """Return this well as a single section.

        The well at the circuit entry (``component_idx == 0``) is the
        injection well. Any other well is horizontal if its
        ``angle_from_vert_deg`` (``NumericalWell`` only) is 90, and a
        vertical production section otherwise.
        """
        if self.component_idx == 0:
            role = WellRole.INJECTION
        elif getattr(self, "angle_from_vert_deg", None) == HORIZONTAL_ANGLE_DEG:
            role = WellRole.HORIZONTAL
        else:
            role = WellRole.PRODUCTION
        history = getattr(self, "history", None)
        pump_history: list[float] = getattr(history, "pump_power_watts", [])
        return [WellSection(role, self.well_length, self.diameter, tuple(pump_history))]
