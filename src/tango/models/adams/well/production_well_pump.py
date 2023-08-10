import copy
import logging
from tango.models.base import *
from tango.models.adams.well import *
from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION, MAX_PRD_PUMP_DP
from dataclasses import dataclass
import numpy as np


class ProductionWellPumpStateAdams(WellStateAdams):
    """The well state model"""
    def __init__(self) -> None:
        WellStateAdams.__init__(self)
        self._dP_pump: float = 0.
        self._w_pump: float = 0.


    def set_dP_pump(self, val) -> None:
        self._dP_pump = min(max(val, 0.), MAX_PRD_PUMP_DP)


    def set_w_pump(self, val) -> None:
        self._w_pump = val


    def get_dP_pump(self) -> None:
        return self._dP_pump


    def get_w_pump(self) -> None:
        return self._w_pump


    def set_inlet_pressure(self) -> None:
        self._inlet_pressure_tmp = self.inlet_fluid.P


    def update_inlet_fluid_state_with_pump(self) -> None:
        P = self._inlet_pressure_tmp + self._dP_pump
        T = self.inlet_fluid.T
        self.inlet_fluid.updatePT(P, T)


class ProductionWellPumpModelAdams(ProductionWellModelAdams):
    """The injection well model based on Adams et al. (2015)."""
    def __init__(self, specs: dict):
        ProductionWellModelAdams.__init__(self, specs)
        self.dP_pump_max = 1.0e7 #TODO: make it modifiable


    def update_w_pump(self, state):
        dP_pump = state.get_dP_pump()
        if dP_pump <= 0.:
            return
        inlet_fluid_state_0 = FluidState.withPT(self._specs.fluid_name,
                                                P=self.fluid_state_init.P - dP_pump,
                                                T=self.fluid_state_init.T) # state w/o pumping
        w_pump = self._well_mass_flow_rate * (inlet_fluid_state_0.H - self.fluid_state_init.H) / self._specs.eta_pump
        state.set_w_pump(w_pump)


    def execute(self, state) -> None:
        state.set_inlet_pressure()
        state.update_inlet_fluid_state_with_pump()
        self.update(state)
        self.update_w_pump(state)