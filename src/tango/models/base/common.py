from dataclasses import dataclass

WELL_PATTERN = ["DOUBLET", "5SPOT", "5SPOT_SHARED", "5SPOT_MANY"]

@dataclass
class CommonSpecs:
    fluid_name: str
    mass_flow_rate: float  # kg/s
    dt: float  # time step years
    reservoir_depth: float
    rock_density: float
    rock_cp: float
    rock_k: float
    surface_temperature: float  # K
    surface_pressure: float  # Pa
    thermal_gradient: float  # degC/m
    cost_year: int # yr #TODO: add start_yr. cost_year=nearest_neighbor(current_yr)?
    project_maturity: str
    well_pattern: str
    num_patterns: 1 # not used if doublet
    # start_yr: int
    # num_5spots: int # optional. requi