import copy
import logging
from dataclasses import dataclass
import numpy as np

from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION, MAX_PRD_PUMP_DP
from tango.units.native.well import *


class ProductionWellPumpStateNative(WellStateNative):
    """The well state unit"""
    def __init__(self) -> None:
        WellStateNative.__init__(self)
        self._dP_pump: float = 0.
        self._w_pump: float = 0.


    # def set_dP_pump(self, val) -> None:
    #     self._dP_pump = min(max(val, 0.), MAX_PRD_PUMP_DP)


    def set_w_pump(self, val) -> None:
        self._w_pump = val


    # def get_dP_pump(self) -> None:
    #     return self._dP_pump


    # def get_w_pump(self) -> None:
    #     return self._w_pump


    # def set_inlet_pressure(self) -> None:
    #     self._inlet_pressure_tmp = self.inlet_fluid.P


    # def update_inlet_fluid_state_with_pump(self) -> None:
    #     P = self._inlet_pressure_tmp + self._dP_pump
    #     T = self.inlet_fluid.T
    #     self.inlet_fluid.updatePT(P, T)


class ProductionWellPumpUnitNative(ProductionWellUnitNative):
    """The production well unit based on Adams et al. (2015)."""
    def __init__(self, id: str, specs: dict):
        ProductionWellUnitNative.__init__(self, id, specs)
        self.init_state()


    def _process_specs(self, specs) -> dict:
        if 'production_well' not in specs:
            raise RuntimeError(f"Required unit when using unit: 'production_well' is not found.")
        if specs['production_well_pump']['well_length'] > specs['production_well']['well_length']:
            raise ValueError(f"Unrealistic value found: 'well_length' of 'production_well_pump' is greater than production well length")
        return specs['common'] | specs['production_well_pump']


    def init_state(self):
        self.state = ProductionWellPumpStateNative()
        self.state.mass_rate = self._well_mass_flow_rate

        self.mass_rate = self._well_mass_flow_rate

        self.state.inlet_fluid = FluidState.withPT(self._specs.fluid_name,
                                                   self._specs.surface_pressure,
                                                   self._specs.surface_temperature)
        self.state.outlet_fluid = FluidState.copy(self.state.inlet_fluid)

        self.outlet_fluid = self.state.outlet_fluid


    def update_w_pump(self):
        dP_pump = self.get_dP_pump()
        if dP_pump <= 0.:
            return
        inlet_fluid_state_0 = FluidState.withPT(self._specs.fluid_name,
                                                P=self.fluid_state_init.P - dP_pump,
                                                T=self.fluid_state_init.T) # state w/o pumping
        w_pump = self._well_mass_flow_rate * (inlet_fluid_state_0.H - self.fluid_state_init.H) / self._specs.eta_pump
        self.state.set_w_pump(w_pump)


    def execute(self) -> None:
        self.update_inlet_state()
        self.set_inlet_pressure()
        self.update_inlet_fluid_state_with_pump()
        self.update()
        self.update_w_pump()

    def set_dP_pump(self, val) -> None:
        self.state._dP_pump = min(max(val, 0.), MAX_PRD_PUMP_DP)


    def get_dP_pump(self) -> None:
        return self.state._dP_pump


    def set_inlet_pressure(self) -> None:
        self._inlet_pressure_tmp = self.state.inlet_fluid.P


    def update_inlet_fluid_state_with_pump(self) -> None:
        P = self._inlet_pressure_tmp + self.state._dP_pump
        T = self.state.inlet_fluid.T
        self.state.inlet_fluid.updatePT(P, T)


    def get_w_pump(self) -> None:
        return self.state._w_pump
