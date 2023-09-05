from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION
from tango.units.native.well.base import *

from dataclasses import dataclass
import copy
import logging
import numpy as np


class ProductionWellStateNative(WellStateNative):
    """The well state unit"""
    def __init__(self) -> None:
        WellStateNative.__init__(self)


class ProductionWellUnitNative(WellUnitNative):
    """The production well unit based on Adams et al. (2015)."""
    def __init__(self, specs: dict):
        WellUnitNative.__init__(self, specs=self._process_specs(specs))
        self._f_dir = 1.0 # upwards
        self._well_mass_flow_rate = self._compute_well_mass_flow_rate()


    def _process_specs(self, specs) -> dict:
        if 'production_well_pump' in specs:
            if 'well_length' not in specs['production_well']:
                raise RuntimeError(f"Required parameter: 'well_length' is not found in specs of 'production_well'.")
            if 'well_length' not in specs['production_well_pump']:
                raise RuntimeError(f"Required parameter: 'well_length' is not found in specs of 'production_well_pump'.")
            if 'reservoir' in specs:
                if 'reservoir_depth' not in specs['reservoir']:
                    raise RuntimeError(f"Required parameter: 'reservoir_depth' is not found in specs of 'reservoir'.")
                if specs['production_well']['well_length'] + specs['production_well_pump']['well_length'] != specs['injection_well']['well_length']:
                    raise ValueError(f"Different production and injection lengths are not supported.")
            specs['production_well']['wellhead_depth'] = specs['production_well_pump']['well_length']
        return specs['common'] | specs['production_well']


    def _compute_well_mass_flow_rate(self) -> float:
        """compute production well mass flow rate per well"""
        return self._specs.mass_flow_rate / 4.0 if self._specs.well_pattern == 'INVERTED_5SPOT' else self._specs.mass_flow_rate


    def init_state(self, P: float=None, T: float=None) -> None:
        P = self._specs.surface_pressure if P==None else P
        T = self._specs.surface_temperature if T == None else T
        self.state = ProductionWellStateNative()
        self.state.mass_rate = self._well_mass_flow_rate
        self.state.inlet_fluid = FluidState.withPT(self._specs.fluid_name, P, T)
        self.state.outlet_fluid = FluidState.copy(self.state.inlet_fluid)


    def update_well_length(self, pump_well_length: float) -> None:
        """sum up lengths of production well + pump well for economic calculation"""
        self._well_length += pump_well_length