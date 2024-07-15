from tango.core.abstracts.orchestrator import *
from tango.orchestrators.pressure_back_calculator import wellbore
import csv
import os
from tango.utils import *
import numpy as np
import inspect

class SystemExternal(UnitManager):

    def __init__(self, specs):
        super().__init__(specs)
        if 'entire_subsurface_external' in specs['schedule'] and specs['schedule']['entire_subsurface_external'] == 'yes':
            pass
        else:
            self.wb = wellbore('back_calculator', self.specs, self.unit.surface.__class__.__name__)

            if (self.unit.reservoir.__class__.__name__ == 'ReservoirFileReaderUnit'):
                print('global')
                self.csv_data = self._read_csv_file()
                self.current_row = 0

            if (self.unit.surface.__class__.__name__ == 'SurfaceUnitORCNative'):
                self._set_convergence_criteria()
                self.x_lst, self.y_lst = [], []
                self.MAX_NUM_ITR = CONVERGENCE_CRITERIA['max_num_itr']


    # def update(self) -> None:
    #     """update unknown to balance the system"""
    #
    #     print('soil')
    #
    #     if 'entire_subsurface_external' in self.specs['schedule'] and self.specs['schedule']['entire_subsurface_external'] == 'yes':
    #         pass
    #     else:
    #         if (self.specs['schedule']['bc_iteration_checkpoint'] == 'injection_well_bottom'):
    #             if (self.unit.reservoir.__class__.__name__ == 'ReservoirFileReaderUnit'):
    #                 self.unit.surface.reservoir_file_reader = True
    #                 target_bottom_pressure, target_bottom_temperature = self._get_next_target_values()
    #                 self.unit.surface.iterative_inj_pressure, self.unit.surface.iterative_inj_temperature = self.wb.find_injection_conditions(target_bottom_pressure, target_bottom_temperature, max_iter=10000)
    #             else:
    #                 print('soil2')
    #                 target_bottom_pressure = self.specs['reservoir']['hydro_static_pressure'] * (self.specs['reservoir']['over_pressure_percentage']+100)/100
    #                 print(target_bottom_pressure)
    #                 self.unit.surface.iterative_inj_pressure = self.wb.find_injection_pressure(target_bottom_pressure, 8000000, 15000000)
    #
    #                 if (self.unit.surface.__class__.__name__ == 'SurfaceUnitCPGNative'):
    #
    #                     outlet_pressure, outlet_temperature, mass_rate = self.unit.surface.process_stream()
    #                     self.unit.surface.outlet_fluid.updatePT(outlet_pressure, outlet_temperature)
    #                     self.wb.update_dimensionless_time_old()
    #                 elif (self.unit.surface.__class__.__name__ == 'SurfaceUnitORCNative'):
    #                     print('ORC')
    #                     count = 0
    #                     while not self.balanced():
    #                         if self.max_itr_reached(count):
    #                             break
    #                         self._update_production_well()
    #                         count += 1
    #                 else:
    #                     raise NotImplementedError("Only SurfaceUnitCPGNative and SurfaceUnitORCNative are supported for now")
    #         else:
    #             raise NotImplementedError("Only 'injection_well_bottom' is supported as check-point when the External system is used as orchestrator")


    def update(self) -> None:
        """update unknown to balance the system"""

        print('soil')

        if 'entire_subsurface_external' in self.specs['schedule'] and self.specs['schedule']['entire_subsurface_external'] == 'yes':
            pass
        else:
            if (self.specs['schedule']['bc_iteration_checkpoint'] == 'injection_well_bottom'):

                if (self.unit.surface.__class__.__name__ == 'SurfaceUnitCPGNative'):

                    if (self.unit.reservoir.__class__.__name__ == 'ReservoirFileReaderUnit'):
                        self.unit.surface.reservoir_file_reader = True
                        if (self.unit.surface.specs.injection_condition_back_calculation == 'yes'):
                            target_bottom_pressure, target_bottom_temperature = self._get_next_target_values()
                            self.unit.surface.iterative_inj_pressure, self.unit.surface.iterative_inj_temperature = self.wb.find_injection_conditions(target_bottom_pressure, target_bottom_temperature, max_iter=10000)

                    else:
                        target_bottom_pressure = self.specs['reservoir']['hydro_static_pressure'] * (self.specs['reservoir']['over_pressure_percentage']+100)/100
                        self.unit.surface.iterative_inj_pressure = self.wb.find_injection_pressure(target_bottom_pressure, 8000000, 15000000)

                    outlet_pressure, outlet_temperature, mass_rate = self.unit.surface.process_stream()
                    self.unit.surface.outlet_fluid.updatePT(outlet_pressure, outlet_temperature)

                elif (self.unit.surface.__class__.__name__ == 'SurfaceUnitORCNative'):

                    if (self.unit.reservoir.__class__.__name__ == 'ReservoirFileReaderUnit'):
                        self.unit.surface.reservoir_file_reader = True
                        if (self.unit.surface.specs.injection_condition_back_calculation == 'yes'):
                            target_bottom_pressure, target_bottom_temperature = self._get_next_target_values()
                            self.unit.surface.iterative_inj_pressure, self.unit.surface.iterative_inj_temperature = self.wb.find_injection_conditions(target_bottom_pressure, target_bottom_temperature, max_iter=10000)

                    else:
                        target_bottom_pressure = self.specs['reservoir']['hydro_static_pressure'] * (self.specs['reservoir']['over_pressure_percentage']+100)/100
                        self.unit.surface.iterative_inj_pressure = self.wb.find_injection_pressure(target_bottom_pressure, 8000000, 15000000)


                    print('ORC')
                    count = 0
                    while not self.balanced():
                        if self.max_itr_reached(count):
                            break
                        self._update_production_well()
                        count += 1
                else:
                    raise NotImplementedError("Only SurfaceUnitCPGNative and SurfaceUnitORCNative are supported for now")

                self.wb.update_dimensionless_time_old()
                self.unit.reservoir.current_row += 1

            else:
                raise NotImplementedError("Only 'injection_well_bottom' is supported as check-point when the External system is used as orchestrator")



        # if (self.unit.reservoir.__class__.__name__ == 'ReservoirFileReaderUnit'):
        #     self.unit.surface.reservoir_file_reader = True  # 2
        #     if (self.specs['schedule']['bc_iteration_checkpoint'] == 'injection_well_bottom'):
        #         pass
        #         target_bottom_pressure, target_bottom_temperature = self._get_next_target_values()
        #         # target_bottom_pressure = 40250000.0
        #         # target_bottom_temperature = 303.15 # movazeb
        #         print('target', target_bottom_pressure, target_bottom_temperature)
        #         self.unit.surface.iterative_inj_pressure, self.unit.surface.iterative_inj_temperature = self.wb.find_injection_conditions(target_bottom_pressure, target_bottom_temperature, max_iter=10000)  # 3
        #         # self.unit.surface.iterative_inj_pressure = self.wb.find_injection_conditions(target_bottom_pressure, target_bottom_temperature, P0=self.unit.surface.inlet_fluid.P, max_iter=10000)
        #     else:
        #          raise NotImplementedError("Only 'injection_well_bottom' is supported as check-point when the reservoir unit is FileReaderUnit")
        #
        #
        #     outlet_pressure, outlet_temperature, mass_rate = self.unit.surface.process_stream()
        #     self.unit.surface.outlet_fluid.updatePT(outlet_pressure, outlet_temperature)
        #     self.wb.update_dimensionless_time_old()  # 4 # movazeb
        #     self._update_production_well_pump()
        # else:
        #     pass


    def _read_csv_file(self):
        file_path = self.unit.reservoir.specs.inlet_state # '/Users/morteza/Documents/projects/TANGO/examples/representer2.csv'
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
            print('self.current_row', self.current_row)

            target_bottom_pressure = float(row[1])
            target_bottom_temperature = float(row[2])

            return target_bottom_pressure, target_bottom_temperature
        else:
            raise IndexError("Reached the end of the CSV file")


    def update_time_dependent_vars(self) -> None:
        if (self.unit.surface.__class__.__name__ == 'SurfaceUnitCPGNative'):
            if (self.unit.reservoir.__class__.__name__ != 'ReservoirFileReaderUnit'):  # include MOOSE and CMG as well!
                # self.unit.reservoir.update_pressure_old()
                self.unit.reservoir.update_energy_extracted_old()

            self.unit.injection_well.update_dimensionless_time_old()
            self.unit.production_well.update_dimensionless_time_old()

        elif (self.unit.surface.__class__.__name__ == 'SurfaceUnitORCNative'):
            if (self.unit.reservoir.__class__.__name__ != 'ReservoirFileReaderUnit'):
                self.unit.reservoir.update_energy_extracted_old()
            self.unit.injection_well.update_dimensionless_time_old()
            self.unit.production_well.update_dimensionless_time_old()
            self.unit.production_well_pump.update_dimensionless_time_old()
        else:
            raise NotImplementedError("Only SurfaceUnitCPGNative and SurfaceUnitORCNative are supported for now")


    def _update_production_well(self) -> None:
        self.unit.production_well.update_inlet_state()
        self.unit.production_well.stream_interface()
        self.unit.production_well.update_outlet_streams()
        self.unit.production_well_pump.update_inlet_state()
        self.unit.production_well_pump.stream_interface()
        self.unit.production_well_pump.update_outlet_streams()
        self._update_production_well_pump()


    def _update_production_well_pump(self) -> None:
        """Local iterations to update dP_pump in production well with pump"""
        dP_pump = self.unit.production_well_pump.get_dP_pump()
        dP_surface = self._compute_dP_surface()
        if dP_pump == 0. and dP_surface >= 0:
            return # no pummping needed
        x_lst, y_lst = [], []
        count = 0
        while np.abs(dP_surface) > self._CONVERGENCE_CRIT_DP_SURFACE:
            if self.max_itr_reached(count):
                break
            x_lst.append(copy.deepcopy(dP_pump))
            y_lst.append(dP_surface)
            if len(x_lst) == 1:  # first call
                root = -1.0 * dP_surface
            else:
                root = newton(x_lst, y_lst)
                x_lst.pop(0), y_lst.pop(0)
            self.unit.production_well_pump.set_dP_pump(root)
            self.unit.production_well_pump.update_inlet_fluid_state_with_pump()
            outlet_enthalpy, outlet_pressure, mass_rate = self.unit.production_well_pump.process_stream()
            self.unit.production_well_pump.outlet_fluid.updateHP(outlet_enthalpy, outlet_pressure)
            self.unit.surface.update_inlet_state()
            self.unit.surface.overwrite_state_pipe()
            dP_pump = self.unit.production_well_pump.get_dP_pump()
            dP_surface = self._compute_dP_surface()
            count += 1
        self.unit.surface.w_downhole_pump = self.unit.production_well_pump.get_w_pump()
        # print(self.unit.production_well_pump._w_pump, 'ajib')
        # self.unit.surface.w_downhole_pump = self.unit.production_well_pump._w_pump
        print(self.unit.surface.w_downhole_pump, self.unit.surface.w_downhole_pump)


    def _compute_dP_surface(self) -> float:
        return self.unit.production_well_pump.outlet_fluid.P \
             - self.unit.injection_well.inlet_fluid.P \
             - self.unit.surface.dP_pipe

    def _set_convergence_criteria(self) -> None:
        self._CONVERGENCE_CRIT_DP_RESERVOIR: float = CONVERGENCE_CRITERIA['dP_reservoir']
        self._CONVERGENCE_CRIT_DP_SURFACE: float = CONVERGENCE_CRITERIA['dP_surface']
        self._CONVERGENCE_CRIT_DT_SURFACE: float = CONVERGENCE_CRITERIA['dT_surface']


    def max_itr_reached(self, count) -> bool:
        if count > self.MAX_NUM_ITR:
            logging.warning(f"Max number of iteration (={count}) has reached in '{inspect.stack()[1][3]}'. Exiting iteration.")
            return True
        return False

    def balanced(self) -> bool:
        dP_surface = self._compute_dP_surface()
        if np.abs(dP_surface) < self._CONVERGENCE_CRIT_DP_SURFACE:
            return True
        return False
