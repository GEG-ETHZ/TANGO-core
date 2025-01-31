from tango.core.abstracts.orchestrator import *
from tango.orchestrators.pressure_back_calculator import wellbore
import csv
import os
from tango.utils import *
import numpy as np
import inspect
from tango.flow_rate import *


class SystemExternal(UnitManager):
    """
    Manages an external system within TANGO.

    This class handles systems where the subsurface computations are performed externally
    or rely on external inputs such as reservoir file readers or back-calculation methods.

    Attributes:
        wb (wellbore): Wellbore object used for back-calculation of injection conditions.
        csv_data (list): Data read from a CSV file for reservoir inputs.
        current_row (int): Tracks the current row in the CSV file for iterative calculations.
        x_lst (list): Stores x-values for root-finding during iterations.
        y_lst (list): Stores y-values for root-finding during iterations.
        MAX_NUM_ITR (int): Maximum number of iterations allowed for convergence.
    """

    def __init__(self, specs):
        """
        Initializes the SystemExternal object.

        Args:
            specs (dict): Specifications for the system.

        Logic:
        - Checks if the entire subsurface system is external.
        - Initializes wellbore object for back-calculations if subsurface is partially external.
        - Handles special cases for reservoir file readers and ORC surface systems.
        """
        super().__init__(specs)
        if 'entire_subsurface_external' in specs['schedule'] and specs['schedule']['entire_subsurface_external'] == 'yes':
            pass
        else:
            self.wb = wellbore('back_calculator', self.specs, self.unit.surface.__class__.__name__)

            if self.unit.reservoir.__class__.__name__ == 'ReservoirFileReaderUnit':
                self.csv_data = self._read_csv_file()
                self.current_row = 0

            if self.unit.surface.__class__.__name__ == 'SurfaceUnitORCNative':
                self._set_convergence_criteria()
                self.x_lst, self.y_lst = [], []
                self.MAX_NUM_ITR = CONVERGENCE_CRITERIA['max_num_itr']

            # self.unit.production_well_pump = None
            if not hasattr(self.unit, 'production_well_pump') or self.unit.production_well_pump is None:
                self.unit.production_well_pump = None

            self.flow_rate_calculator = FlowRateCalculator(self.unit.injection_well, self.unit.production_well, self.unit.production_well_pump, self.unit.reservoir, self.unit.surface)

    def update(self) -> None:
        """
        Updates unknown variables to balance the system.

        Logic:
        - Handles injection well conditions based on the type of surface and reservoir systems.
        - For ORC systems, performs iterative updates until the system is balanced.
        - Supports only the "injection_well_bottom" checkpoint.

        Raises:
            NotImplementedError: If the surface system is unsupported or the checkpoint is not "injection_well_bottom".
        """
        if 'entire_subsurface_external' in self.specs['schedule'] and self.specs['schedule']['entire_subsurface_external'] == 'yes':
            pass
        else:
            if self.specs['schedule']['bc_iteration_checkpoint'] == 'injection_well_bottom':
                if self.unit.surface.__class__.__name__ == 'SurfaceUnitCPGNative':
                    if self.unit.reservoir.__class__.__name__ == 'ReservoirFileReaderUnit':
                        self.unit.surface.reservoir_file_reader = True
                        if self.unit.surface.specs.injection_condition_back_calculation == 'yes':
                            target_bottom_pressure, target_bottom_temperature = self._get_next_target_values()
                            self.unit.surface.iterative_inj_pressure, self.unit.surface.iterative_inj_temperature = self.wb.find_injection_conditions(target_bottom_pressure, target_bottom_temperature, max_iter=10000)
                    else:
                        target_bottom_pressure = self.specs['reservoir']['hydro_static_pressure'] * (self.specs['reservoir']['over_pressure_percentage'] + 100) / 100
                        self.unit.surface.iterative_inj_pressure = self.wb.find_injection_pressure(target_bottom_pressure, 8000000, 15000000)
                    outlet_pressure, outlet_temperature, mass_rate = self.unit.surface.process_stream()
                    self.unit.surface.outlet_fluid.updatePT(outlet_pressure, outlet_temperature)

                elif self.unit.surface.__class__.__name__ == 'SurfaceUnitFlexiblePP':
                    # pass
                    self.flow_rate_calculator.prr()
                    self.flow_rate_calculator.fracing_flow()
                    self.flow_rate_calculator.pressure_finder(self.unit.reservoir.specs.hydro_static_pressure * (self.unit.reservoir.specs.over_pressure_percentage / 100.0 + 1.0))

                    # optimal_rate = self.flow_rate_calculator.find_mass_rate()

                    # self.unit.injection_well.update_inlet_fluid_state_PT(P=self.flow_rate_calculator.well.inlet_fluid.P)
                    # self.unit.injection_well.stream_interface()

                    # if self.unit.reservoir.__class__.__name__ == 'ReservoirFileReaderUnit':
                    #     self.unit.surface.reservoir_file_reader = True
                    #     if self.unit.surface.specs.injection_condition_back_calculation == 'yes':
                    #         target_bottom_pressure, target_bottom_temperature = self._get_next_target_values()
                    #         self.unit.surface.iterative_inj_pressure, self.unit.surface.iterative_inj_temperature = self.wb.find_injection_conditions(target_bottom_pressure, target_bottom_temperature, max_iter=10000)
                    # else:
                    #     target_bottom_pressure = self.specs['reservoir']['hydro_static_pressure'] * (self.specs['reservoir']['over_pressure_percentage'] + 100) / 100
                    #     self.unit.surface.iterative_inj_pressure = self.wb.find_injection_pressure(target_bottom_pressure, 8000000, 15000000)
                    # outlet_pressure, outlet_temperature, mass_rate = self.unit.surface.process_stream()
                    # self.unit.surface.outlet_fluid.updatePT(outlet_pressure, outlet_temperature)

                elif self.unit.surface.__class__.__name__ == 'SurfaceUnitORCNative':
                    if self.unit.reservoir.__class__.__name__ == 'ReservoirFileReaderUnit':
                        self.unit.surface.reservoir_file_reader = True
                        if self.unit.surface.specs.injection_condition_back_calculation == 'yes':
                            target_bottom_pressure, target_bottom_temperature = self._get_next_target_values()
                            self.unit.surface.iterative_inj_pressure, self.unit.surface.iterative_inj_temperature = self.wb.find_injection_conditions(target_bottom_pressure, target_bottom_temperature, max_iter=10000)
                    else:
                        target_bottom_pressure = self.specs['reservoir']['hydro_static_pressure'] * (self.specs['reservoir']['over_pressure_percentage'] + 100) / 100
                        self.unit.surface.iterative_inj_pressure = self.wb.find_injection_pressure(target_bottom_pressure, 8000000, 15000000)

                    count = 0
                    while not self.balanced():
                        if self.max_itr_reached(count):
                            break
                        self._update_production_well()
                        count += 1
                else:
                    raise NotImplementedError("Only SurfaceUnitCPGNative and SurfaceUnitORCNative are supported for now")

                self.wb.update_dimensionless_time_old()
                self.wb.current_row += 1
                self.unit.reservoir.current_row += 1
            else:
                raise NotImplementedError("Only 'injection_well_bottom' is supported as a checkpoint when the external system is used as orchestrator")

    def _read_csv_file(self):
        """
        Reads a CSV file for reservoir inputs.

        Returns:
            list: A list of rows from the CSV file.

        Raises:
            FileNotFoundError: If the CSV file does not exist.

        Example:
            >>> data = self._read_csv_file()
        """
        file_path = self.unit.reservoir.specs.inlet_state
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"The CSV file does not exist at {file_path}")

        with open(file_path, 'r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row
            return list(reader)

    def _get_next_target_values(self):
        """
        Retrieves the next target values (pressure and temperature) from the CSV data.

        Returns:
            tuple: A tuple containing:
                - `target_bottom_pressure` (float): Target bottom pressure.
                - `target_bottom_temperature` (float): Target bottom temperature.

        Raises:
            IndexError: If the end of the CSV data is reached.

        Example:
            >>> pressure, temperature = self._get_next_target_values()
        """
        if self.current_row < len(self.csv_data):
            row = self.csv_data[self.current_row]
            self.current_row += 1
            target_bottom_pressure = float(row[1])
            target_bottom_temperature = float(row[2])
            return target_bottom_pressure, target_bottom_temperature
        else:
            raise IndexError("Reached the end of the CSV file")


    def update_time_dependent_vars(self) -> None:
        """
        Updates time-dependent variables for the system.

        Logic:
            Handles time-dependent updates for different surface units:
            - For `SurfaceUnitCPGNative`, updates dimensionless time for wells and current row indices.
            - For `SurfaceUnitORCNative` and `SurfaceUnitDHNative`, includes production well pump updates.

        Raises:
            NotImplementedError: If the surface unit type is unsupported.
        """
        if self.unit.surface.__class__.__name__ == 'SurfaceUnitCPGNative':
            if self.unit.reservoir.__class__.__name__ != 'ReservoirFileReaderUnit':
                self.unit.reservoir.update_energy_extracted_old()
            self.unit.injection_well.update_dimensionless_time_old()
            self.unit.production_well.update_dimensionless_time_old()
            self.unit.surface.current_row += 1
            self.unit.reservoir.current_row += 1
            self.unit.injection_well.current_row += 1
            self.unit.production_well.current_row += 1

        if self.unit.surface.__class__.__name__ == 'SurfaceUnitFlexiblePP':
            if self.unit.reservoir.__class__.__name__ != 'ReservoirFileReaderUnit':
                self.unit.reservoir.update_energy_extracted_old()
            self.unit.injection_well.update_dimensionless_time_old()
            self.unit.production_well.update_dimensionless_time_old()
            self.unit.surface.current_row += 1
            self.unit.reservoir.current_row += 1
            self.unit.injection_well.current_row += 1
            self.unit.production_well.current_row += 1

        elif self.unit.surface.__class__.__name__ in ['SurfaceUnitORCNative', 'SurfaceUnitDHNative']:
            if self.unit.reservoir.__class__.__name__ != 'ReservoirFileReaderUnit':
                self.unit.reservoir.update_energy_extracted_old()
            self.unit.injection_well.update_dimensionless_time_old()
            self.unit.production_well.update_dimensionless_time_old()
            self.unit.production_well_pump.update_dimensionless_time_old()
        else:
            raise NotImplementedError("Only SurfaceUnitCPGNative and SurfaceUnitORCNative are supported for now")


    def _update_production_well(self) -> None:
        """
        Updates the state of the production well and its associated pump.

        Steps:
        - Updates the inlet and outlet states of the production well.
        - Updates the inlet and outlet states of the production well pump.
        - Calls `_update_production_well_pump` for further pressure adjustments.
        """
        self.unit.production_well.update_inlet_state()
        self.unit.production_well.stream_interface()
        self.unit.production_well.update_outlet_streams()
        self.unit.production_well_pump.update_inlet_state()
        self.unit.production_well_pump.stream_interface()
        self.unit.production_well_pump.update_outlet_streams()
        self._update_production_well_pump()


    def _update_production_well_pump(self) -> None:
        """
        Iteratively updates `dP_pump` for the production well pump.

        Logic:
        - Adjusts the pump pressure difference (`dP_pump`) to balance the surface pressure difference.
        - Uses a root-finding approach with the Newton-Raphson method.

        Steps:
        - Computes `dP_surface` and determines if pumping is needed.
        - Iteratively updates `dP_pump` until the convergence criterion is met.

        Raises:
            RuntimeError: If the maximum number of iterations is reached without convergence.
        """
        dP_pump = self.unit.production_well_pump.get_dP_pump()
        dP_surface = self._compute_dP_surface()
        if dP_pump == 0.0 and dP_surface >= 0:
            return  # No pumping needed
        x_lst, y_lst = [], []
        count = 0
        while np.abs(dP_surface) > self._CONVERGENCE_CRIT_DP_SURFACE:
            if self.max_itr_reached(count):
                break
            x_lst.append(copy.deepcopy(dP_pump))
            y_lst.append(dP_surface)
            if len(x_lst) == 1:
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


    def _compute_dP_surface(self) -> float:
        """
        Computes the surface pressure difference (`dP_surface`).

        Formula:
            dP_surface = P_outlet_production_pump - P_inlet_injection_well - dP_pipe

        Returns:
            float: Surface pressure difference.
        """
        return self.unit.production_well_pump.outlet_fluid.P \
             - self.unit.injection_well.inlet_fluid.P \
             - self.unit.surface.dP_pipe


    def _set_convergence_criteria(self) -> None:
        """
        Sets the convergence criteria for pressure and temperature differences.

        Updates:
            - `self._CONVERGENCE_CRIT_DP_RESERVOIR`: Convergence criterion for reservoir pressure.
            - `self._CONVERGENCE_CRIT_DP_SURFACE`: Convergence criterion for surface pressure.
            - `self._CONVERGENCE_CRIT_DT_SURFACE`: Convergence criterion for surface temperature.
        """
        self._CONVERGENCE_CRIT_DP_RESERVOIR: float = CONVERGENCE_CRITERIA['dP_reservoir']
        self._CONVERGENCE_CRIT_DP_SURFACE: float = CONVERGENCE_CRITERIA['dP_surface']
        self._CONVERGENCE_CRIT_DT_SURFACE: float = CONVERGENCE_CRITERIA['dT_surface']


    def max_itr_reached(self, count) -> bool:
        """
        Checks if the maximum number of iterations has been reached.

        Args:
            count (int): Current iteration count.

        Returns:
            bool: True if the maximum iteration limit is reached, False otherwise.
        """
        if count > self.MAX_NUM_ITR:
            logging.warning(f"Max number of iteration (={count}) has reached in '{inspect.stack()[1][3]}'. Exiting iteration.")
            return True
        return False

    def balanced(self) -> bool:
        """
        Checks if the system is balanced based on surface pressure difference.

        Returns:
            bool: True if `dP_surface` is within the convergence criterion, False otherwise.
        """
        dP_surface = self._compute_dP_surface()
        if np.abs(dP_surface) < self._CONVERGENCE_CRIT_DP_SURFACE:
            return True
        return False

