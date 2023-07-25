from abc import ABC
from tango.core import FluidState

class ReservoirSpecs(ABC):
    """Implements the common interface for classes providing reservoir specifications."""
    pass


class ReservoirState(ABC):
    """Implements the common interface for classes defining state for reservoir modeling computations."""

    def __init__(self):
        self.mass_rate: float = 0.0
        self.inlet_fluid: FluidState
        self.outlet_fluid: FluidState

    def update(self, specs: ReservoirSpecs) -> None:
        pass


class ReservoirModel(ABC):
    """Implements the common interface for classes providing reservoir modeling capabilities."""

    def execute(self, state: ReservoirState) -> None:
        pass

