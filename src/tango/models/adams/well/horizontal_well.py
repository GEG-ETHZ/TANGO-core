from tango.models.base import *
from tango.models.adams.well.base import *
from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import GRAVITY_ACCELERATION
import copy
import logging
import numpy as np


class HorizontalWellStateAdams(WellStateAdams):
    """The well state model"""
    def __init__(self) -> None:
        WellStateAdams.__init__(self)


class HorizontalWellModelAdams(WellModelAdams):

    def __init__(self, specs: dict):
        WellModelAdams.__init__(self, specs)
        self._well_mass_flow_rate = self._injector_mass_flow_rate #TODO: update this for multiple lateral
        self._f_dir = -1.0 # not used?

        # overwrite static parameters for horizontal well
        self._dL = self._well_length / self._num_cells
        self._dz = self._dZ / self._num_cells


    def _compute_well_length(self) -> float:
        if self._specs.well_length is None:
            assert self._specs.vertical_deviation >= 0
            horizontal_deviation = 90. - self._specs.vertical_deviation
            self._horizontal_deviation_rad = np.deg2rad(horizontal_deviation)
            return self._specs.well_spacing / np.cos(self._horizontal_deviation_rad)
        else:
            return self._specs.well_length


    def _initialize_farfield_temperature(self) -> None:
        self._dZ = self._well_length * np.tan(self._horizontal_deviation_rad)
        Z0 = self._specs.reservoir_depth if self._specs.wellhead_depth < 1e-10 else self._specs.wellhead_depth
        zspace = np.linspace(Z0, Z0 + self._dZ, self._num_cells+1)
        zspace = (zspace[1:] + zspace[:-1]) * 0.5  # depth at cell centers

        dTdz = self._specs.thermal_gradient
        T0 = self._specs.surface_temperature
        self._T_r = T0 + zspace * dTdz  # rock temperature (K)


    def init_state(self, state) -> None:
        h, dTdz, T0 = self._specs.reservoir_depth, self._specs.thermal_gradient, self._specs.surface_temperature
        initial_pressure = self._specs.brine_density * GRAVITY_ACCELERATION * h
        initial_temperature = T0 + h * dTdz
        state.inlet_fluid = FluidState.withPT(self._specs.fluid_name, initial_pressure, initial_temperature)
        state.outlet_fluid = FluidState.withPT(self._specs.fluid_name, initial_pressure, initial_temperature)


    def set_inlet_state(self, state_self, state_from) -> None:
        state_self.inlet_fluid = state_from.outlet_fluid
        self.fluid_state_tmp = state_self.outlet_fluid
        self.fluid_state_init = state_self.inlet_fluid
        state_self.mass_rate = self._well_mass_flow_rate