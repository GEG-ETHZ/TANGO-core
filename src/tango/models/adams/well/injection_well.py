import copy
import logging
from tango.models.base import *
from tango.models.adams.well.base import *
from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION
from dataclasses import dataclass
import numpy as np


class InjectionWellStateAdams(WellState):
    """The well state model"""
    def __init__(self) -> None:
        WellState.__init__(self)


class InjectionWellModelAdams(WellModelAdams):
    """The injection well model based on Adams et al. (2015)."""
    def __init__(self, specs: dict):
        WellModelAdams.__init__(self, specs)
        self.well_mass_flow_rate = self.injector_mass_flow_rate
        self.f_dir = -1.0 # downwards


    def overwrite_inlet_fluid_state_PT(self, P: float = None, T: float = None):
        if P != None and T == None:
            T = self.fluid_state_init.T
        elif P == None and T != None:
            P = self.fluid_state_init.P
        self.fluid_state_init.updatePT(P, T)
