from tango.models.base import *
from tango.model import ModelState
from dataclasses import dataclass


@dataclass
class WellSpecsAdams(WellSpecs):
    """The well specs based on Adams et al. (2015)."""
    pass


class WellModelAdams(WellModel):
    """The well model based on Adams et al. (2015)."""

    def __init__(self, specs: WellSpecs) -> None:
        self.specs = specs


    def execute(self, state: ModelState) -> None:
        pass

