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
        self.init_stream_interface()
        self.iterative_inj_pressure = 9000000

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self, P: float=None, T: float=None) -> None:
        """
        direct CO2 thermosiphon system:
            production_well - turbine - condenser - pump - injection_well
        """
        if P != None and T != None:
            self.inlet_fluid = FluidState.withPT(self._fluid_name, P, T)

        self.mass_rate = self.specs.mass_flow_rate

        #------------------------------------------------------------
        self.outlet_fluid_condenser = FluidState.withQT(self._fluid_name, Q=0.0, T=self._condensation_temperature)
        self.condensation_pressure = self.outlet_fluid_condenser.P + self.specs.condensation_pressure_offset
        self.inlet_fluid_pump = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        self.outlet_fluid_pump = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        self.inlet_fluid_pump_test = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        self.outlet_fluid_pump_ideal = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        self.outlet_fluid = FluidState.copy(self.outlet_fluid_pump)
        #------------------------------------------------------------


    def process_stream(self) -> None:
        self._update_heat_exchanger_state()
        self._update_net_state()

        logging.info('\n')
        logging.info(f'pp inlet -> P = {self.inlet_fluid.P}, T = {self.inlet_fluid.T}, H = {self.inlet_fluid.H}')
        logging.info(f'pp outlet -> P = {self.outlet_fluid.P}, T = {self.outlet_fluid.T}, H = {self.outlet_fluid.H}, mr = {self.mass_rate}, , Pow = {self.w_turbine}')

        return self.P_out, self.T_out, self.mass_rate

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _specs_post_processor(self) -> float:
        self._fluid_name = self.specs.fluid_name
        self._condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        # self._X_CO2 = 1.0 if self._fluid_name == 'CO2' else 0.0 #TODO: implement something like inlet_fluid.X_CO2 for multphase flow
        self._set_mult()

    def _process_specs(self, specs) -> dict:
        return specs['common'] | specs['surface']

    def _update_heat_exchanger_state(self) -> None:

        eta = self.specs.eta_pump
        self.inlet_fluid_pump_test.updatePT(P=self.inlet_fluid.P * 0.9, T=295.15)
        fracing_limit_P = self.iterative_inj_pressure
        if (fracing_limit_P < self.inlet_fluid.P * 0.9):
            self.outlet_fluid_pump.updatePT(P=fracing_limit_P, T=295.15)
            self.T_out = 295.15
            self.P_out = fracing_limit_P
            self.w_pump = 0.0
        else:
            self.outlet_fluid_pump_ideal.updatePS(P=fracing_limit_P, S=self.inlet_fluid_pump_test.S)
            h_pump_outlet = self.inlet_fluid_pump_test.H + (self.outlet_fluid_pump_ideal.H - self.inlet_fluid_pump_test.H) / eta
            self.outlet_fluid_pump.updateHP(h_pump_outlet, P=fracing_limit_P)
            self.P_out = fracing_limit_P
            self.T_out = self.outlet_fluid_pump.T
            self.w_pump = -1.0 * self.mass_rate * (h_pump_outlet - self.inlet_fluid_pump_test.H)

        self.w_turbine = self.mass_rate*(self.inlet_fluid.H - self.inlet_fluid_pump_test.H)

    def _update_net_state(self) -> None:
        # They have the same unit, but their summation is meaningless. should be revised later!
        self.w_net = self.w_turbine + self.w_pump
