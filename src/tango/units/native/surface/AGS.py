#TODO: Implement
import logging

from tango.core.config import *
from tango.core import FluidState
from tango.units.native.common import CommonSpecs
from tango.units.native.surface.base import *
from dataclasses import dataclass


@dataclass
class SurfaceSpecsAGSNative(CommonSpecs):
    place_holder: float = None  # (m)


class SurfaceStateAGSNative(SurfaceState):
    def __init__(self):
        SurfaceState.__init__(self)
        self.inlet_fluid_state: FluidState
        self.outlet_fluid_state: FluidState


class SurfaceUnitAGSNative(SurfaceUnitNative):

    def __init__(self, specs: dict):
        SurfaceUnitNative.__init__(self, specs)
        self.specs = SurfaceSpecsCPGNative.from_dict(specs)