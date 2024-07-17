import networkx as nx
import numpy as np
import copy
import logging
import inspect

from tango.core.config import *
from tango.core.constants import *
from tango.core.stream import *
from tango.core.abstracts.orchestrator import *
from tango.utils import *
from tango.orchestrators.pressure_back_calculator import wellbore


class SystemNative(UnitManager):

    def __init__(self, specs):
        super().__init__(specs)
        self.x_lst, self.y_lst = [], []
        self.MAX_NUM_ITR = CONVERGENCE_CRITERIA['max_num_itr']


    def max_itr_reached(self, count) -> bool:
        if count > self.MAX_NUM_ITR:
            logging.warning(f"Max number of iteration (={count}) has reached in '{inspect.stack()[1][3]}'. Exiting iteration.")
            return True
        return False


    def balanced(self) -> bool:
        return True


    def update_time_dependent_vars(self) -> None:
        pass


    def update(self) -> None:
        pass


class SystemCPGNative(SystemNative):

    def __init__(self, specs):
        super().__init__(specs)
        self._input_check(['injection_well', 'reservoir', 'production_well', 'surface'])
        self._set_convergence_criteria()
        self.stop = False


    def _set_convergence_criteria(self) -> None:
        self._CONVERGENCE_CRIT_DP_RESERVOIR: float = CONVERGENCE_CRITERIA['dP_reservoir']


    def balanced(self) -> bool:
        if (self.specs['schedule']['bc_iteration_checkpoint'] == 'production_well_bottom'):
            self.dP_reservoir = self.unit.reservoir.get_del_pressure()
        elif (self.specs['schedule']['bc_iteration_checkpoint'] == 'injection_well_bottom'):
            self.dP_reservoir = 10000000

        if np.abs(self.dP_reservoir) < self._CONVERGENCE_CRIT_DP_RESERVOIR:
            return True
        return False


    def update(self) -> None:
        """update unknown to balance the system"""
        print('abc')
        if (self.specs['schedule']['bc_iteration_checkpoint'] == 'production_well_bottom'):
            self.x_lst.append(self.unit.surface.get_dP_pump())
            self.y_lst.append(self.dP_reservoir)
            if len(self.x_lst) == 1: # first call
                root = 0.5 * self.dP_reservoir
            else:
                root = newton(self.x_lst, self.y_lst)
                self.x_lst.pop(0)
                self.y_lst.pop(0)
            self.unit.surface.update_dP_pump(root)

        elif (self.specs['schedule']['bc_iteration_checkpoint'] == 'injection_well_bottom'):
            wb = wellbore('back_calculator', self.specs, self.unit.surface.__class__.__name__)
            target_bottom_pressure = self.specs['reservoir']['hydro_static_pressure'] * (self.specs['reservoir']['over_pressure_percentage']+100)/100
            P0_guess1 = 8e6
            P0_guess2 = 15e6
            self.unit.surface.iterative_inj_pressure = wb.find_injection_pressure(target_bottom_pressure, P0_guess1, P0_guess2)
            wb.update_dimensionless_time_old()

        outlet_pressure, outlet_temperature, mass_rate = self.unit.surface.process_stream()
        self.unit.surface.outlet_fluid.updatePT(outlet_pressure, outlet_temperature)


    def update_time_dependent_vars(self) -> None:
        self.x_lst.clear()
        self.y_lst.clear()
        self.unit.reservoir.update_pressure_old()
        self.unit.reservoir.update_energy_extracted_old()
        self.unit.injection_well.update_dimensionless_time_old()
        self.unit.production_well.update_dimensionless_time_old()
        self.unit.surface.current_row += 1
        self.unit.reservoir.current_row += 1
        self.unit.injection_well.current_row += 1
        self.unit.production_well.current_row += 1


