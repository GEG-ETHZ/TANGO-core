from abc import ABC

class WellSpecs:
    """Implements the common interface for classes providing well specifications."""
    pass


class WellState(ABC):
    """Implements the common interface for classes defining state for well modeling computations."""
    pass


class WellModel(ABC):
    """Implements the common interface for classes providing well modeling capabilities."""

    def __init__(self, specs: WellSpecs) -> None:
        raise NotImplementedError("Define __init__ for your derived WellModel class.")

    def execute(self, state: WellState) -> None:
        raise NotImplementedError("Define execute method for your derived WellModel class.")

