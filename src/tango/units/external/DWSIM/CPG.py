from tango.units.native.surface.base import *
import pexpect
import csv
from tango.units.native.common import SurfaceSpecsCPGDWSIM


class SurfaceStateCPGDWSIM():
    def __init__(self):
        # SurfaceState.__init__(self)
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


class SurfaceUnitCPGDWSIM(SurfaceUnitNative):
    """DWSIM power plant unit"""
    def __init__(self, id: str, specs: dict):
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsCPGDWSIM.from_dict(self._process_specs(specs))
        self._fluid_name = self.specs.fluid_name
        self._condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        self._condensation_temperature_range = 0
        self._X_CO2 = 1.0 if self._fluid_name == 'CO2' else 0.0 #TODO: implement something like state.inlet_fluid.X_CO2 for multphase flow
        self._set_mult()
        self._set_constants()

        self.init_state()

        self.local_script_path = self.specs.local_script_path
        self.remote_ip = self.specs.remote_ip
        self.remote_script_path = self.specs.remote_script_path
        self.PP_csv_file = self.specs.PP_csv_file
        self.remote_username = self.specs.remote_username


    def read_last_row(self, csv_file):
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
        self.state.w_turbine = (w_turbine_DWSIM)


    def _update_condenser_state(self) -> None:
        X_CO2 = self._X_CO2
        self.state.q_cooler = X_CO2 * q_Cooler_DWSIM
        self.state.q_condenser = X_CO2 * q_Condenser_DWSIM
        self._condensation_temperature_range = T_Turbine_outlet_DWSIM - T_Condenser_outlet_DWSIM
        self.state.w_cooler = X_CO2 * self.state.q_cooler * self._get_parasitic_power_fraction_cooling() # (W)
        self.state.w_condenser = X_CO2 * self.state.q_condenser * self._get_parasitic_power_fraction_condensing() # (W)


    def _update_pump_state(self) -> None:
        X_CO2 = self._X_CO2
        self.outlet_fluid.updatePT(P_Pump_outlet_DWSIM, T_Pump_outlet_DWSIM)
        self.ppp = P_Pump_outlet_DWSIM
        self.ttt = T_Pump_outlet_DWSIM
        self.state.w_pump = X_CO2 * w_Pump_DWSIM

    def _update_net_state(self) -> None:
        self.state.w_net = self.state.w_turbine + self.state.w_cooler + self.state.w_condenser + self.state.w_pump


    def init_state(self, P: float=None, T: float=None) -> None:
        """
        direct CO2 thermosiphon system:
            production_well - turbine - condenser - pump - injection_well
        """
        self.state = SurfaceStateCPGDWSIM()
        # To Do: change the pressure temperature values!
        self.inlet_fluid = FluidState.withPT(self._fluid_name, 8000000, 300)
        self.mass_rate = self.specs.mass_flow_rate
        self.outlet_fluid = FluidState.copy(self.inlet_fluid)

    def windows_scp_communication(self, command):
        try:
            cmd = command
            scp_child = pexpect.spawn(cmd)
            # To DO: ssh connection without password
            scp_child.expect('password:')
            scp_child.sendline("1")
            scp_child.expect(pexpect.EOF, timeout=300)
        except Exception as e:
            return str(e)

    def windows_ssh_communication(self, command):
        try:
            ssh_child = pexpect.spawn(command)
            ssh_child.expect('password:')
            ssh_child.sendline("1")
            ssh_child.expect(pexpect.EOF, timeout=300)
            ssh_child.before.decode()
        except Exception as e:
            return str(e)


    def process_stream(self) -> None:
        try:
            scp_command = f"scp {self.local_script_path} {self.remote_username}@{self.remote_ip}:{self.remote_script_path}"
            ssh_command = f'ssh {self.remote_username}@{self.remote_ip} "python {self.remote_script_path} {self.inlet_fluid.P} {self.inlet_fluid.T} {self.mass_rate}"'
            self.windows_scp_communication(scp_command)
            self.windows_ssh_communication(ssh_command)
            self.read_last_row(self.PP_csv_file)
        except pexpect.ExceptionPexpect as pe:
            print(f"An error occurred with pexpect: {pe}")

        self._update_turbine_power()
        self._update_condenser_state()
        self._update_pump_state()
        self._update_net_state()
        self.update_outlet_streams()
