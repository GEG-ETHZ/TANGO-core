from tango.models.base import *
from tango.model import ModelState


class PowerPlantSpecsAdams(PowerPlantSpecs):
    """Implements the common interface for classes providing economic specifications."""
    pass


class PowerPlantModelAdams(PowerPlantModel):
    """Implements the common interface for classes providing economic modeling capabilities."""

    def __init__(self, specs: PowerPlantSpecsAdams) -> None:
        pass

    def execute(self, state: ModelState) -> None:
        pass
