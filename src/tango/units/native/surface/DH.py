import logging

from tango.units.dataclasses import CommonSpecs
from tango.units.native.surface.base import *
from dataclasses import dataclass

@dataclass
class SurfaceSpecsDHNative(CommonSpecs):
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


class SurfaceUnitDHNative(SurfaceUnitNative):

    """The power plant unit based on Adams et al. (2015)."""
    def __init__(self, id: str, specs: dict):
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsDHNative.from_dict(self._process_specs(specs))
        self._specs_post_processor()
        self._initialize_attributes()
        self.init_stream_interface()
        self.something = 9000000

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self, P: float=None, T: float=None) -> None:
        """
        direct CO2 thermosiphon system:
            production_well - turbine - condenser - pump - injection_well
        """
        if P != None and T != None:
            self.inlet_fluid = FluidState.withPT(self._fluid_name, P, T)

        self.mass_rate = self.specs.mass_flow_rate
        # TODO: Is it really necessary to do the below calculations?
        #------------------------------------------------------------
        self.outlet_fluid_turbine = FluidState.withQT(self._fluid_name, Q=1.0, T=self._condensation_temperature)
        self.outlet_fluid_condenser = FluidState.withQT(self._fluid_name, Q=0.0, T=self._condensation_temperature)
        self.condensation_pressure = self.outlet_fluid_condenser.P + self.specs.condensation_pressure_offset
        self.condenser_saturated_vapor_h = FluidState.withPQ(self._fluid_name, Q=1.0, P=self.condensation_pressure).H
        self.condenser_saturated_liquid_h = FluidState.withPQ(self._fluid_name, Q=0.0, P=self.condensation_pressure).H
        self.inlet_fluid_pump = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        self.outlet_fluid_pump = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        # print( 'self.condensation_pressure, self._condensation_temperature',  self.condensation_pressure, self._condensation_temperature)
        # self.inlet_fluid_pump = FluidState.withPT(self._fluid_name,  5953084.845609539, 295.15)
        self.inlet_fluid_pump_test = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        self.outlet_fluid_pump_ideal = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        #------------------------------------------------------------
        self.outlet_fluid = FluidState.copy(self.outlet_fluid_pump)


    def process_stream(self) -> None:
        self._update_turbine_power()
        self._update_condenser_state()
        self._update_pump_state()
        self._update_net_state()

        print('\n')
        print(f'pp inlet -> P = {self.inlet_fluid.P}, T = {self.inlet_fluid.T}, H = {self.inlet_fluid.H}')
        print(f'pp outlet -> P = {self.outlet_fluid.P}, T = {self.outlet_fluid.T}, H = {self.outlet_fluid.H}, mr = {self.mass_rate}, , Pow = {self.w_turbine}')

        return self.P_out, self.T_out, self.mass_rate
        # return 10000000, 310, 10

    # -------------------------------------- data storing Functions -------------------------------------- #
    # These PUBLIC functions are specific to native CPG units. They will be called by the native
    # orchestrator for iterative computations. Please don't set them for external CPG units, as they
    # will not be called by the native orchestrator, and the solution is not iterative.

    def update_dP_pump(self, val) -> None:
        self._dP_pump = val


    def get_dP_pump(self) -> float:
        return self._dP_pump

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _specs_post_processor(self) -> float:
        self._fluid_name = self.specs.fluid_name
        self._condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        self._X_CO2 = 1.0 if self._fluid_name == 'CO2' else 0.0 #TODO: implement something like inlet_fluid.X_CO2 for multphase flow
        self._set_mult()
        self._set_constants()


    def _initialize_attributes(self) -> float:
        self._dP_pump: float = 16000000.
        # TODO: the below initialization should be removed!
        self._condensation_temperature_range = 0
        self.q_preheater: float = 0.
        self.q_boiler: float = 0.
        self.q_desuperheater: float = 0.


    def _process_specs(self, specs) -> dict:
        return specs['common'] | specs['surface']


    def _update_turbine_power(self) -> None:
        self.outlet_fluid_turbine.updatePS(P = self.condensation_pressure, S = self.inlet_fluid.S)
        # print(self.condensation_pressure, self.inlet_fluid.S)
        # print('self.outlet_fluid_turbine.H', self.outlet_fluid_turbine.H)
        # print('self.inlet_fluid.H', self.inlet_fluid.H)

        hs_outlet = self.outlet_fluid_turbine.H # (J/kg)
        h_inlet = self.inlet_fluid.H            # (J/kg)
        eta = self.specs.eta_turbine             # (-)
        X_CO2 = self._X_CO2

        # self.w_turbine = X_CO2 * self.mass_rate * eta * (h_inlet - hs_outlet) # (W)
        # self.w_turbine = self.mass_rate * (self.inlet_fluid.H - 249948)
        # print(self.w_turbine)


    def _update_condenser_state(self) -> None:

        hs_outlet = self.outlet_fluid_turbine.H  # Ideal (eta=1.0) enthalpy of outlet fluid (J/kg)
        h_inlet = self.inlet_fluid.H  # (J/kg)
        X_CO2 = self._X_CO2
        eta = self.specs.eta_turbine  # (-)
        h_saturated_vapor = self.condenser_saturated_vapor_h # (J/kg)
        h_condensed = self.condenser_saturated_liquid_h # (J/kg)
        h_turbine_outlet = h_inlet - eta * (h_inlet - hs_outlet) # (J/kg)

        self.q_cooler = 0. # (W)
        self.q_condenser = 0 # self.mass_rate * (h_condensed - h_turbine_outlet) # (W)
        # if h_turbine_outlet > h_saturated_vapor: # desuperheating needed
        #     self.q_cooler = self.mass_rate * (h_saturated_vapor - h_turbine_outlet)
        #     self.q_condenser = self.mass_rate * (h_condensed - h_saturated_vapor)
        #     T_turbine_outlet = FluidState.withHP(self._fluid_name, h_turbine_outlet, self.condensation_pressure).T
        #     self._condensation_temperature_range = T_turbine_outlet - self._condensation_temperature

        self.w_cooler = 0 # X_CO2 * self.q_cooler * self._get_parasitic_power_fraction_cooling() # (W)
        self.w_condenser = 0 # X_CO2 * self.q_condenser * self._get_parasitic_power_fraction_condensing() # (W)


    def _update_pump_state(self) -> None:

        eta = self.specs.eta_pump
        self.inlet_fluid_pump_test.updatePT(P=self.inlet_fluid.P * 0.9, T=295.15)
        fracing_limit_P = self.something
        if (fracing_limit_P < self.inlet_fluid.P * 0.9):
            self.outlet_fluid_pump.updatePT(P=fracing_limit_P, T=295.15)
            self.T_out = 295.15
            self.P_out = fracing_limit_P
            # self.w_turbine = self.mass_rate*(self.inlet_fluid.H - self.outlet_fluid_pump.H)
            self.w_pump = 0.0
        else:
            self.outlet_fluid_pump_ideal.updatePS(P=fracing_limit_P, S=self.inlet_fluid_pump_test.S)
            h_pump_outlet = self.inlet_fluid_pump_test.H + (self.outlet_fluid_pump_ideal.H - self.inlet_fluid_pump_test.H) / eta
            self.outlet_fluid_pump.updateHP(h_pump_outlet, P=fracing_limit_P)
            self.P_out = fracing_limit_P
            self.T_out = self.outlet_fluid_pump.T
            print('check here')
            print(self.inlet_fluid_pump_test.P, self.inlet_fluid_pump_test.T, self.inlet_fluid_pump_test.H)
            print(self.outlet_fluid_pump.P, self.outlet_fluid_pump.T, self.outlet_fluid_pump.H)
            self.w_pump = -1.0 * self.mass_rate * (h_pump_outlet - self.inlet_fluid_pump_test.H)

        self.dT_LMTD_preheater = 5
        self.q_preheater = self.mass_rate*(self.inlet_fluid.H - self.inlet_fluid_pump.H)
        # print('pth', self.inlet_fluid.P, self.inlet_fluid.T, self.inlet_fluid.H)
        # print(self.outlet_fluid_pump.P, self.outlet_fluid_pump.T, self.outlet_fluid_pump.H)
        self.w_turbine = self.mass_rate*(self.inlet_fluid.H - self.inlet_fluid_pump_test.H)
        self.q_boiler = 0
        self.dT_LMTD_boiler = 1000000000
        # print('self.inlet_fluid.P * 0.9 = ', self.inlet_fluid.P * 0.9, 'injection_P = ', self.something)
        # self.w_pump2 = -1.0 * X_CO2 *  self.mass_rate * (302376 - self.inlet_fluid.H)
        print('self.inlet_fluid.P-self.P_out = ', self.inlet_fluid.P-self.P_out)


    def _update_net_state(self) -> None:
        self.w_net = self.w_turbine + self.w_cooler + self.w_condenser + self.w_pump
