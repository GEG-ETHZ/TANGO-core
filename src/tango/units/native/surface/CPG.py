import logging

from tango.core.config import *
from tango.core import FluidState
from tango.units.native.common import CommonSpecs
from tango.units.native.surface.base import *
from dataclasses import dataclass

@dataclass
class SurfaceSpecsCPGNative(CommonSpecs):
    pipe_diameter: float = None  # (m)
    approach_temperature: float = None  # The temperature difference between condensing and the surface temperature (K)
    condensation_pressure_offset: float = None  # (Pa)
    temperature_range: float = 0. # diff between inlet and exit fluid temperature.
    eta_pump: float = 0.90    # The pump efficiency (-)
    total_pipe_length: float = None # (m)
    epsilon: float = 55.e-6  # roughness of surface pipe (m)
    eta_turbine: float = 0.78 # The isentropic efficiency of the turbine (-)
    cooling_tower_design: str = 'CLOSED' # cooling tower design
    cooling_mode: str = 'WET' # WET or DRY
    def __post_init__(self):
        required_fields = ['pipe_diameter', 'approach_temperature', 'condensation_pressure_offset']
        for s in required_fields:
            if getattr(self, s, None) == None:
                raise RuntimeError(f"Required parameter: {s} is not found.")


class SurfaceStateCPGNative(SurfaceState):
    def __init__(self):
        SurfaceState.__init__(self)
        self.inlet_fluid_turbine: FluidState
        self.inlet_fluid_condenser: FluidState
        self.inlet_fluid_pump: FluidState
        self.outlet_fluid_turbine: FluidState
        self.outlet_fluid_condenser: FluidState
        self.outlet_fluid_pump: FluidState
        self.q_condenser: float = 0.
        self.q_cooler: float = 0.
        self.q_preheater: float = 0.
        self.q_boiler: float = 0.
        self.q_desuperheater: float = 0.
        self.q_recuperator: float = 0.
        self.w_turbine: float = 0.
        self.w_pump: float = 0.
        self.w_cooler: float = 0.
        self.w_condenser: float = 0.
        self.w_net: float = 0.
        self._dP_pump: float = 0.


    # def get_dP_pump(self) -> float:
    #     return self._dP_pump


    # def update_dP_pump(self, val) -> None:
    #     self._dP_pump = val


