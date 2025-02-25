from tango.units.native.surface.base import *
# import pexpect
import csv
from tango.units.dataclasses import SurfaceSpecsCPGTESPy
from tango.units.native.surface.tespy.tespy_input_adapter import *


class SurfaceUnitCPGTESPy(SurfaceUnitNative):
    """TESPy power plant unit"""
    def __init__(self, id: str, specs: dict):
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsCPGTESPy.from_dict(self._process_specs(specs))
        self._specs_post_processor()
        self._initialize_attributes()
        self.init_stream_interface()

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self, P: float=None, T: float=None) -> None:
        # TODO: change the pressure temperature values!
        self.inlet_fluid = FluidState.withPT(self._fluid_name, 8000000, 300)
        self.mass_rate = self.specs.mass_flow_rate
        self.outlet_fluid = FluidState.copy(self.inlet_fluid)


    def process_stream(self) -> None:
        yaml_file_path = self.specs.yaml_file_path
        self.pp = PowerPlant(yaml_file_path, self.inlet_fluid.P/100000.0, self.inlet_fluid.T-273.15, self.mass_rate, {'CO2': 1})
        self._update_turbine_power()
        self._update_condenser_state()
        self._update_pump_state()
        self._update_net_state()

        return self.P_out, self.T_out, self.mass_rate

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _specs_post_processor(self) -> float:
        self._fluid_name = self.specs.fluid_name
        self._condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        self._X_CO2 = 1.0 if self._fluid_name == 'CO2' else 0.0 #TODO: implement something like state.inlet_fluid.X_CO2 for multphase flow
        self._set_mult()
        self._set_constants()


    def _initialize_attributes(self) -> float:
        self._dP_pump: float = 0.
        # TODO: the below initialization should be removed!
        self._condensation_temperature_range = 0
        self.q_preheater: float = 0.
        self.q_boiler: float = 0.
        self.q_desuperheater: float = 0.


    def _process_specs(self, specs) -> dict:
        return specs['common'] | specs['surface']


    def _update_turbine_power(self) -> None:
        self.w_turbine = -self.pp.components['turbine'].P.val


    def _update_condenser_state(self) -> None:
        X_CO2 = self._X_CO2
        self.q_cooler = X_CO2 * self.pp.components['cooler'].Q.val
        self.q_condenser = X_CO2 * self.pp.components['condenser'].Q.val
        self._condensation_temperature_range = self.pp.connections['turbine_condenser'].T.val - self.pp.connections['condenser_cooler'].T.val
        self.w_cooler = X_CO2 * self.q_cooler * self._get_parasitic_power_fraction_cooling() # (W)
        self.w_condenser = X_CO2 * self.q_condenser * self._get_parasitic_power_fraction_condensing() # (W)


    def _update_pump_state(self) -> None:
        X_CO2 = self._X_CO2
        self.P_out = self.pp.connections['pump_outlet'].p.val * 100000
        self.T_out = self.pp.connections['pump_outlet'].T.val + 273.15
        self.w_pump = X_CO2 * -self.pp.components['pump'].P.val

    def _update_net_state(self) -> None:
        self.w_net = self.w_turbine + self.w_cooler + self.w_condenser + self.w_pump
