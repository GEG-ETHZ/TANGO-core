from dataclasses import dataclass

@dataclass
class CommonSpecs:
    fluid_name: str
    mass_flow_rate: float  # kg/s
    dt: float  # time step years
    reservoir_depth: float
    rock_density: float
    rock_cp: float
    surface_temperature: float  # K
    surface_pressure: float  # Pa
    thermal_gradient: float  # degC/m