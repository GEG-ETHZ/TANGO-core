from tango.model import ModelState


class WellSpecs:
    """Implements the common interface for classes providing well specifications."""
    pass


class WellState:
    """Implements the common interface for classes defining state for well modeling computations."""
    pass


class WellModel:
    """Implements the common interface for classes providing well modeling capabilities."""

    def __init__(self, specs: WellSpecs) -> None:
        raise NotImplementedError("Define __init__ for your derived WellModel class.")

    def execute(self, state: ModelState) -> None:
        raise NotImplementedError("Define execute method for your derived WellModel class.")

