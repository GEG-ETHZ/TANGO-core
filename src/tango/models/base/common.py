from dataclasses import dataclass

@dataclass
class CommonSpecs:
    fluid_name: str
    mass_flow_rate: float  # kg/s
    dt: float  # time step years