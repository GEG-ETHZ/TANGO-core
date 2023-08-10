from tango.models.base import *
from tango.models.adams.well.base import *
from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION
from dataclasses import dataclass
import copy
import logging
import numpy as np


class ProductionWellStateAdams(WellStateAdams):
    """The well state model"""
    def __init__(self) -> None:
        WellStateAdams.__init__(self)


class ProductionWellModelAdams(WellModelAdams):
    """The production well model based on Adams et al. (2015)."""
    def __init__(self, specs: dict):
        WellModelAdams.__init__(self, specs)
        self._f_dir = 1.0 # upwards
        self._well_mass_flow_rate = self._compute_well_mass_flow_rate()


    def _compute_well_mass_flow_rate(self) -> float:
        """compute production well mass flow rate per well"""
        return self._injector_mass_flow_rate / 4.0 if self._specs.well_pattern == 'INVERTED_5SPOT' else self._injector_mass_flow_rate


    def update_well_length(self, pump_well_length: float) -> None:
        """sum up lengths of production well + pump well for economic calculation"""
        self._well_length += pump_well_length