import sys
import os
import pythoncom
pythoncom.CoInitialize()
import clr
from System.IO import Directory, Path, File
from System import String, Environment
import csv


class DWSIMSimulationModifier:
    def __init__(self, dwsim_path, simulation_file_path, csv_file):
        self.csv_file = csv_file
        self.add_dwsim_references(dwsim_path)

        from DWSIM.Interfaces.Enums.GraphicObjects import ObjectType
        from DWSIM.Thermodynamics import Streams, PropertyPackages
        from DWSIM.UnitOperations import UnitOperations
        from DWSIM.Automation import Automation3
        from DWSIM.GlobalSettings import Settings

        Directory.SetCurrentDirectory(dwsim_path)
        self.interf = Automation3()
        self.flowsheet = self.interf.LoadFlowsheet(simulation_file_path)


    def add_dwsim_references(self, dwsim_path):
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


    def DWSIM_inputs(self, pressure, temperature, mass_rate):
        pp_inlet_stream = self.flowsheet.GetObject("Turbine_inlet")
        inlet_stream_obj = pp_inlet_stream.GetAsObject()
        inlet_stream_obj.SetTemperature(temperature)
        inlet_stream_obj.SetPressure(pressure)
        inlet_stream_obj.SetMassFlow(mass_rate)


    def DWSIM_runner(self, pressure, temperature, mass_rate):
        self.DWSIM_inputs(pressure, temperature, mass_rate)
        self.interf.CalculateFlowsheet2(self.flowsheet)


    def DWSIM_data_extractor(self, PP_object_name, new_class_name):
        pp_object = self.flowsheet.GetObject(PP_object_name)
        setattr(self, new_class_name, pp_object.GetAsObject())


    def save_modified_simulation(self, save_path):
        save_path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Desktop), save_path)
        self.interf.SaveFlowsheet(self.flowsheet, save_path, True)
        print("Modified simulation saved to:", save_path)


    def write_row(self, row_data):
        with open(self.csv_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(row_data)


    def variables_to_strings(self, components):
        variable_names = []
        for component in components:
            for name, value in globals().items():
                if value is component:
                    variable_names.append(name)
        return variable_names


    def append_variables_to_csv(self, variables):
        if not os.path.exists(self.csv_file):
            with open(self.csv_file, mode='a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(variables)


    def get_inputs_from_args(self):
        if len(sys.argv) >= 4:
            pressure = float(sys.argv[1])
            temperature = float(sys.argv[2])
            mass_rate = float(sys.argv[3])
            return pressure, temperature, mass_rate
        else:
            print("Error: The required arguments (pressure, temperature and mass rate) are missing.")
            sys.exit(1)


    def extract_simulation_data(self):
        self.DWSIM_data_extractor("Turbine_inlet", "TurbineInlet")
        self.DWSIM_data_extractor("Turbine", "Turbine")
        self.DWSIM_data_extractor("Turbine_outlet", "TurbineOutlet")
        self.DWSIM_data_extractor("Cooler", "Cooler")
        self.DWSIM_data_extractor("Cooler_outlet", "CoolerOutlet")
        self.DWSIM_data_extractor("Condenser", "Condenser")
        self.DWSIM_data_extractor("Condenser_outlet", "CondenserOutlet")
        self.DWSIM_data_extractor("Pump", "Pump")
        self.DWSIM_data_extractor("Pump_outlet", "PumpOutlet")


    def process_data_and_write_to_csv(self):
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

        data_row = [T_Turbine_inlet_DWSIM, P_Turbine_inlet_DWSIM, w_turbine_DWSIM,
                     T_Turbine_outlet_DWSIM, P_Turbine_outlet_DWSIM, q_Cooler_DWSIM,
                     T_Cooler_outlet_DWSIM, P_Cooler_outlet_DWSIM, q_Condenser_DWSIM,
                     T_Condenser_outlet_DWSIM, P_Condenser_outlet_DWSIM, w_Pump_DWSIM,
                     T_Pump_outlet_DWSIM, P_Pump_outlet_DWSIM]

        variables = ['T_Turbine_inlet_DWSIM', 'P_Turbine_inlet_DWSIM', 'w_turbine_DWSIM',
                     'T_Turbine_outlet_DWSIM', 'P_Turbine_outlet_DWSIM', 'q_Cooler_DWSIM',
                     'T_Cooler_outlet_DWSIM', 'P_Cooler_outlet_DWSIM', 'q_Condenser_DWSIM',
                     'T_Condenser_outlet_DWSIM', 'P_Condenser_outlet_DWSIM', 'w_Pump_DWSIM',
                     'T_Pump_outlet_DWSIM', 'P_Pump_outlet_DWSIM']

        self.append_variables_to_csv(variables)
        self.write_row(data_row)


    def process_and_save_data(self, pressure, temperature, mass_rate):
        self.DWSIM_runner(pressure, temperature, mass_rate)
        self.extract_simulation_data()
        self.save_modified_simulation("modified_simulation.dwxmz")
        self.process_data_and_write_to_csv()


dwsim_path = "C:\\Users\\Morteza\\AppData\\Local\\DWSIM\\"
simulation_file_path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Desktop), "second.dwxmz")
csv_file = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Desktop), "data.csv")

simulation_modifier = DWSIMSimulationModifier(dwsim_path, simulation_file_path, csv_file)
pressure, temperature, mass_rate = simulation_modifier.get_inputs_from_args()
simulation_modifier.process_and_save_data(pressure, temperature, mass_rate)
