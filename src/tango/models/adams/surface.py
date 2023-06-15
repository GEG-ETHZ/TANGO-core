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
    eta_turbine: float = 0.78    # The isentropic efficiency of the turbine (-)
    eta_pump: float = 0.75    # The pump efficiency (-)
    condensation_pressure_offset: float = 5e4   # (Pa)


class SurfaceStateAdams(SurfaceState):
    """The power plant state based on Adams et al. (2015)."""
    def __init__(self):
        SurfaceState.__init__(self)
        # power plant
        self.outlet_fluid_turbine: FluidState
        self.outlet_fluid_condenser: FluidState
        self.w_turbine: float
        self.w_pump: float
        self.w_cooler: float
        self.w_condenser: float
        self.w_net: float    # (MW)

        # pipe

        # economic

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

        # self.set_econ()


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


    def set_econ_specs(self) -> None:
        self.specs.econ = EconomicSpecs()
        self.get_CAPEX()


    def get_CAPEX(self):

        # CAPEX for surface pipes

        pass


    def get_cost(self) -> float:
        # TODO: implement C_TG (dynamic cost with some dependencies)
        return 0


    def execute(self) -> None:
        self.update_turbine_power()