class SystemORCNative(SystemNative):

    def __init__(self, state):
        super().__init__(state)
        self._input_check(['injection_well', 'reservoir', 'production_well', 'production_well_pump', 'surface'])
        self._set_convergence_criteria()


    def _set_convergence_criteria(self) -> None:
        self._CONVERGENCE_CRIT_DP_RESERVOIR: float = CONVERGENCE_CRITERIA['dP_reservoir']
        self._CONVERGENCE_CRIT_DP_SURFACE: float = CONVERGENCE_CRITERIA['dP_surface']
        self._CONVERGENCE_CRIT_DT_SURFACE: float = CONVERGENCE_CRITERIA['dT_surface']


    def _update_injection_well_inlet_P(self) -> None:
        """Local iterations to update injection well inlet pressure"""
        self.unit.injection_well.update_inlet_state()
        dP_reservoir = self.unit.reservoir.get_del_pressure()
        x_lst, y_lst = [], []
        count = 0
        while np.abs(dP_reservoir) > self._CONVERGENCE_CRIT_DP_RESERVOIR:
            if self.max_itr_reached(count):
                break
            x_lst.append(copy.deepcopy(self.unit.injection_well.inlet_fluid.P))
            y_lst.append(dP_reservoir)
            if len(x_lst) == 1:  # first call
                root = x_lst[0] + dP_reservoir
            else:
                root = newton(x_lst, y_lst)
                x_lst.pop(0), y_lst.pop(0)
            self.unit.injection_well.update_inlet_fluid_state_PT(P=root)
            outlet_enthalpy, outlet_pressure, mass_rate = self.unit.injection_well.process_stream()
            self.unit.injection_well.outlet_fluid.updateHP(outlet_enthalpy, outlet_pressure)
            self.unit.reservoir.update_inlet_state()
            self.unit.reservoir.stream_interface()
            self.unit.reservoir.update_outlet_streams()
            dP_reservoir = self.unit.reservoir.get_del_pressure()
            count += 1


    def _compute_dP_surface(self) -> float:
        return self.unit.production_well_pump.outlet_fluid.P \
             - self.unit.injection_well.inlet_fluid.P \
             - self.unit.surface.dP_pipe


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


    def _update_surface(self) -> None:
        self.unit.surface.update_inlet_state()
        self.unit.surface.stream_interface()
        self.unit.surface.update_outlet_streams()
        self.unit.injection_well.update_inlet_state()


    def _update_injection_well_inlet_T(self) -> None:
        """Local iterations to update temperature at injection well"""
        self.unit.surface.update_inlet_state()
        self.unit.surface.stream_interface()
        self.unit.surface.update_outlet_streams()
        dT_surface = self.unit.injection_well.get_del_temperature(T=self.unit.surface.outlet_fluid.T)
        self.x_lst.append(copy.deepcopy(self.unit.injection_well.get_inlet_temperature_tmp()))
        self.y_lst.append(dT_surface)
        if len(self.x_lst) == 1: # first call
            root = self.unit.surface.outlet_fluid.T
        else:
            try:
                root = newton(self.x_lst, self.y_lst)
            except:
                root= -1. # dummy
            root = max(root, MIN_INJ_TEMPERATURE)
            self.x_lst.pop(0)
            self.y_lst.pop(0)
        self.unit.injection_well.update_inlet_fluid_state_PT(T=root)
        self.unit.injection_well.update_inlet_temperature_tmp()


    def balanced(self) -> bool:
        dP_reservoir = self.unit.reservoir.get_del_pressure()
        dP_surface = self._compute_dP_surface()
        dT_surface = self.unit.injection_well.get_del_temperature(T=self.unit.surface.outlet_fluid.T)
        if  np.abs(dP_reservoir) < self._CONVERGENCE_CRIT_DP_RESERVOIR and \
            np.abs(dP_surface) < self._CONVERGENCE_CRIT_DP_SURFACE and \
            np.abs(dT_surface) < self._CONVERGENCE_CRIT_DT_SURFACE:
            return True
        return False


    def update(self) -> None:
        """update unknown variables to balance the system"""
        count = 0
        while not self.balanced():

            if self.max_itr_reached(count):
                break

            self._update_injection_well_inlet_P()

            self._update_production_well()

            self._update_injection_well_inlet_T()

            count += 1


    def update_time_dependent_vars(self) -> None:
        self.x_lst.clear()
        self.y_lst.clear()
        self.unit.reservoir.update_pressure_old()
        self.unit.reservoir.update_energy_extracted_old()
        self.unit.injection_well.update_dimensionless_time_old()
        self.unit.production_well.update_dimensionless_time_old()
        self.unit.production_well_pump.update_dimensionless_time_old()
        self.unit.surface.current_row += 1
        self.unit.reservoir.current_row += 1
        self.unit.injection_well.current_row += 1
        self.unit.production_well.current_row += 1
        self.unit.production_well_pump.current_row += 1
