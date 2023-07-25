import copy
import logging
from tango.models.base import *
from tango.models.adams.well.base import *
from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION
from dataclasses import dataclass
import numpy as np


class ProductionWellPumpStateAdams(WellState):
    """The well state model"""
    def __init__(self) -> None:
        WellState.__init__(self)
        dP_pump: float = 0.


class ProductionWellPumpModelAdams(WellModelAdams):
    """The injection well model based on Adams et al. (2015)."""
    def __init__(self, specs: dict):
        WellModelAdams.__init__(self, specs)
        self.f_dir = 1.0 # upwards
        self.set_well_mass_flow_rate()


    def set_well_mass_flow_rate(self) -> None:
        self.well_mass_flow_rate = self.injector_mass_flow_rate # doublet
        if self.specs.well_pattern == 'INVERTED_5SPOT':
            self.well_mass_flow_rate = self.well_mass_flow_rate / 4.0 # 4=number of producers


    def initialize_inlet_state(self, state) -> None:
        if state.dP_pump <= 0.:
            return
        self.fluid_state_init.updatePT(P=self.fluid_state_init.P + state.dP_pump,
                                       T=self.fluid_state_init.T)

    def execute(self, state) -> None:
        self.initialize_inlet_state(state)
        self.update()
