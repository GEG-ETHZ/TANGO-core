import logging

from tango.units.dataclasses import CommonSpecs
from tango.units.native.surface.base import *
from dataclasses import dataclass

import csv
import os

@dataclass
class SurfaceSpecsDHNative(CommonSpecs):
    r"""
    Represents the specifications for a surface power plant unit operating with direct heat exchange.

    Attributes:
        # pipe_diameter (float): Diameter of the pipe (m).
        # approach_temperature (float): Temperature difference between condensing and surface temperature (K).
        # condensation_pressure_offset (float): Offset for condensation pressure (Pa).
        # temperature_range (float): Difference between inlet and exit fluid temperatures (K).
        # eta_pump (float): Pump efficiency (-).
        # total_pipe_length (float): Total length of the pipes (m).
        # epsilon (float): Roughness of surface pipes (m). :no-index:
        # eta_turbine (float): Isentropic efficiency of the turbine (-).
        # cooling_tower_design (str): Design of the cooling tower ('CLOSED', 'OPEN').
        # cooling_mode (str): Cooling mode, either 'WET' or 'DRY'.

    Methods:
        __post_init__: Ensures required fields are initialized.
    """

    pipe_diameter: float = None  # (m)
    approach_temperature: float = None  # Temperature difference (K)
    condensation_pressure_offset: float = None  # (Pa)
    temperature_range: float = 0.0  # (K)
    eta_pump: float = 0.90  # Pump efficiency (-)
    total_pipe_length: float = None  # (m)
    epsilon: float = 55.e-6  # Roughness (m)
    eta_turbine: float = 0.78  # Turbine efficiency (-)
    cooling_tower_design: str = 'CLOSED'
    cooling_mode: str = 'WET'

    def __post_init__(self):
        """
        Validates that all required fields are initialized.

        Raises:
            RuntimeError: If a required field is not initialized.
        """
        required_fields = ['pipe_diameter', 'approach_temperature', 'condensation_pressure_offset']
        for field in required_fields:
            if getattr(self, field, None) is None:
                raise RuntimeError(f"Required parameter: {field} is not found.")

class SurfaceUnitDHNative(SurfaceUnitNative):
    r"""
    Represents a direct heat exchange power plant unit based on Adams et al. (2015).

    This class extends `SurfaceUnitNative` to support additional functionality specific to
    direct heat exchange systems, including CSV-driven flow rates and iterative pressure handling.

    Attributes:
        specs (SurfaceSpecsDHNative): Specifications for the surface power plant.
        iterative_inj_pressure (float): Initial injection pressure for iterations (Pa).
        iterative_inj_temperature (float): Initial injection temperature for iterations (K).
        reservoir_file_reader (bool): Whether to use a reservoir file reader.
        cooler_include (bool): Whether a cooler is included in the system.
        current_row (int): Current row index for CSV-driven flow rates.
        csv_data (list): Data from the CSV file if applicable.
    """

    def __init__(self, id: str, specs: dict):
        """
        Initializes a new instance of the SurfaceUnitDHNative class.

        Args:
            id (str): Identifier for the unit.
            specs (dict): Specifications for the unit.
        """
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsDHNative.from_dict(self._process_specs(specs))
        self._specs_post_processor()
        self.init_stream_interface()
        self.iterative_inj_pressure = 9_000_000  # Pa
        self.iterative_inj_temperature = 302.0  # K
        self.reservoir_file_reader = False
        self.cooler_include = False
        self.current_row = 0

        if self.specs.flow_rate_from_csv == 'yes':
            self.csv_data = self._read_csv_file()

    def init_stream_interface(self, P: float = None, T: float = None) -> None:
        """
        Initializes stream interfaces for a direct CO2 thermosiphon system.

        Args:
            P (float, optional): Initial pressure for the inlet fluid (Pa).
            T (float, optional): Initial temperature for the inlet fluid (K).

        System Overview:
            Production Well -> Turbine -> Condenser -> Pump -> Injection Well
        """
        if P is not None and T is not None:
            self.inlet_fluid = FluidState.withPT(self._fluid_name, P, T)

        # self.mass_rate = self.specs.mass_flow_rate
        self.mass_rate = self.specs.mass_flow_rate * self.specs.well_pattern_dimens[0] * self.specs.well_pattern_dimens[1] / self.specs.num_pp

        self.outlet_fluid_condenser = FluidState.withQT(self._fluid_name, Q=0.0, T=self._condensation_temperature)
        self.condensation_pressure = self.outlet_fluid_condenser.P + self.specs.condensation_pressure_offset
        self.inlet_fluid_pump = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        self.outlet_fluid_pump = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        self.inlet_fluid_pump_test = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        self.outlet_fluid_pump_ideal = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        self.outlet_fluid = FluidState.copy(self.outlet_fluid_pump)

    def process_stream(self) -> None:
        """
        Processes the stream to update system states and outputs.

        Updates:
            - Heat exchanger states.
            - Net power and mass flow rates.
        """
        self.mass_rate = self.specs.mass_flow_rate * self.specs.well_pattern_dimens[0] * self.specs.well_pattern_dimens[1] / self.specs.num_pp
        if self.specs.flow_rate_from_csv == 'yes' and self.current_row < len(self.csv_data):
            row = self.csv_data[self.current_row]
            self.mass_rate = float(row[1])

        self._update_heat_exchanger_state()
        self._update_net_state()

        print('\n')
        print(f'pp inlet -> P = {self.inlet_fluid.P}, T = {self.inlet_fluid.T}, H = {self.inlet_fluid.H}')
        print(f'pp outlet -> P = {self.outlet_fluid.P}, T = {self.outlet_fluid.T}, H = {self.outlet_fluid.H}, mr = {self.mass_rate}, Pow = {self.w_turbine}')

        return self.P_out, self.T_out, self.specs.mass_flow_rate

    def _read_csv_file(self):
        """
        Reads flow rate data from a CSV file.

        Returns:
            list: Parsed CSV data.

        Raises:
            FileNotFoundError: If the CSV file does not exist.
        """
        file_path = self.specs.flow_rate_file
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"The CSV file does not exist at {file_path}")

        with open(file_path, 'r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row
            return list(reader)

    def _specs_post_processor(self) -> None:
        """
        Processes specifications to initialize system properties.
        """
        self._fluid_name = self.specs.fluid_name
        self._condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        self._set_mult()

    def _process_specs(self, specs) -> dict:
        """
        Combines common and surface-specific specifications.

        Args:
            specs (dict): Input specifications.

        Returns:
            dict: Merged specifications.
        """
        return specs['common'] | specs['surface']

    def _update_heat_exchanger_state(self) -> None:
        """
        Updates the state of the heat exchanger.
        """
        eta = self.specs.eta_pump
        self.inlet_fluid_pump_test.updatePT(P=self.inlet_fluid.P * 0.9, T=295.15)
        fracing_limit_P = self.iterative_inj_pressure

        if fracing_limit_P < self.inlet_fluid.P * 0.9:
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

        self.w_turbine = self.mass_rate * (self.inlet_fluid.H - self.inlet_fluid_pump_test.H)

    def _update_net_state(self) -> None:
        """
        Updates the net state of the system.
        """
        self.w_net = self.w_turbine + self.w_pump

