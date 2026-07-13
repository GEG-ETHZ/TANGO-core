"""Init Protocol for post-deserialization initialization."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Init(Protocol):
    """Protocol for objects that require post-deserialization initialization.

    ``Component.from_config()`` calls ``self.init()`` after constructing any
    object that implements this protocol, allowing derived fields to be computed
    from the validated input state.  Modeled on the Init trait from fastsim-core.
    """

    def init(self) -> None:
        """Initialize computed fields after deserialization."""
        ...
