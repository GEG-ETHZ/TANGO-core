"""SerdeAPI mixin — format-agnostic file I/O for tango_next objects.

Phase 1 stub: the interface is declared but not yet implemented.
Full implementation planned for Phase 2 (modeled on the fastsim-core SerdeAPI trait).
Format dispatch: .yaml → YAML, .json → JSON, .msgpack → MessagePack.
After deserialization, self.init() is called if the object implements Init.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar


class SerdeAPI:
    """Mixin providing to_file / from_file / to_str / from_str with format dispatch."""

    supported_formats: ClassVar[tuple[str, ...]] = (".yaml", ".json", ".msgpack")

    def to_file(self, path: Path | str) -> None:
        """Serialize this object to a file, dispatching on file extension."""
        raise NotImplementedError

    @classmethod
    def from_file(cls, path: Path | str) -> SerdeAPI:
        """Deserialize an instance from a file."""
        raise NotImplementedError

    def to_str(self, fmt: str) -> str:
        """Serialize this object to a string in the given format."""
        raise NotImplementedError

    @classmethod
    def from_str(cls, s: str, fmt: str) -> SerdeAPI:
        """Deserialize an instance from a string."""
        raise NotImplementedError
