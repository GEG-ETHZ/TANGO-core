from tango.models.base import *
from tango.core.config import *
from tango.core import FluidState
from dataclasses import dataclass

@dataclass
class SurfaceSpecsAdams(CommonSpecs):
    """The power plant specs based on Adams et al. (2015)."""
    approach_temperature: float = 7.0    # The temperature difference between condensing and the surface temperature (K)
    pinch_temperature: float = 5.0    # (K)
    temperature_range: float = 0. # diff between inlet and exit fluid temperature.
    eta_turbine: float = 0.78    # The isentropic efficiency of the turbine (-)
    eta_pump: float = 0.90    # The pump efficiency (-)
    condensation_pressure_offset: float = 5e4   # (Pa)
    total_pipe_length: float = None # (m)
    pipe_diameter: float = 0.41 # (m)
    pipe_length_per_well_pair: float = 750 # (m)
    cooling_tower_design: str = 'CLOSED' # cooling tower design
    cooling_mode: str = 'WET' # WET or DRY
    initial_outlet_pressure: float = 1.2e6 # (Pa) Initial guess of outlet (injector wellhead) pressure (Pa) for ORC
    initial_outlet_temperature: float = 333.15 # Initial guess of outlet (injector wellhead) temperature (K) for ORC


class SurfaceStateAdams(SurfaceState):
    """The power plant state based on Adams et al. (2015)."""
    def __init__(self):
        SurfaceState.__init__(self)
        self.inlet_fluid_turbine: FluidState
        self.inlet_fluid_condenser: FluidState
        self.inlet_fluid_pump: FluidState
        self.outlet_fluid_turbine: FluidState
        self.outlet_fluid_condenser: FluidState
        self.outlet_fluid_pump: FluidState
        self.dP_pump: float = 0.
        self.dP_pipes: float = 0.
        self.temperature_old: float = 333.15 # K temperature at previous time step
        self.q_condenser: float = 0.
        self.q_cooler: float = 0.
        self.q_preheater: float = 0.
        self.q_boiler: float = 0.
        self.q_desuperheater: float = 0.
        self.w_turbine: float = 0.
        self.w_pump: float = 0.
        self.w_cooler: float = 0.
        self.w_condenser: float = 0.
        self.w_net: float = 0.


class SurfaceModelAdams(SurfaceModel):
    """The power plant model based on Adams et al. (2015)."""
    def __init__(self, specs: dict):
        self.specs = SurfaceSpecsAdams(**specs)
        self.fluid_name = self.specs.fluid_name
        self.m_dot = self.specs.mass_flow_rate


    def set_inlet_state(self, state, state_from) -> None:
        state.inlet_fluid = state_from.outlet_fluid # inlet_fluid at production_well


    def execute(self, state: SurfaceStateAdams) -> None:
        self.update(state)
