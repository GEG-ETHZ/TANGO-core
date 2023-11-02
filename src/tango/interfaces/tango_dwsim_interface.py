import csv
import sys
import random
import os
import pythoncom

pythoncom.CoInitialize()

import clr
from System.IO import Directory, Path, File
from System import String, Environment


class DWSIMSimulationModifier:
    def __init__(self, dwsim_path, simulation_file_path):
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


    def DWSIM_inputs(self):
        pp_inlet_stream = self.flowsheet.GetObject("Turbine_inlet")
        inlet_stream_obj = pp_inlet_stream.GetAsObject()
        inlet_stream_obj.SetTemperature(403.0)
        inlet_stream_obj.SetPressure(16500000)
        inlet_stream_obj.SetMassFlow(40)


    def DWSIM_runner(self):
        self.interf.CalculateFlowsheet2(self.flowsheet)


    def DWSIM_outputs(self, pp_outlet_stream_name):
        pp_outlet_stream = self.flowsheet.GetObject(pp_outlet_stream_name)
        outlet_stream_obj = pp_outlet_stream.GetAsObject()
        self.temperature_from_dwsim = outlet_stream_obj.GetTemperature()
        self.pressure_from_dwsim = outlet_stream_obj.GetPressure()
        self.massrate_from_dwsim = outlet_stream_obj.GetMassFlow()
        print(self.temperature_from_dwsim, self.pressure_from_dwsim, self.massrate_from_dwsim)


    def DWSIM_data_extractor(self, PP_object_name, new_class_name):
        pp_object = self.flowsheet.GetObject(PP_object_name)
        setattr(self, new_class_name, pp_object.GetAsObject())


    def save_modified_simulation(self, save_path):
        save_path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Desktop), save_path)
        self.interf.SaveFlowsheet(self.flowsheet, save_path, True)
        print("Modified simulation saved to:", save_path)


    def write_row(self, csv_file, row_data):
        with open(csv_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(row_data)


# Example usage
dwsim_path = "C:\\Users\\Morteza\\AppData\\Local\\DWSIM\\"

# simulation_file_path = "Z:\\Desktop\\second.dwxmz"
simulation_file_path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Desktop), "second.dwxmz")

if len(sys.argv) >= 3:
    pressure = sys.argv[1]
    temperature = sys.argv[2]
else:
    print("Error: The required arguments (pressure and temperature) are missing.")
    sys.exit(1)

print("Parameter received from Mac:", pressure, temperature)

simulation_modifier = DWSIMSimulationModifier(dwsim_path, simulation_file_path)
simulation_modifier.DWSIM_inputs()
simulation_modifier.DWSIM_runner()
simulation_modifier.DWSIM_outputs("Pump_outlet")
simulation_modifier.DWSIM_data_extractor("Turbine_inlet", "TurbineInlet")
simulation_modifier.DWSIM_data_extractor("Turbine", "newww")
simulation_modifier.DWSIM_data_extractor("Turbine_outlet", "TurbineOutlet")
simulation_modifier.DWSIM_data_extractor("Cooler", "Cooler")
# simulation_modifier.DWSIM_data_extractor("Cooler_removed_heat", "CoolerRemovedHeat")
simulation_modifier.DWSIM_data_extractor("Cooler_outlet", "CoolerOutlet")
simulation_modifier.DWSIM_data_extractor("Condenser", "Condenser")
simulation_modifier.DWSIM_data_extractor("Condenser_outlet", "CondenserOutlet")
simulation_modifier.DWSIM_data_extractor("Pump", "Pump")
simulation_modifier.DWSIM_data_extractor("Pump_outlet", "PumpOutlet")
# print(simulation_modifier.newww.GetPowerGeneratedOrConsumed())
simulation_modifier.save_modified_simulation("modified_simulation2.dwxmz")

T_Turbine_inlet_DWSIM = simulation_modifier.TurbineInlet.GetTemperature()
P_Turbine_inlet_DWSIM = simulation_modifier.TurbineInlet.GetPressure()
w_turbine_DWSIM = 1000.0 * simulation_modifier.newww.GetPowerGeneratedOrConsumed()
T_Turbine_outlet_DWSIM = simulation_modifier.TurbineOutlet.GetTemperature()
P_Turbine_outlet_DWSIM = simulation_modifier.TurbineOutlet.GetPressure()
q_Cooler_DWSIM = -1000.0 * simulation_modifier.Cooler.DeltaQ
T_Cooler_outlet_DWSIM = simulation_modifier.CoolerOutlet.GetTemperature()
P_Cooler_outlet_DWSIM = simulation_modifier.CoolerOutlet.GetPressure()
q_Condenser_DWSIM = -1000.0 * simulation_modifier.Condenser.DeltaQ
T_Condenser_outlet_DWSIM = simulation_modifier.CondenserOutlet.GetTemperature()
P_Condenser_outlet_DWSIM = simulation_modifier.CondenserOutlet.GetPressure()
w_Pump_DWSIM = 1000.0 * simulation_modifier.Pump.GetPowerGeneratedOrConsumed()
T_Pump_outlet_DWSIM = simulation_modifier.PumpOutlet.GetTemperature()
P_Pump_outlet_DWSIM = simulation_modifier.PumpOutlet.GetPressure()
# q_cooler_DWSIM = simulation_modifier.CoolerRemovedHeat.EnergyFlow

variables = ['T_Turbine_inlet_DWSIM', 'P_Turbine_inlet_DWSIM', 'w_turbine_DWSIM',
             'T_Turbine_outlet_DWSIM', 'P_Turbine_outlet_DWSIM', 'q_Cooler_DWSIM',
             'T_Cooler_outlet_DWSIM', 'P_Cooler_outlet_DWSIM', 'q_Condenser_DWSIM',
             'T_Condenser_outlet_DWSIM', 'P_Condenser_outlet_DWSIM', 'w_Pump_DWSIM',
             'T_Pump_outlet_DWSIM', 'P_Pump_outlet_DWSIM']

header = True

# csv_file = "Z:\\Desktop\\data.csv"
csv_file = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Desktop), "data.csv")

if not os.path.exists(csv_file):
    with open(csv_file, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(variables)

data_row = [T_Turbine_inlet_DWSIM, P_Turbine_inlet_DWSIM, w_turbine_DWSIM,
             T_Turbine_outlet_DWSIM, P_Turbine_outlet_DWSIM, q_Cooler_DWSIM,
             T_Cooler_outlet_DWSIM, P_Cooler_outlet_DWSIM, q_Condenser_DWSIM,
             T_Condenser_outlet_DWSIM, P_Condenser_outlet_DWSIM, w_Pump_DWSIM,
             T_Pump_outlet_DWSIM, P_Pump_outlet_DWSIM + random.randint(0, 9)]

simulation_modifier.write_row(csv_file, data_row)
