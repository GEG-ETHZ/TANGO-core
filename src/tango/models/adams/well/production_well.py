from tango.models.base import *
from tango.models.adams.well.base import *
from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION
from dataclasses import dataclass
import copy
import logging
import numpy as np


class ProductionWellStateAdams(WellState):
    """The well state model"""
    def __init__(self) -> None:
        WellState.__init__(self)


class ProductionWellModelAdams(WellModelAdams):
    """The injection well model based on Adams et al. (2015)."""
    def __init__(self, specs: dict):
        WellModelAdams.__init__(self, specs)
        self.f_dir = 1.0 # upwards
        self.set_well_mass_flow_rate()


    def set_well_mass_flow_rate(self) -> None:
        self.well_mass_flow_rate = self.injector_mass_flow_rate # doublet
        if self.specs.well_pattern == 'INVERTED_5SPOT':
            self.well_mass_flow_rate = self.well_mass_flow_rate / 4.0 # 4=number of producers


    def execute(self, *args) -> None:
        self.update()
