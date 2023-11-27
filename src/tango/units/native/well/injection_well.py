from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import *
from tango.units.native.well.base import *

import copy
import logging
from dataclasses import dataclass
import numpy as np


class InjectionWellStateNative(WellStateNative):
    """The well state unit"""
    def __init__(self) -> None:
        WellStateNative.__init__(self)
        self._injection_temperature_tmp: float = 0. # injection temperature at previous iteration (K)


    # def get_inlet_temperature_tmp(self) -> float:
    #     return self._injection_temperature_tmp


    # def get_del_temperature(self, T:float) -> float:
    #     return self._injection_temperature_tmp - T


    # def update_inlet_temperature_tmp(self) -> None:
    #     self._injection_temperature_tmp = self.inlet_fluid.T


    # def update_inlet_fluid_state_PT(self, P: float = None, T: float = None) -> None:
    #     if P != None and T == None:
    #         P = max(P, ATMOSPHERIC_PRESSURE)
    #         T = self.inlet_fluid.T
    #     elif P == None and T != None:
    #         P = self.inlet_fluid.P
    #         T = max(T, MIN_INJ_TEMPERATURE)
    #     self.inlet_fluid.updatePT(P, T)


class InjectionWellUnitNative(WellUnitNative):
    """The injection well unit based on Adams et al. (2015)."""
    def __init__(self, id: str, specs: dict):
        WellUnitNative.__init__(self, id, specs=self._process_specs(specs))
        self._well_mass_flow_rate = self._specs.mass_flow_rate
        self._f_dir = -1.0 # downwards
        self._set_mult()
        self.init_state()


    def _process_specs(self, specs) -> dict:
        return specs['common'] | specs['injection_well']


    def _set_mult(self) -> None:
        """
            - m_dot_mult is to convert m_dot (well-pair level mass flow rate) at a producer
              to a pattern level mass flow rate (=injection mass flow rate)
        """
        self._m_dot_mult = 0.25 if self._specs.well_pattern in ['5SPOT'] else 1.0


    def init_state(self, P: float=None, T: float=None) -> None:
        P = self._specs.surface_pressure if P==None else P
        T = self._specs.surface_temperature if T == None else T
        self.state = InjectionWellStateNative()
        self.mass_rate = self._well_mass_flow_rate

        # self.mass_rate = self._well_mass_flow_rate

        self.inlet_fluid = FluidState.withPT(self._specs.fluid_name, P, T)

        self.outlet_fluid = FluidState.copy(self.inlet_fluid)


    def init_inlet_state(self, inlet_state) -> None:
        self.inlet_fluid = FluidState.copy(inlet_state.outlet_fluid)
        self.update_inlet_temperature_tmp()


    def overwrite_inlet_fluid_state_PT(self, P: float = None, T: float = None):
        if P != None and T == None:
            T = self.fluid_state_init.T
        elif P == None and T != None:
            P = self.fluid_state_init.P
        self.fluid_state_init.updatePT(P, T)


    def get_del_temperature(self, T:float) -> float:
        return self.state._injection_temperature_tmp - T


    def update_inlet_fluid_state_PT(self, P: float = None, T: float = None) -> None:
        if P != None and T == None:
            P = max(P, ATMOSPHERIC_PRESSURE)
            T = self.inlet_fluid.T
        elif P == None and T != None:
            P = self.inlet_fluid.P
            T = max(T, MIN_INJ_TEMPERATURE)
        self.inlet_fluid.updatePT(P, T)


    def update_inlet_temperature_tmp(self) -> None:
        self.state._injection_temperature_tmp = self.inlet_fluid.T

    def get_inlet_temperature_tmp(self) -> float:
        return self.state._injection_temperature_tmp
