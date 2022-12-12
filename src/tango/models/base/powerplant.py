from abc import ABC

class PowerPlantSpecs:
    """Implements the common interface for classes providing power plant specifications."""
    pass


class PowerPlantState(ABC):
    """Implements the common interface for classes defining state for power plant modeling computations."""
    pass


class PowerPlantModel(ABC):
    """Implements the common interface for classes providing power plant modeling capabilities."""

    def __init__(self, specs: PowerPlantSpecs) -> None:
        raise NotImplementedError("Define __init__ for your derived PowerPlantModel class.")

    def execute(self, state: PowerPlantState) -> None:
        raise NotImplementedError("Define execute method for your derived PowerPlantModel class.")

