import copy
import logging
import numpy as np

from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import GRAVITY_ACCELERATION
from tango.units.native.well.base import *


# class HorizontalWellStateNative(WellStateNative):
#     """The well state unit"""


class HorizontalWellUnitNative(WellUnitNative):

    def __init__(self, id, specs: dict):
        WellUnitNative.__init__(self, id, specs=self._process_specs(id, specs))
        self._well_mass_flow_rate = self._specs.mass_flow_rate
        self._f_dir = -1.0

        # overwrite static parameters for horizontal well
        self._dL = self._well_length / self._num_cells
        self._dz = self._dZ / self._num_cells

        self.init_state()


    def _process_specs(self, id, specs) -> dict:
        if isinstance(specs['horizontal_well'], list): # multiple h_wells
            specs_tmp = copy.deepcopy(specs)
            specs = dict()
            specs['common'] = specs_tmp['common']
            specs['horizontal_well'] = None
            for d in specs_tmp['horizontal_well']:
                if id in d.keys():
                    specs['horizontal_well'] = d[id]
                    break
            if specs['horizontal_well'] == None:
                raise RuntimeError(f"Failed to read horizontal_well specs for id: {id}")
        if 'wellhead_depth' not in specs['horizontal_well']:
            raise RuntimeError(f"Required parameter 'wellhead_depth' is not found in specs")
        if np.abs(specs['common']['well_spacing'] - specs['horizontal_well']['well_length']) < 1e-5:
            logging.warning("Inconsistent well_spacing and horizontal_well length found.")
        return specs['common'] | specs['horizontal_well']


    def _set_well_length(self) -> float:
        if self._specs.well_length is None:
            raise RuntimeError(f"Required parameter 'well_length' is not found in specs.")
        else:
            return self._specs.well_length


    def _initialize_farfield_temperature(self) -> None:
        if self._specs.vertical_deviation == None:
            raise ValueError(f"Required parameter: 'vertical_deviation' is not found.")
        if self._specs.vertical_deviation <= 0:
            raise ValueError(f"Invalid parameter value found in 'vertical_deviation'. Please use a positive value")
        self._dZ = self._well_length * np.tan(np.deg2rad(90. - self._specs.vertical_deviation))
        Z0 = self._specs.wellhead_depth # heel depth
        zspace = np.linspace(Z0, Z0 + self._dZ, self._num_cells+1)
        zspace = (zspace[1:] + zspace[:-1]) * 0.5  # depth at cell centers

        dTdz = self._specs.thermal_gradient
        T0 = self._specs.surface_temperature
        self._T_r = T0 + zspace * dTdz  # rock temperature (K)


    def init_state(self) -> None:
        # self.state = HorizontalWellStateNative()
        h, dTdz, T0 = self._specs.wellhead_depth, self._specs.thermal_gradient, self._specs.surface_temperature
        initial_pressure = self._specs.brine_density * GRAVITY_ACCELERATION * h
        initial_temperature = T0 + h * dTdz
        self.inlet_fluid = FluidState.withPT(self._specs.fluid_name, initial_pressure, initial_temperature)
        self.outlet_fluid = FluidState.withPT(self._specs.fluid_name, initial_pressure, initial_temperature)

        self.mass_rate = self._well_mass_flow_rate

