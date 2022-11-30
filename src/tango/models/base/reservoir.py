from abc import ABC
from dataclasses import dataclass
from tango.core import FluidState
from tango.model import ModelState


class ReservoirSpecs(ABC):
    """Implements the common interface for classes providing reservoir specifications."""
    pass


@dataclass
class ReservoirState(ABC):
    """Implements the common interface for classes defining state for reservoir modeling computations."""
    pass


class ReservoirModel(ABC):
    """Implements the common interface for classes providing reservoir modeling capabilities."""

    def execute(self, state: ModelState) -> None:
        pass

