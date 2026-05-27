import os
import sys

import pythoncom

pythoncom.CoInitialize()
import csv

import clr
from System import Environment
from System.IO import Directory, Path


class DWSIMSimulationModifier:
    r"""A class to modify and execute DWSIM simulations, extract data, and save results.

    Attributes:
        _csv_file (str): Path to the CSV file for storing results.
        _interf (object): Automation interface for interacting with DWSIM.
        _flowsheet (object): The loaded DWSIM flowsheet.

    Methods:
        _add_dwsim_references: Adds references to required DWSIM libraries.
        _DWSIM_inputs: Updates the DWSIM simulation with new input conditions.
        _DWSIM_runner: Runs the simulation with specified inputs.
        _DWSIM_data_extractor: Extracts specified objects from the DWSIM flowsheet.
        _save_modified_simulation: Saves the modified flowsheet.
        _write_row: Writes a row of data to the CSV file.
        variables_to_strings: Converts variables to their string representations.
        _append_variables_to_csv: Appends variable names to the CSV header.
        get_inputs_from_args: Parses input arguments for pressure, temperature, and mass rate.
        _extract_simulation_data: Extracts key simulation data from the flowsheet.
        _process_data_and_write_to_csv: Processes extracted data and writes it to the CSV.
        process_and_save_data: Executes the workflow for running the simulation, extracting data, and saving results.

    """

    def __init__(self, dwsim_path, simulation_file_path, csv_file):
        """Initializes the DWSIMSimulationModifier class.

        Args:
            dwsim_path (str): Path to the DWSIM installation.
            simulation_file_path (str): Path to the DWSIM simulation file.
            csv_file (str): Path to the CSV file for saving results.

        """
        self._csv_file = csv_file
        self._add_dwsim_references(dwsim_path)

        from DWSIM.Automation import Automation3

        Directory.SetCurrentDirectory(dwsim_path)
        self._interf = Automation3()
        self._flowsheet = self._interf.LoadFlowsheet(simulation_file_path)

    def _add_dwsim_references(self, dwsim_path):
        """Adds references to required DWSIM libraries.

        Args:
            dwsim_path (str): Path to the DWSIM installation directory.

        """
        clr.AddReference(dwsim_path + "CapeOpen.dll")
        clr.AddReference(dwsim_path + "DWSIM.Automation.dll")
        clr.AddReference(dwsim_path + "DWSIM.Interfaces.dll")
        clr.AddReference(dwsim_path + "DWSIM.GlobalSettings.dll")
        clr.AddReference(dwsim_path + "DWSIM.SharedClasses.dll")
        clr.AddReference(dwsim_path + "DWSIM.Thermodynamics.dll")
        clr.AddReference(dwsim_path + "DWSIM.UnitOperations.dll")
        clr.AddReference(dwsim_path + "DWSIM.Inspector.dll")
        clr.AddReference(dwsim_path + "System.Buffers.dll")
        clr.AddReference(dwsim_path + "DWSIM.Thermodynamics.ThermoC.dll")

    def _DWSIM_inputs(self, pressure, temperature, mass_rate):
        """Updates the DWSIM simulation inputs for the turbine inlet.

        Args:
            pressure (float): Pressure at the turbine inlet (Pa).
            temperature (float): Temperature at the turbine inlet (K).
            mass_rate (float): Mass flow rate at the turbine inlet (kg/s).

        """
        pp_inlet_stream = self._flowsheet.GetObject("Turbine_inlet")
        inlet_stream_obj = pp_inlet_stream.GetAsObject()
        inlet_stream_obj.SetTemperature(temperature)
        inlet_stream_obj.SetPressure(pressure)
        inlet_stream_obj.SetMassFlow(mass_rate)

    def _DWSIM_runner(self, pressure, temperature, mass_rate):
        """Runs the DWSIM simulation with specified inputs.

        Args:
            pressure (float): Pressure at the turbine inlet (Pa).
            temperature (float): Temperature at the turbine inlet (K).
            mass_rate (float): Mass flow rate at the turbine inlet (kg/s).

        """
        self._DWSIM_inputs(pressure, temperature, mass_rate)
        self._interf.CalculateFlowsheet2(self._flowsheet)

    def _DWSIM_data_extractor(self, PP_object_name, new_class_name):
        """Extracts a specific object from the DWSIM flowsheet.

        Args:
            PP_object_name (str): Name of the object in the flowsheet.
            new_class_name (str): Name to assign the extracted object.

        """
        pp_object = self._flowsheet.GetObject(PP_object_name)
        setattr(self, new_class_name, pp_object.GetAsObject())

    def _save_modified_simulation(self, save_path):
        """Saves the modified DWSIM simulation to a specified path.

        Args:
            save_path (str): Path to save the modified simulation.

        """
        save_path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Desktop), save_path)
        self._interf.SaveFlowsheet(self._flowsheet, save_path, True)
        print("Modified simulation saved to:", save_path)

    def _write_row(self, row_data):
        """Writes a row of data to the CSV file.

        Args:
            row_data (list): Data row to write to the CSV file.

        """
        with open(self._csv_file, mode="a", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(row_data)

    def variables_to_strings(self, components):
        """Converts variables to their string representations.

        Args:
            components (list): List of components to convert.

        Returns:
            list: List of string representations of the variables.

        """
        variable_names = []
        for component in components:
            for name, value in globals().items():
                if value is component:
                    variable_names.append(name)
        return variable_names

    def _append_variables_to_csv(self, variables):
        """Appends variable names to the CSV file as a header.

        Args:
            variables (list): List of variable names.

        """
        if not os.path.exists(self._csv_file):
            with open(self._csv_file, mode="a", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(variables)

    def get_inputs_from_args(self):
        """Retrieves pressure, temperature, and mass rate inputs from command-line arguments.

        Returns:
            tuple: Pressure (Pa), temperature (K), and mass rate (kg/s).

        """
        if len(sys.argv) >= 4:
            pressure = float(sys.argv[1])
            temperature = float(sys.argv[2])
            mass_rate = float(sys.argv[3])
            return pressure, temperature, mass_rate
        else:
            print("Error: The required arguments (pressure, temperature and mass rate) are missing.")
            sys.exit(1)

    def _extract_simulation_data(self):
        """Extracts key data from the DWSIM simulation flowsheet."""
        self._DWSIM_data_extractor("Turbine_inlet", "TurbineInlet")
        self._DWSIM_data_extractor("Turbine", "Turbine")
        self._DWSIM_data_extractor("Turbine_outlet", "TurbineOutlet")
        self._DWSIM_data_extractor("Cooler", "Cooler")
        self._DWSIM_data_extractor("Cooler_outlet", "CoolerOutlet")
        self._DWSIM_data_extractor("Condenser", "Condenser")
        self._DWSIM_data_extractor("Condenser_outlet", "CondenserOutlet")
        self._DWSIM_data_extractor("Pump", "Pump")
        self._DWSIM_data_extractor("Pump_outlet", "PumpOutlet")

    def _process_data_and_write_to_csv(self):
        T_Turbine_inlet_DWSIM = self.TurbineInlet.GetTemperature()
        P_Turbine_inlet_DWSIM = self.TurbineInlet.GetPressure()

        w_turbine_DWSIM = 1000.0 * self.Turbine.GetPowerGeneratedOrConsumed()
        T_Turbine_outlet_DWSIM = self.TurbineOutlet.GetTemperature()
        P_Turbine_outlet_DWSIM = self.TurbineOutlet.GetPressure()

        q_Cooler_DWSIM = -1000.0 * self.Cooler.DeltaQ
        T_Cooler_outlet_DWSIM = self.CoolerOutlet.GetTemperature()
        P_Cooler_outlet_DWSIM = self.CoolerOutlet.GetPressure()

        q_Condenser_DWSIM = -1000.0 * self.Condenser.DeltaQ
        T_Condenser_outlet_DWSIM = self.CondenserOutlet.GetTemperature()
        P_Condenser_outlet_DWSIM = self.CondenserOutlet.GetPressure()

        w_Pump_DWSIM = 1000.0 * self.Pump.GetPowerGeneratedOrConsumed()
        T_Pump_outlet_DWSIM = self.PumpOutlet.GetTemperature()
        P_Pump_outlet_DWSIM = self.PumpOutlet.GetPressure()

        data_row = [
            T_Turbine_inlet_DWSIM,
            P_Turbine_inlet_DWSIM,
            w_turbine_DWSIM,
            T_Turbine_outlet_DWSIM,
            P_Turbine_outlet_DWSIM,
            q_Cooler_DWSIM,
            T_Cooler_outlet_DWSIM,
            P_Cooler_outlet_DWSIM,
            q_Condenser_DWSIM,
            T_Condenser_outlet_DWSIM,
            P_Condenser_outlet_DWSIM,
            w_Pump_DWSIM,
            T_Pump_outlet_DWSIM,
            P_Pump_outlet_DWSIM,
        ]

        variables = [
            "T_Turbine_inlet_DWSIM",
            "P_Turbine_inlet_DWSIM",
            "w_turbine_DWSIM",
            "T_Turbine_outlet_DWSIM",
            "P_Turbine_outlet_DWSIM",
            "q_Cooler_DWSIM",
            "T_Cooler_outlet_DWSIM",
            "P_Cooler_outlet_DWSIM",
            "q_Condenser_DWSIM",
            "T_Condenser_outlet_DWSIM",
            "P_Condenser_outlet_DWSIM",
            "w_Pump_DWSIM",
            "T_Pump_outlet_DWSIM",
            "P_Pump_outlet_DWSIM",
        ]

        self._append_variables_to_csv(variables)
        self._write_row(data_row)

    def process_and_save_data(self, pressure, temperature, mass_rate):
        self._DWSIM_runner(pressure, temperature, mass_rate)
        self._extract_simulation_data()
        self._save_modified_simulation("modified_simulation.dwxmz")
        self._process_data_and_write_to_csv()


dwsim_path = "C:\\Users\\Morteza\\AppData\\Local\\DWSIM\\"
simulation_file_path = Path.Combine(
    Environment.GetFolderPath(Environment.SpecialFolder.Desktop),
    "second.dwxmz",
)
csv_file = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Desktop), "data.csv")

simulation_modifier = DWSIMSimulationModifier(dwsim_path, simulation_file_path, csv_file)
pressure, temperature, mass_rate = simulation_modifier.get_inputs_from_args()
simulation_modifier.process_and_save_data(pressure, temperature, mass_rate)
