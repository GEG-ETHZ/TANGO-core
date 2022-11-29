from tango.models.base import *
from tango.model import ModelState


class EconomicsSpecsAdams(EconomicsSpecs):
    """Implements the common interface for classes providing economic specifications."""
    pass


class EconomicsModelAdams(EconomicsModel):
    """Implements the common interface for classes providing economic modeling capabilities."""

    def __init__(self, specs: EconomicsSpecsAdams) -> None:
        pass

    def execute(self, state: ModelState) -> None:
        pass
