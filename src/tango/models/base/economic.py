from abc import ABC


class EconomicSpecs(ABC):
    def __init__(self):
        pass


class EconomicState(ABC):
    """Implements the common interface for classes defining state for economic modeling computations."""
    pass


class EconomicModel(ABC):
    """Implements the common interface for classes providing economic modeling capabilities."""

    def __init__(self, specs: EconomicSpecs) -> None:
        # raise NotImplementedError("Define __init__ for your derived EconomicsModel class.")
        pass


    def execute(self, state: EconomicState) -> None:
        # raise NotImplementedError("Define execute method for your derived EconomicsModel class.")
        pass
