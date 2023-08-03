import copy
import logging
from tango.models.base import *
from tango.models.adams.well import *
from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION
from dataclasses import dataclass
import numpy as np


class ProductionWellPumpStateAdams(WellState):
    """The well state model"""
    def __init__(self) -> None:
        WellState.__init__(self)
        # self.inlet_P_old: float = 0
        self.dP_pump: float = 0.
        self.w_pump: float = 0.


class ProductionWellPumpModelAdams(ProductionWellModelAdams):
    """The injection well model based on Adams et al. (2015)."""
    def __init__(self, specs: dict):
        ProductionWellModelAdams.__init__(self, specs)
        self.dP_pump_max = 1.0e7 #TODO: make it modifiable


    def set_inlet_P_tmp(self):
        self.inlet_P_tmp = copy.deepcopy(self.fluid_state_init.P) # inlet P w/o pumping


    def update_inlet_P(self, state):
        self.fluid_state_init.updatePT(P=self.inlet_P_tmp + state.dP_pump, T=self.fluid_state_init.T)

    def update_w_pump(self, state):
        if state.dP_pump <= 0.:
            return
        inlet_fluid_state_0 = FluidState.withPT(self.specs.fluid_name,
                                                P=self.fluid_state_init.P - state.dP_pump,
                                                T=self.fluid_state_init.T) # state w/o pumping
        state.w_pump = self.well_mass_flow_rate * (inlet_fluid_state_0.H - self.fluid_state_init.H) / self.specs.eta_pump


    def execute(self, state) -> None:
        self.set_inlet_P_tmp()
        self.update_inlet_P(state)
        self.update()
        self.update_w_pump(state)