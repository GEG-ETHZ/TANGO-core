from tango.models.base import *
from tango.models.adams.well.base import WellModelAdams
from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import GRAVITY_ACCELERATION
import copy
import logging
import numpy as np


class HorizontalWellStateAdams(WellState):
    """The well state model"""
    def __init__(self) -> None:
        WellState.__init__(self)


class HorizontalWellModelAdams(WellModelAdams):

    def __init__(self, specs: dict):
        WellModelAdams.__init__(self, specs)
        self.well_mass_flow_rate = self.injector_mass_flow_rate #TODO: update this
        self.f_dir = -1.0 # not used?

        # overwrite static parameters for horizontal well
        self.set_well_length()
        self.set_farfield_temperature()
        num_cells = self.specs.num_cells
        self.dL = self.well_length/num_cells
        self.dz = self.dZ/num_cells


    def init_state(self, state) -> None:
        h, dTdz, T0 = self.specs.reservoir_depth, self.specs.thermal_gradient, self.specs.surface_temperature
        initial_pressure = self.specs.brine_density * GRAVITY_ACCELERATION * h
        initial_temperature = T0 + h * dTdz
        state.inlet_fluid = FluidState.withPT(self.specs.fluid_name, initial_pressure, initial_temperature)
        state.outlet_fluid = FluidState.withPT(self.specs.fluid_name, initial_pressure, initial_temperature)



    def set_inlet_state(self, state_self, state_from) -> None:
        state_self.inlet_fluid = state_from.outlet_fluid
        # state_self.outlet_fluid = FluidState.copy(state_self.inlet_fluid)
        self.fluid_state_tmp = state_self.outlet_fluid
        self.fluid_state_init = state_self.inlet_fluid
        state_self.mass_rate = self.well_mass_flow_rate


    def set_well_length(self):
        if self.specs.well_length is None:
            assert self.specs.vertical_deviation >= 0
            horizontal_deviation = 90. - self.specs.vertical_deviation
            self.horizontal_deviation_rad = np.deg2rad(horizontal_deviation)
            self.well_length = self.specs.well_spacing / np.cos(self.horizontal_deviation_rad)
        else:
            self.well_length = self.specs.well_length


    def set_farfield_temperature(self): # wellhead_depth is to overwrite T_r if prd_pump exists
        self.dZ = self.well_length * np.tan(self.horizontal_deviation_rad)
        Z0 = self.specs.reservoir_depth if self.specs.wellhead_depth < 1e-10 else self.specs.wellhead_depth
        self.zspace = np.linspace(Z0, Z0 + self.dZ, self.specs.num_cells+1)
        self.zspace = (self.zspace[1:] + self.zspace[:-1]) * 0.5  # depth at cell centers

        dTdz = self.specs.thermal_gradient
        T0 = self.specs.surface_temperature
        self.T_r = T0 + self.zspace * dTdz  # rock temperature (K)


    def execute(self, *args) -> None:
        self.update()
