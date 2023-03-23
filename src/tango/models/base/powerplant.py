from abc import ABC
from tango.core import FluidState

class PowerPlantSpecs:
    """Implements the common interface for classes providing power plant specifications."""
    pass


class PowerPlantState(ABC):
    """Implements the common interface for classes defining state for power plant modeling computations."""
    def __init__(self):
        self.mass_rate: float = 0.0
        self.inlet_fluid: FluidState
        self.outlet_fluid: FluidState


class PowerPlantModel(ABC):
    """Implements the common interface for classes providing power plant modeling capabilities."""

    def __init__(self, specs: PowerPlantSpecs) -> None:
        raise NotImplementedError("Define __init__ for your derived PowerPlantModel class.")

    def execute(self, state: PowerPlantState) -> None:
        raise NotImplementedError("Define execute method for your derived PowerPlantModel class.")

