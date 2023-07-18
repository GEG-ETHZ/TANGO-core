from tango.core.config import *
from tango.core import FluidState
from tango.models.adams.surface.base import *

import logging

class SurfaceModelAdamsORC(SurfaceModelAdams):

    """The power plant model based on Adams et al. (2015)."""
    def __init__(self, specs: dict):
        super().__init__(**specs)

        self.condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        self.condensation_temperature_range = 0

        self.set_constants()


    def update(self, state: SurfaceStateAdams) -> None:
        pass
