import copy
import logging
from tango.models.base import *
from tango.models.adams.well.base import *
from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import *
from dataclasses import dataclass
import numpy as np


class InjectionWellStateAdams(WellStateAdams):
    """The well state model"""
    def __init__(self) -> None:
        WellStateAdams.__init__(self)
        self._injection_temperature_tmp: float = 0. # injection temperature at previous iteration (K)


    def get_inlet_temperature_tmp(self) -> float:
        return self._injection_temperature_tmp


    def get_del_temperature(self) -> float:
        return self._injection_temperature_tmp - self.inlet_fluid.T


    def update_inlet_temperature_tmp(self) -> None:
        self._injection_temperature_tmp = self.inlet_fluid.T


    def update_inlet_fluid_state_PT(self, P: float = None, T: float = None) -> None:
        if P != None and T == None:
            P = max(P, ATMOSPHERIC_PRESSURE)
            T = self.inlet_fluid.T
        elif P == None and T != None:
            P = self.inlet_fluid.P
            T = max(T, MIN_INJ_TEMPERATURE)
        self.inlet_fluid.updatePT(P, T)


class InjectionWellModelAdams(WellModelAdams):
    """The injection well model based on Adams et al. (2015)."""
    def __init__(self, specs: dict):
        WellModelAdams.__init__(self, specs)
        self._well_mass_flow_rate = self._injector_mass_flow_rate
        self._f_dir = -1.0 # downwards


    def set_inlet_state(self, state_self, state_from) -> None:
        state_self.inlet_fluid = state_from.outlet_fluid
        state_self.outlet_fluid = FluidState.copy(state_self.inlet_fluid)
        self.fluid_state_tmp = state_self.outlet_fluid
        self.fluid_state_init = state_self.inlet_fluid
        state_self.mass_rate = self._well_mass_flow_rate
        state_self.update_inlet_temperature_tmp()


    def overwrite_inlet_fluid_state_PT(self, P: float = None, T: float = None):
        if P != None and T == None:
            T = self.fluid_state_init.T
        elif P == None and T != None:
            P = self.fluid_state_init.P
        self.fluid_state_init.updatePT(P, T)
