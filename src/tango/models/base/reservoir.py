from tango.model import ModelState


class ReservoirSpecs:
    """Implements the common interface for classes providing reservoir specifications."""
    pass


class ReservoirState:
    """Implements the common interface for classes defining state for reservoir modeling computations."""
    pass


class ReservoirModel:
    """Implements the common interface for classes providing reservoir modeling capabilities."""

    def __init__(self, specs: ReservoirSpecs) -> None:
        raise NotImplementedError("Define __init__ for your derived ReservoirModel class.")

    def execute(self, state: ModelState) -> None:
        raise NotImplementedError("Define execute method for your derived ReservoirModel class.")

