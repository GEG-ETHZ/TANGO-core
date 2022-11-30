from tango.models.base import *
from tango.model import ModelState
from dataclasses import dataclass


@dataclass
class ReservoirSpecsAdams(ReservoirSpecs):
    """Specifications for reservoir modeling based on Adams et. al (2015)"""
    well_diameter: float    = 0.14    # the well diameter (in m)
    depth: float            = 1.0     # the reservoir depth (in km)
    thickness: float        = 305     # the reservoir thickness (in m)
    rock_density: float     = 2300    # the rock density in the reservoir (in kg/m3)
    porosity: float         = 0.10    # the rock porosity in the reservoir (dimensionless)
    permeability: float     = 5.0e-14 # the rock permeability in the reservoir (in m2)
    volume: float           = 2.7e+8  # the reservoir volume (in m3)
    fluid_volume: float     = 0.3e+8  # the volume of fluid in the reservoir (in m3)
    thermal_gradient: float = 20.0    # the vertical thermal gradient in the reservoir (in °C/km)


class ReservoirModelAdams(ReservoirModel):
    """The reservoir model based on Adams et al. (2015)."""

    def __init__(self, specs: ReservoirSpecs) -> None:
        self.specs = specs


    def execute(self, state: ModelState) -> None:
        pass

