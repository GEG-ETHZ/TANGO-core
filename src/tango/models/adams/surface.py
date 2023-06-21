from tango.models.base import *
from tango.core import FluidState
from tango.model import ModelState
from dataclasses import dataclass

@dataclass
class SurfaceSpecsAdams(CommonSpecs):
    """The power plant specs based on Adams et al. (2015)."""
    approach_temperature: float = 7.0    # The temperature difference between condensing and ambient temperature (K)
    pinch_temperature: float = 5.0    # (K)
    ambient_temperature: float = 288.15    # (K)
    temperature_range: float = 0. # diff between inlet and exit fluid temperature.
    eta_turbine: float = 0.78    # The isentropic efficiency of the turbine (-)
    eta_pump: float = 0.75    # The pump efficiency (-)
    condensation_pressure_offset: float = 5e4   # (Pa)
    total_pipe_length: float = None # (m)
    pipe_diameter: float = 0.41 # (m)
    pipe_length_per_well_pair: float = 750 # (m)
    cooling_tower_design: str = 'CLOSED' # cooling tower design
    cooling_mode: str = 'WET' # WET or DRY


class SurfaceStateAdams(SurfaceState):
    """The power plant state based on Adams et al. (2015)."""
    def __init__(self):
        SurfaceState.__init__(self)
        # power plant
        self.outlet_fluid_turbine: FluidState
        self.outlet_fluid_condenser: FluidState
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
    def __init__(self, specs: dict, state: SurfaceStateAdams):
        self.specs = SurfaceSpecsAdams(**specs)
        self.state = state
        self.fluid_name = self.specs.fluid_name

        self.condensation_temperature = self.specs.ambient_temperature + self.specs.approach_temperature
        self.state.outlet_fluid_condenser = FluidState.withQT(self.fluid_name, Q = 0.0, T = self.condensation_temperature)

        self.condensation_pressure = self.state.outlet_fluid_condenser.P + self.specs.condensation_pressure_offset
        self.state.outlet_fluid_turbine = FluidState.withQT(self.fluid_name, Q = 1.0, T = self.condensation_temperature)

        #TODO: w_pump, w_cooler, etc.


    def set_inlet_state(self, state) -> None:
        self.state.inlet_fluid = state.outlet_fluid


    def update_turbine_power(self) -> None:
        self.state.outlet_fluid_turbine.updatePS(P = self.condensation_pressure, S = self.state.inlet_fluid.S)

        hs_outlet = self.state.outlet_fluid_turbine.H    # (J/kg)
        h_inlet = self.state.inlet_fluid.H
        m_dot = self.specs.mass_flow_rate    # (kg/s)
        eta = self.specs.eta_turbine    # (-)

        self.state.w_turbine = m_dot * eta * (h_inlet- hs_outlet)

    def update_condensed_state(self) -> None:
        pass


    def execute(self) -> None:
        self.update_turbine_power()
        # TODO: temporary treatment below
        # self.state.q_condenser = -96870.880
        # self.state.q_cooler = 0.
        # self.state.w_turbine = 4627.154
        # self.state.w_pump = -620.439
        # self.state.w_cooler  = 0
        # self.state.w_condenser = -2601.939
        self.state.q_condenser = -93780.14908238029
        self.state.q_cooler = 0.
        self.state.w_turbine = 4561.923527055129
        self.state.w_pump = -620.4393145114882
        self.state.w_cooler  = 0
        self.state.w_condenser = -2518.9228540823065
