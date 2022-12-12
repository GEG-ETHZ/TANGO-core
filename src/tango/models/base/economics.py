from abc import ABC

class EconomicsSpecs:
    """Implements the common interface for classes providing economic specifications."""
    pass


class EconomicsState(ABC):
    """Implements the common interface for classes defining state for economic modeling computations."""
    pass


class EconomicsModel(ABC):
    """Implements the common interface for classes providing economic modeling capabilities."""

    def __init__(self, specs: EconomicsSpecs) -> None:
        raise NotImplementedError("Define __init__ for your derived EconomicsModel class.")

    def execute(self, state: EconomicsState) -> None:
        raise NotImplementedError("Define execute method for your derived EconomicsModel class.")
