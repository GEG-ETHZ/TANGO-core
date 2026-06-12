"""Component ABC and base ComponentSpec for tango_next."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict

from tango_next.core.stream import Stream


class ComponentSpec(BaseModel):
    """Base specification for all tango_next components.

    Subclasses add component-specific fields. All specs are frozen (immutable)
    after construction — mutation goes through the orchestrator, not the spec.
    """

    model_config = ConfigDict(frozen=True)

    component_idx: int
    """Circuit index. 0 is reserved for the BC checkpoint (surface component)."""


class Component(ABC):
    """Abstract base for all tango_next physical components.

    Each component owns its typed spec and implements solve() to compute
    outlet state from inlet state. Stream wiring is the orchestrator's job.

    The orchestrator sets ``inlet`` before calling ``solve()``;
    ``solve()`` reads ``inlet`` and writes ``outlet``.
    """

    def __init__(self) -> None:
        """Initialise inlet and outlet streams to default (zero) state."""
        self.inlet: Stream = Stream()
        self.outlet: Stream = Stream()

    @property
    @abstractmethod
    def spec(self) -> ComponentSpec:
        """The typed, validated specification for this component."""
        ...

    @abstractmethod
    def solve(self) -> None:
        """Compute outlet stream state from the current inlet stream state."""
        ...

    @property
    def component_idx(self) -> int:
        """Shortcut for spec.component_idx."""
        return self.spec.component_idx
