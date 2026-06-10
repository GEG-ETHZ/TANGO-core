"""Init Protocol for post-deserialization initialization."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Init(Protocol):
    """Protocol for objects that require post-deserialization initialization.

    SerdeAPI calls self.init() after deserializing any object that implements
    this protocol, allowing computed fields to be set up from the loaded state.
    Modeled on the Init trait from fastsim-core.
    """

    def init(self) -> None:
        """Initialize computed fields after deserialization."""
        ...