class SurfaceUnitCPGNative(SurfaceUnitNative):

    """The power plant unit based on Adams et al. (2015)."""
    def __init__(self, id: str, specs: dict):
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsCPGNative.from_dict(self._process_specs(specs))
        self._fluid_name = self.specs.fluid_name
        self._condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        self._condensation_temperature_range = 0
        self._X_CO2 = 1.0 if self._fluid_name == 'CO2' else 0.0 #TODO: implement something like state.inlet_fluid.X_CO2 for multphase flow
        self._set_mult()
        self._set_constants()

        self.init_state()


    def _process_specs(self, specs) -> dict:
        return specs['common'] | specs['surface']


    def _update_turbine_power(self) -> None:
        self.state.outlet_fluid_turbine.updatePS(P = self.condensation_pressure, S = self.state.inlet_fluid.S)

        hs_outlet = self.state.outlet_fluid_turbine.H # (J/kg)
        h_inlet = self.state.inlet_fluid.H            # (J/kg)
        eta = self.specs.eta_turbine             # (-)
        X_CO2 = self._X_CO2

        self.state.w_turbine = X_CO2 * self.state.mass_rate * eta * (h_inlet - hs_outlet) # (W)


    def _update_condenser_state(self) -> None:

        hs_outlet = self.state.outlet_fluid_turbine.H  # Ideal (eta=1.0) enthalpy of outlet fluid (J/kg)
        h_inlet = self.state.inlet_fluid.H  # (J/kg)
        X_CO2 = self._X_CO2
        eta = self.specs.eta_turbine  # (-)
        h_saturated_vapor = self.condenser_saturated_vapor_h # (J/kg)
        h_condensed = self.condenser_saturated_liquid_h # (J/kg)

        h_turbine_outlet = h_inlet - eta * (h_inlet - hs_outlet) # (J/kg)

        self.state.q_cooler = 0. # (W)
        self.state.q_condenser = self.state.mass_rate * (h_condensed - h_turbine_outlet) # (W)
        if h_turbine_outlet > h_saturated_vapor: # desuperheating needed
            self.state.q_cooler = self.state.mass_rate * (h_saturated_vapor - h_turbine_outlet)
            self.state.q_condenser = self.state.mass_rate * (h_condensed - h_saturated_vapor)
            T_turbine_outlet = FluidState.withHP(self._fluid_name, h_turbine_outlet, self.condensation_pressure).T
            self._condensation_temperature_range = T_turbine_outlet - self._condensation_temperature

        self.state.w_cooler = X_CO2 * self.state.q_cooler * self._get_parasitic_power_fraction_cooling() # (W)
        self.state.w_condenser = X_CO2 * self.state.q_condenser * self._get_parasitic_power_fraction_condensing() # (W)


    def _update_pump_state(self) -> None:

        eta = self.specs.eta_pump
        X_CO2 = self._X_CO2

        dP_pump = self.get_dP_pump()
        P_pump_outlet = self.condensation_pressure + dP_pump

        h_pump_inlet = self.state.inlet_fluid_pump.H
        h_pump_outlet = self.state.inlet_fluid_pump.H
        if dP_pump > 0:
            try:
                self.state.outlet_fluid_pump.updatePS(P=P_pump_outlet, S=self.state.inlet_fluid_pump.S)
            except:
                logging.warning(f"Failed to update fluid state with PS. Updating with PT instead.")
                self.state.outlet_fluid_pump.updatePT(P=P_pump_outlet, T=self.state.inlet_fluid_pump.T)
            h_pump_outlet = h_pump_inlet + (self.state.outlet_fluid_pump.H - h_pump_inlet) / eta

        self.state.w_pump = -1.0 * X_CO2 *  self.state.mass_rate * (h_pump_outlet - h_pump_inlet)

        P_inj_inlet = P_pump_outlet + min(0., dP_pump) # if dP_pump <0, then choke.
        try:
            self.state.outlet_fluid.updateHP(H=h_pump_outlet, P=P_inj_inlet)
        except:
            logging.warning(f"Failed to update fluid state with HP. Updating with PT instead.")
            self.state.outlet_fluid.updatePT(P=P_inj_inlet, T=self.state.outlet_fluid_pump.T)

    def _update_net_state(self) -> None:
        self.state.w_net = self.state.w_turbine + self.state.w_cooler + self.state.w_condenser + self.state.w_pump


    def init_state(self, P: float=None, T: float=None) -> None:
        """
        direct CO2 thermosiphon system:
            production_well - turbine - condenser - pump - injection_well
        """

        self.state = SurfaceStateCPGNative()
        if P != None and T != None:
            self.state.inlet_fluid = FluidState.withPT(self._fluid_name, P, T)

        self.state.mass_rate = self.specs.mass_flow_rate

        self.state.outlet_fluid_turbine = FluidState.withQT(self._fluid_name, Q=1.0, T=self._condensation_temperature)

        self.state.outlet_fluid_condenser = FluidState.withQT(self._fluid_name, Q=0.0, T=self._condensation_temperature)
        self.condensation_pressure = self.state.outlet_fluid_condenser.P + self.specs.condensation_pressure_offset
        self.condenser_saturated_vapor_h = FluidState.withPQ(self._fluid_name, Q=1.0, P=self.condensation_pressure).H
        self.condenser_saturated_liquid_h = FluidState.withPQ(self._fluid_name, Q=0.0, P=self.condensation_pressure).H

        self.state.inlet_fluid_pump = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        self.state.outlet_fluid_pump = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)

        self.state.outlet_fluid = FluidState.copy(self.state.outlet_fluid_pump)


    def overwrite_pump_state(self) -> None:

        self._update_pump_state()

        self._update_net_state()

        self.update_outlet_streams()


    def update(self) -> None:

        # self.update_inlet_state()

        self._update_turbine_power()

        self._update_condenser_state()

        self._update_pump_state()

        self._update_net_state()

        self.update_outlet_streams()


    def update_dP_pump(self, val) -> None:
        self.state._dP_pump = val

    def get_dP_pump(self) -> float:
        return self.state._dP_pump
