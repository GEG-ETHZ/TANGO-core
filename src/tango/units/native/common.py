from tango.core.config import *

from dataclasses import dataclass
import inspect

@dataclass
class CommonSpecs:
    fluid_name: str
    mass_flow_rate: float  # kg/s
    rock_density: float # kg/m3
    rock_cp: float # specific heat capacity (J/(kg*K))
    rock_k: float
    surface_temperature: float  # K
    surface_pressure: float  # Pa
    thermal_gradient: float  # degC/m
    well_pattern: str
    well_spacing: float
    well_pattern_dimens: list
    start_date: str
    num_tsteps: int
    dt: float  # time step years
    def __post_init__(self):
        if self.well_pattern not in WELL_PATTERN_OPTIONS:
            raise ValueError(f"Well_pattern: {self.well_pattern} is not supported")
    @classmethod
    def from_dict(cls, env): # ignore extra arguments passed to a dataclass
        return cls(**{
            k: v for k, v in env.items()
            if k in inspect.signature(cls).parameters
        })


@dataclass
class WellSpecsNative(CommonSpecs):
    """The well specs based on Adams et al. (2015)."""
    well_length: float = None  # well length (m)
    diameter: float = None # (m)
    vertical_deviation: float = None    # vertical deviation angle defined in degrees
    epsilon: float = 55.e-6  # roughness of the well (m)
    num_cells: int = 100    # number of cells that is used for discretization
    gravity_scale_factor: float = 1.0    # the scale factor used for changing the direction of gravity
    probability_of_success: float = 0.95
    wellhead_depth: float = 0. # wellhead measured depth (m)
    eta_pump: float = 0.90  # The pump efficiency (-)
    brine_density: float = 1000.0  # the brine density used to calculate the reservoir pressure (kg/m3)
    def __post_init__(self):
        required_fields = ['well_length', 'diameter']
        for s in required_fields:
            if getattr(self, s, None) == None:
                raise RuntimeError(f"Required parameter: {s} is not found.")
