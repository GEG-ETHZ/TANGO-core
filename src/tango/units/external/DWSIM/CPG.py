from tango.units.native.surface.base import *
import pexpect
import csv
from tango.units.native.common import SurfaceSpecsCPGDWSIM


class SurfaceUnitCPGDWSIM(SurfaceUnitNative):
    """DWSIM power plant unit"""
    def __init__(self, id: str, specs: dict):
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsCPGDWSIM.from_dict(self._process_specs(specs))
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
        try:
            scp_command = f"scp {self._local_script_path} {self._remote_username}@{self._remote_ip}:{self._remote_script_path}"
            ssh_command = f'ssh {self._remote_username}@{self._remote_ip} "python {self._remote_script_path} {self.inlet_fluid.P} {self.inlet_fluid.T} {self.mass_rate}"'
            self._windows_scp_communication(scp_command)
            self._windows_ssh_communication(ssh_command)
            self._read_last_row(self._PP_csv_file)
        except pexpect.ExceptionPexpect as pe:
            print(f"An error occurred with pexpect: {pe}")

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
        self._local_script_path = self.specs.local_script_path
        self._remote_ip = self.specs.remote_ip
        self._remote_script_path = self.specs.remote_script_path
        self._PP_csv_file = self.specs.PP_csv_file
        self._remote_username = self.specs.remote_username


    def _initialize_attributes(self) -> float:
        self._dP_pump: float = 0.
        # TODO: the below initialization should be removed!
        self._condensation_temperature_range = 0
        self.q_preheater: float = 0.
        self.q_boiler: float = 0.
        self.q_desuperheater: float = 0.


    def _read_last_row(self, csv_file):
        with open(csv_file, mode='r') as file:
            reader = csv.reader(file)
            data = list(reader)
            if len(data) > 1:
                last_row = data[-1]
                for header, value in zip(data[0], last_row):
                    globals()[header] = float(value)


    def _process_specs(self, specs) -> dict:
        return specs['common'] | specs['surface']


    def _update_turbine_power(self) -> None:
        self.w_turbine = (w_turbine_DWSIM)


    def _update_condenser_state(self) -> None:
        X_CO2 = self._X_CO2
        self.q_cooler = X_CO2 * q_Cooler_DWSIM
        self.q_condenser = X_CO2 * q_Condenser_DWSIM
        self._condensation_temperature_range = T_Turbine_outlet_DWSIM - T_Condenser_outlet_DWSIM
        self.w_cooler = X_CO2 * self.q_cooler * self._get_parasitic_power_fraction_cooling() # (W)
        self.w_condenser = X_CO2 * self.q_condenser * self._get_parasitic_power_fraction_condensing() # (W)


    def _update_pump_state(self) -> None:
        X_CO2 = self._X_CO2
        self.P_out = P_Pump_outlet_DWSIM
        self.T_out = T_Pump_outlet_DWSIM
        self.w_pump = X_CO2 * w_Pump_DWSIM

    def _update_net_state(self) -> None:
        self.w_net = self.w_turbine + self.w_cooler + self.w_condenser + self.w_pump


    def _windows_scp_communication(self, command):
        try:
            cmd = command
            scp_child = pexpect.spawn(cmd)
            # TODO: ssh connection without password
            scp_child.expect('password:')
            scp_child.sendline("1")
            scp_child.expect(pexpect.EOF, timeout=300)
        except Exception as e:
            return str(e)

    def _windows_ssh_communication(self, command):
        try:
            ssh_child = pexpect.spawn(command)
            ssh_child.expect('password:')
            ssh_child.sendline("1")
            ssh_child.expect(pexpect.EOF, timeout=300)
            ssh_child.before.decode()
        except Exception as e:
            return str(e)
