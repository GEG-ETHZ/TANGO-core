from dataclasses import dataclass

@dataclass
class CommonSpecs:
    fluid_name: str
    mass_flow_rate: float  # kg/s
    # inj_fluid_temperature: float # K
    dt: float # time step years
    reservoir_depth: float
    rock_density: float
    rock_cp: float
    rock_k: float
    surface_temperature: float  # K
    surface_pressure: float  # Pa
    thermal_gradient: float  # degC/m
    start_year: int 
    project_maturity: str
    well_pattern: str
    well_spacing: float
    num_patterns_sqrt: int
    lifetime: int # yr