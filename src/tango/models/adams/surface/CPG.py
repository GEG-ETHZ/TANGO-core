from tango.core.config import *
from tango.core import FluidState
from tango.models.adams.surface.base import *
from dataclasses import dataclass

import logging

@dataclass
class SurfaceSpecsAdamsCPG(CommonSpecs):
    approach_temperature: float = 7.0  # The temperature difference between condensing and the surface temperature (K)
    temperature_range: float = 0. # diff between inlet and exit fluid temperature.
    eta_pump: float = 0.90    # The pump efficiency (-)
    condensation_pressure_offset: float = 5e4   # (Pa)
    total_pipe_length: float = None # (m)
    pipe_diameter: float = 0.41 # (m)
    epsilon: float = 55.e-6  # roughness of surface pipe (m)
    eta_turbine: float = 0.78 # The isentropic efficiency of the turbine (-)
    cooling_tower_design: str = 'CLOSED' # cooling tower design
    cooling_mode: str = 'WET' # WET or DRY



class SurfaceStateAdamsCPG(SurfaceState): #TODO: cleanup states
    def __init__(self):
        SurfaceState.__init__(self)
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


class SurfaceModelAdamsCPG(SurfaceModelAdams):

    """The power plant model based on Adams et al. (2015)."""
    def __init__(self, specs: dict):
        SurfaceModelAdams.__init__(self)
        self.specs = SurfaceSpecsAdamsCPG(**specs)
        # self.specs = SurfaceSpecsAdamsCPG(specs)
        self.fluid_name = self.specs.fluid_name
        self.condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        self.condensation_temperature_range = 0
        self.X_CO2 = 1.0 if self.fluid_name == 'CO2' else 0.0 #TODO: implement something like state.inlet_fluid.X_CO2 for multphase flow
        self.set_mdot()
        self.set_constants()


    def set_inlet_state(self, state, state_from) -> None:
        state.inlet_fluid = state_from.outlet_fluid # inlet_fluid at production_well


    def init_state(self, state) -> None:
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


    def update_turbine_power(self, state) -> None:
        state.outlet_fluid_turbine.updatePS(P = self.condensation_pressure, S = state.inlet_fluid.S)

        hs_outlet = state.outlet_fluid_turbine.H # (J/kg)
        h_inlet = state.inlet_fluid.H            # (J/kg)
        eta = self.specs.eta_turbine             # (-)
        X_CO2 = self.X_CO2

        state.w_turbine = X_CO2 * self.m_dot * eta * (h_inlet - hs_outlet) # (W)


    def update_condenser_state(self, state) -> None:

        hs_outlet = state.outlet_fluid_turbine.H  # Ideal (eta=1.0) enthalpy of outlet fluid (J/kg)
        h_inlet = state.inlet_fluid.H  # (J/kg)
        X_CO2 = self.X_CO2
        eta = self.specs.eta_turbine  # (-)
        h_saturated_vapor = self.condenser_saturated_vapor_h # (J/kg)
        h_condensed = self.condenser_saturated_liquid_h # (J/kg)

        h_turbine_outlet = h_inlet - eta * (h_inlet - hs_outlet) # (J/kg)

        state.q_cooler = 0. # (W)
        state.q_condenser = self.m_dot * (h_condensed - h_turbine_outlet) # (W)
        if h_turbine_outlet > h_saturated_vapor: # desuperheating needed
            state.q_cooler = self.m_dot * (h_saturated_vapor - h_turbine_outlet)
            state.q_condenser = self.m_dot * (h_condensed - h_saturated_vapor)
            T_turbine_outlet = FluidState.withHP(self.fluid_name, h_turbine_outlet, self.condensation_pressure).T
            self.condensation_temperature_range = T_turbine_outlet - self.condensation_temperature

        state.w_cooler = X_CO2 * state.q_cooler * self.get_parasitic_power_fraction_cooling() # (W)
        state.w_condenser = X_CO2 * state.q_condenser * self.get_parasitic_power_fraction_condensing() # (W)


    def update_pump_state(self, state) -> None:

        eta = self.specs.eta_pump
        X_CO2 = self.X_CO2

        P_pump_outlet = self.condensation_pressure + state.dP_pump

        h_pump_inlet = state.inlet_fluid_pump.H
        h_pump_outlet = state.inlet_fluid_pump.H
        if state.dP_pump > 0:
            try:
                state.outlet_fluid_pump.updatePS(P=P_pump_outlet, S=state.inlet_fluid_pump.S)
            except:
                logging.warning(f"Failed to update fluid state with PS. Updating with PT instead.")
                state.outlet_fluid_pump.updatePT(P=P_pump_outlet, T=state.inlet_fluid_pump.T)

            h_pump_outlet = h_pump_inlet + (state.outlet_fluid_pump.H - h_pump_inlet) / eta

        state.w_pump = -1.0 * X_CO2 *  self.m_dot * (h_pump_outlet - h_pump_inlet)

        P_inj_inlet = P_pump_outlet + min(0., state.dP_pump) # if dP_pump <0, then choke.
        try:
            state.outlet_fluid.updateHP(H=h_pump_outlet, P=P_inj_inlet)
        except:
            logging.warning(f"Failed to update fluid state with HP. Updating with PT instead.")
            state.outlet_fluid.updatePT(P=P_inj_inlet, T=state.outlet_fluid_pump.T)

    def update_net_state(self, state) -> None:
        state.w_net = state.w_turbine + state.w_cooler + state.w_condenser + state.w_pump


    def overwrite_pump_state(self, state) -> None:

        self.update_pump_state(state)

        self.update_net_state(state)


    def update(self, state) -> None:

        self.update_turbine_power(state)

        self.update_condenser_state(state)

        self.update_pump_state(state)

        self.update_net_state(state)

