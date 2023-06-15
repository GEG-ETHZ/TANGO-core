from abc import ABC
from tango.core import FluidState

class SurfaceSpecs:
    """Implements the common interface for classes providing power plant specifications."""
    pass


class SurfaceState(ABC):
    """Implements the common interface for classes defining state for power plant modeling computations."""
    def __init__(self):
        self.mass_rate: float = 0.0
        self.inlet_fluid: FluidState
        self.outlet_fluid: FluidState


class SurfaceModel(ABC):
    """Implements the common interface for classes providing power plant modeling capabilities."""

    def __init__(self, specs: SurfaceSpecs) -> None:
        raise NotImplementedError("Define __init__ for your derived SurfaceModel class.")

    def execute(self, state: SurfaceState) -> None:
        raise NotImplementedError("Define execute method for your derived SurfaceModel class.")

