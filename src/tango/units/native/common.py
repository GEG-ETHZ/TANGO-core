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
