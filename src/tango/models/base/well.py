from abc import ABC
from tango.core import FluidState

class WellSpecs:
    """Implements the common interface for classes providing well specifications."""
    pass


class WellState(ABC):
    """Implements the common interface for classes defining state for well modeling computations."""
    def __init__(self):
        self.mass_rate: float = 0.0
        self.inlet_fluid: FluidState
        self.outlet_fluid: FluidState


class WellModel(ABC):
    """Implements the common interface for classes providing well modeling capabilities."""

    def __init__(self, specs: WellSpecs) -> None:
        raise NotImplementedError("Define __init__ for your derived WellModel class.")

    def execute(self, state: WellState) -> None:
        raise NotImplementedError("Define execute method for your derived WellModel class.")

