from tango.core.abstracts.orchestrator import *
from tango.orchestrators.pressure_back_calculator import wellbore
import csv
import os

class SystemExternal(UnitManager):

    def __init__(self, specs):
        super().__init__(specs)
        if (self.unit.reservoir.__class__.__name__ == 'FileReaderUnit'):
            self.wb = wellbore('back_calculator', self.specs, self.unit.surface.__class__.__name__)
            self.csv_data = self._read_csv_file()
            self.current_row = 0
            print(self.unit.reservoir.specs)

    def update(self) -> None:
        """update unknown to balance the system"""

        if (self.unit.reservoir.__class__.__name__ == 'FileReaderUnit'):
            self.unit.surface.reservoir_file_reader = True
            if (self.specs['schedule']['bc_iteration_checkpoint'] == 'injection_well_bottom'):
                target_bottom_pressure, target_bottom_temperature = self._get_next_target_values()
                self.unit.surface.iterative_inj_pressure, self.unit.surface.iterative_inj_temperature = self.wb.find_injection_conditions(target_bottom_pressure, target_bottom_temperature, max_iter=10000)
            else:
                 raise NotImplementedError("Only 'injection_well_bottom' is supported as check-point when the reservoir unit is FileReaderUnit")


            outlet_pressure, outlet_temperature, mass_rate = self.unit.surface.process_stream()
            self.unit.surface.outlet_fluid.updatePT(outlet_pressure, outlet_temperature)
            self.unit.injection_well.update_dimensionless_time_old()
        else:
            pass


    def _read_csv_file(self):
        file_path = self.unit.reservoir.specs.outlet_state # '/Users/morteza/Documents/projects/TANGO/examples/representer2.csv'
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"The CSV file does not exist at {file_path}")

        with open(file_path, 'r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row
            return list(reader)

    def _get_next_target_values(self):
        if self.current_row < len(self.csv_data):
            row = self.csv_data[self.current_row]
            self.current_row += 1

            target_bottom_pressure = float(row[1])
            target_bottom_temperature = float(row[2])

            return target_bottom_pressure, target_bottom_temperature
        else:
            raise IndexError("Reached the end of the CSV file")


    def update_time_dependent_vars(self) -> None:
        if (self.unit.reservoir.__class__.__name__ != 'FileReaderUnit'):  # include MOOSE and CMG as well!
            self.unit.reservoir.update_pressure_old()
            self.unit.reservoir.update_energy_extracted_old()

        self.unit.injection_well.update_dimensionless_time_old()
        self.unit.production_well.update_dimensionless_time_old()
