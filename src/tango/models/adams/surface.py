from tango.models.base import *
from tango.core.config import *
from tango.core import FluidState
from tango.model import ModelState
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


class SurfaceStateAdams(SurfaceState):
    """The power plant state based on Adams et al. (2015)."""
    def __init__(self):
        SurfaceState.__init__(self)
        # power plant
        self.inlet_fluid_turbine: FluidState
        self.inlet_fluid_condenser: FluidState
        self.inlet_fluid_pump: FluidState
        self.outlet_fluid_turbine: FluidState
        self.outlet_fluid_condenser: FluidState
        self.outlet_fluid_pump: FluidState
        self.dP_pump: float = 0.
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
        self.X_CO2 = 1.0

        self.condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        self.condensation_temperature_range = 0

        self.set_constants()


    def set_constants(self) -> None:

        # """
        #     - mass_flow_rate = flow rate at an injector (Kg/s)
        #     - m_dot = flow rate at each well pair (Kg/s)
        # """
        # if self.specs.well_pattern not in WELL_PATTERN_OPTIONS:
        #     raise RuntimeError(f"well_pattern: {self.well_pattern} is not supported")
        # self.m_dot = self.specs.mass_flow_rate
        # if self.specs.well_pattern == 'INVERTED_5SPOT':
        #     self.m_dot = self.specs.mass_flow_rate / 4.0

        if self.specs.cooling_mode == 'WET':
            self.coeffs_cooling = [1.2, 0., -3.79e-3, 1.95e-2]
            self.coeffs_condensing = [1.65, -6.24e-6, -5.03e-3, 0.]
        elif self.specs.cooling_mode == 'DRY':
            self.coeffs_cooling = [7.65e-1, 0., 0., 1.28e-1]
            self.coeffs_condensing = [0.619, 0., 0., 0.]
        else:
            raise ValueError(f"surface_cooling_tower_mode: {self.specs.cooling_mode} is not supported")


    def init_state(self, state: SurfaceStateAdams) -> None:
        """
        direct CO2 thermosiphon system:
            production_well - turbine - condenser - pump - injection_well
        """
        state.outlet_fluid_turbine = FluidState.withQT(self.fluid_name, Q=1.0, T=self.condensation_temperature)

        state.outlet_fluid_condenser = FluidState.withQT(self.fluid_name, Q=0.0, T=self.condensation_temperature)
        self.condensation_pressure = state.outlet_fluid_condenser.P + self.specs.condensation_pressure_offset
        self.condenser_saturated_vapor_h = FluidState.withPQ(self.fluid_name, Q=1.0, P=self.condensation_pressure).H
        self.condenser_saturated_liquid_h = FluidState.withPQ(self.fluid_name, Q=0.0, P=self.condensation_pressure).H

        state.inlet_fluid_pump = FluidState.withPT(self.fluid_name, self.condensation_pressure, self.condensation_temperature)
        state.outlet_fluid_pump = FluidState.withPT(self.fluid_name, self.condensation_pressure, self.condensation_temperature)

        state.outlet_fluid = FluidState.copy(state.outlet_fluid_pump)


    def set_inlet_state(self, state, state_from) -> None:
        state.inlet_fluid = state_from.outlet_fluid # inlet_fluid at production_well


    def update_turbine_power(self, state: SurfaceStateAdams) -> None:
        state.outlet_fluid_turbine.updatePS(P = self.condensation_pressure, S = state.inlet_fluid.S)

        hs_outlet = state.outlet_fluid_turbine.H # (J/kg)
        h_inlet = state.inlet_fluid.H            # (J/kg)
        eta = self.specs.eta_turbine             # (-)
        X_CO2 = 1.0 # CO2 mass fraction of produced fluid #TODO: implement something like state.inlet_fluid.X_CO2 for multphase flow

        state.w_turbine = X_CO2 * eta * (h_inlet - hs_outlet)


    def BAC_regression_model(self, coeffs: list) -> float:
        """
        Baltimore Aircoil Specific (BAC) regression model for cooling and condensing costs
        """
        a, b, c, d = coeffs
        T_ambient = self.specs.surface_temperature
        dT_approach = self.specs.approach_temperature
        dT_range = self.condensation_temperature_range
        return a / dT_approach + b * T_ambient + c * T_ambient / dT_approach + d / (dT_approach+dT_range)


    def get_parasitic_power_fraction_cooling(self):
        return self.BAC_regression_model(coeffs=self.coeffs_cooling)


    def get_parasitic_power_fraction_condensing(self):
        return self.BAC_regression_model(coeffs=self.coeffs_condensing)


    def update_condenser_state(self, state: SurfaceStateAdams) -> None:

        hs_outlet = state.outlet_fluid_turbine.H  # Ideal (eta=1.0) enthalpy of outlet fluid (J/kg)
        h_inlet = state.inlet_fluid.H  # (J/kg)
        X_CO2 = 1.0  # CO2 mass fraction of produced fluid #TODO: implement something like state.inlet_fluid.X_CO2 for multphase flow
        eta = self.specs.eta_turbine  # (-)
        h_saturated_vapor = self.condenser_saturated_vapor_h
        h_condensed = self.condenser_saturated_liquid_h

        h_turbine_outlet = h_inlet - eta * (h_inlet - hs_outlet)

        state.q_cooler = 0.
        state.q_condenser = h_condensed - h_turbine_outlet
        if h_turbine_outlet > h_saturated_vapor: # desuperheating needed
            state.q_cooler = h_saturated_vapor - h_turbine_outlet
            state.q_condenser = h_condensed - h_saturated_vapor
            T_turbine_outlet = FluidState.withHP(self.fluid_name, h_turbine_outlet, self.condensation_pressure).T
            self.condensation_temperature_range = T_turbine_outlet - self.condensation_temperature

        state.w_cooler = X_CO2 * state.q_cooler * self.get_parasitic_power_fraction_cooling()
        state.w_condenser = X_CO2 * state.q_condenser * self.get_parasitic_power_fraction_condensing()


    def update_pump_state(self, state: SurfaceStateAdams) -> None:

        eta = self.specs.eta_pump
        X_CO2 = 1.0  # CO2 mass fraction of produced fluid #TODO: implement something like state.inlet_fluid.X_CO2 for multphase flow

        P_pump_outlet = self.condensation_pressure + state.dP_pump

        h_pump_inlet = state.inlet_fluid_pump.H
        h_pump_outlet = state.inlet_fluid_pump.H
        if state.dP_pump > 0:
            state.outlet_fluid_pump.updatePS(P=P_pump_outlet, S=state.inlet_fluid_pump.S)
            h_pump_outlet = h_pump_inlet + (state.outlet_fluid_pump.H - h_pump_inlet) / eta

        state.w_pump = -1.0 * X_CO2 * (h_pump_outlet - h_pump_inlet)

        P_inj_inlet = P_pump_outlet + min(0., state.dP_pump) # if dP_pump <0, then choke.
        state.outlet_fluid.updateHP(H=h_pump_outlet, P=P_inj_inlet)


    def update_net_state(self, state: SurfaceStateAdams) -> None:
        state.w_net = state.w_turbine + state.w_cooler + state.w_condenser + state.w_pump

    def overwrite_pump_state(self, state: SurfaceStateAdams, dP_pump: float) -> None:

        state.dP_pump = dP_pump

        self.update_pump_state(state)

        self.update_net_state(state)


    def execute(self, state: SurfaceStateAdams) -> None:

        self.update_turbine_power(state)

        self.update_condenser_state(state)

        self.update_pump_state(state)

        self.update_net_state(state)
