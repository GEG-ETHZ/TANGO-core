from tango.units.native.surface.base import *
import csv
from tango.units.dataclasses import SurfaceSpecsCPGDWSIM


class SurfaceUnitCPGDWSIM(SurfaceUnitNative):
    r"""
    DWSIM Power Plant Unit for simulating surface operations with CO2 Plume Geothermal (CPG).

    This class interfaces with a DWSIM-based application to simulate power plant behavior,
    including turbine, condenser, and pump dynamics, leveraging external communication for simulation.

    Attributes:
        specs (SurfaceSpecsCPGDWSIM): Specifications for the surface power plant.
        _fluid_name (str): Name of the fluid used in the simulation.
        _local_script_path (str): Path to the local script for execution.
        _remote_ip (str): IP address of the remote machine for script execution.
        _remote_script_path (str): Path to the remote script on the server.
        _PP_csv_file (str): Path to the CSV file for output data.
        _remote_username (str): Username for SSH connection.
        w_net (float): Net power output (W).
    """
    def __init__(self, id: str, specs: dict):
        """
        Initializes a new instance of the SurfaceUnitCPGDWSIM class.

        Args:
            id (str): Identifier for the surface unit.
            specs (dict): Specifications for the surface power plant.
        """
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsCPGDWSIM.from_dict(self._process_specs(specs))
        self._specs_post_processor()
        self._initialize_attributes()
        self.init_stream_interface()

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self, P: float = None, T: float = None) -> None:
        """
        Initializes the stream interface with default or specified pressure and temperature.

        Args:
            P (float, optional): Pressure for the inlet fluid (Pa).
            T (float, optional): Temperature for the inlet fluid (K).
        """
        self.inlet_fluid = FluidState.withPT(self._fluid_name, 8000000, 300)
        self.mass_rate = self.specs.mass_flow_rate
        self.outlet_fluid = FluidState.copy(self.inlet_fluid)

    def process_stream(self) -> tuple:
        r"""
        Simulates the surface unit operations by interfacing with external scripts and updates states.

        Returns:
            tuple: Outlet pressure (Pa), outlet temperature (K), and mass rate (kg/s).
        """
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

    def _specs_post_processor(self) -> None:
        """
        Processes specifications and initializes internal properties.
        """
        self._fluid_name = self.specs.fluid_name
        self._condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        self._X_CO2 = 1.0 if self._fluid_name == 'CO2' else 0.0
        self._set_mult()
        self._set_constants()
        self._local_script_path = self.specs.local_script_path
        self._remote_ip = self.specs.remote_ip
        self._remote_script_path = self.specs.remote_script_path
        self._PP_csv_file = self.specs.PP_csv_file
        self._remote_username = self.specs.remote_username

    def _initialize_attributes(self) -> None:
        """
        Initializes additional attributes for internal calculations.
        """
        self._dP_pump = 0.0
        self._condensation_temperature_range = 0.0
        self.q_preheater = 0.0
        self.q_boiler = 0.0
        self.q_desuperheater = 0.0

    def _read_last_row(self, csv_file):
        """
        Reads the last row of a CSV file to retrieve simulation outputs.

        Args:
            csv_file (str): Path to the CSV file.
        """
        with open(csv_file, mode='r') as file:
            reader = csv.reader(file)
            data = list(reader)
            if len(data) > 1:
                last_row = data[-1]
                for header, value in zip(data[0], last_row):
                    globals()[header] = float(value)

    def _process_specs(self, specs) -> dict:
        """
        Combines common and surface-specific specifications.

        Args:
            specs (dict): Input specifications.

        Returns:
            dict: Merged specifications.
        """
        return specs['common'] | specs['surface']

    def _update_turbine_power(self) -> None:
        """
        Updates the turbine power using external simulation results.
        """
        self.w_turbine = w_turbine_DWSIM

    def _update_condenser_state(self) -> None:
        """
        Updates the condenser state using external simulation results.
        """
        X_CO2 = self._X_CO2
        self.q_cooler = X_CO2 * q_Cooler_DWSIM
        self.q_condenser = X_CO2 * q_Condenser_DWSIM
        self._condensation_temperature_range = T_Turbine_outlet_DWSIM - T_Condenser_outlet_DWSIM
        self.w_cooler = X_CO2 * self.q_cooler * self._get_parasitic_power_fraction_cooling()
        self.w_condenser = X_CO2 * self.q_condenser * self._get_parasitic_power_fraction_condensing()

    def _update_pump_state(self) -> None:
        """
        Updates the pump state using external simulation results.
        """
        X_CO2 = self._X_CO2
        self.P_out = P_Pump_outlet_DWSIM
        self.T_out = T_Pump_outlet_DWSIM
        self.w_pump = X_CO2 * w_Pump_DWSIM

    def _update_net_state(self) -> None:
        """
        Updates the net power output of the system.

        Formula:
            .. math::
                w_{{net}} = w_{{turbine}} + w_{{cooler}} + w_{{condenser}} + w_{{pump}}
        """
        self.w_net = self.w_turbine + self.w_cooler + self.w_condenser + self.w_pump

    def _windows_scp_communication(self, command):
        """
        Executes an SCP command to transfer files.

        Args:
            command (str): SCP command.
        """
        try:
            scp_child = pexpect.spawn(command)
            scp_child.expect('password:')
            scp_child.sendline("1")
            scp_child.expect(pexpect.EOF, timeout=300)
        except Exception as e:
            return str(e)

    def _windows_ssh_communication(self, command):
        """
        Executes an SSH command on a remote server.

        Args:
            command (str): SSH command.
        """
        try:
            ssh_child = pexpect.spawn(command)
            ssh_child.expect('password:')
            ssh_child.sendline("1")
            ssh_child.expect(pexpect.EOF, timeout=300)
            ssh_child.before.decode()
        except Exception as e:
            return str(e)
