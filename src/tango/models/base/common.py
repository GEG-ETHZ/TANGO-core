from dataclasses import dataclass

@dataclass
class CommonSpecs:
    fluid_name: str
    mass_flow_rate: float  # kg/s
    # inj_fluid_temperature: float # K
    reservoir_depth: float
    rock_density: float
    rock_cp: float
    rock_k: float
    surface_temperature: float  # K
    surface_pressure: float  # Pa
    thermal_gradient: float  # degC/m
    # project_maturity: str
    well_pattern: str
    well_spacing: float
    well_pattern_dimens: list
    start_date: str
    # lifetime: int # yr
    num_tsteps: int
    dt: float  # time step years