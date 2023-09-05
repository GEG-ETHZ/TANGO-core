#TODO: Implement
import logging

from tango.core.config import *
from tango.core import FluidState
from tango.models.native.common import CommonSpecs
from tango.models.native.surface.base import *
from dataclasses import dataclass


@dataclass
class SurfaceSpecsAGSNative(CommonSpecs):
    place_holder: float = None  # (m)


class SurfaceStateAGSNative(SurfaceState):
    def __init__(self):
        SurfaceState.__init__(self)
        self.inlet_fluid_state: FluidState
        self.outlet_fluid_state: FluidState


class SurfaceModelAGSNative(SurfaceModelNative):

    def __init__(self, specs: dict):
        SurfaceModelNative.__init__(self, specs)
        self.specs = SurfaceSpecsCPGNative.from_dict(specs)