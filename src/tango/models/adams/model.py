from tango.models.base import *
from tango.core.config import *
from tango.core.constants import *
from tango import utils
import numpy as np
import copy
import logging
import inspect

class ModelStateAdams(ModelState):
    def __init__(self, specs):
        super().__init__(self, specs)


class ModelAdams(Model):
    def __init__(self, specs):
        super().__init__(self, specs)


class SystemAdams(System):

    def __init__(self, state, models):
        super().__init__(state, models)
        self.x_lst, self.y_lst = [], []
        self.max_num_itr = CONVERGENCE_CRITERIA['max_num_itr']


    def max_itr_reached(self, count) -> bool:
        if count > self.max_num_itr:
            logging.warning(f"Max number of iteration (={count}) has reached in '{inspect.stack()[1][3]}'. Exiting iteration.")
            return True
        return False


class SystemCPGAdams(SystemAdams):

    def __init__(self, state, models):
        super().__init__(state, models)
        self.surface_model = models['surface']
        self._set_convergence_criteria()


    def _set_convergence_criteria(self) -> None:
        self._CONVERGENCE_CRIT_DP_RESERVOIR: float = CONVERGENCE_CRITERIA['dP_reservoir']


    def balanced(self) -> bool:
        self.dP_reservoir = self.state.reservoir.get_del_pressure()
        if np.abs(self.dP_reservoir) < self._CONVERGENCE_CRIT_DP_RESERVOIR:
            return True
        return False


    def update(self) -> None:
        """update unknown to balance the system"""
        self.x_lst.append(self.state.surface.get_dP_pump())
        self.y_lst.append(self.dP_reservoir)
        if len(self.x_lst) == 1: # first call
            root = 0.5 * self.dP_reservoir
        else:
            root = utils.newton(self.x_lst, self.y_lst)
            self.x_lst.pop(0)
            self.y_lst.pop(0)
        self.state.surface.update_dP_pump(root)
        self.surface_model.overwrite_pump_state(state=self.state.surface)


    def update_time_dependent_vars(self) -> None:
        self.x_lst.clear()
        self.y_lst.clear()
        self.state.reservoir.update_pressure_old()
        self.state.reservoir.update_energy_extracted_old()
        self.state.injection_well.update_dimensionless_time_old()
        self.state.production_well.update_dimensionless_time_old()



class SystemORCAdams(SystemAdams):

    def __init__(self, state, models):
        super().__init__(state, models)
        self._set_models(models)
        self._set_convergence_criteria()


    def _set_models(self, models: dict) -> None:
        for name in models.keys():
            setattr(self, name, models[name])


    def _set_convergence_criteria(self) -> None:
        self._CONVERGENCE_CRIT_DP_RESERVOIR: float = CONVERGENCE_CRITERIA['dP_reservoir']
        self._CONVERGENCE_CRIT_DP_SURFACE: float = CONVERGENCE_CRITERIA['dP_surface']
        self._CONVERGENCE_CRIT_DT_SURFACE: float = CONVERGENCE_CRITERIA['dT_surface']


    def _update_injection_well_inlet_P(self) -> None:
        """Local iterations to update injection well inlet pressure"""
        dP_reservoir = self.state.reservoir.get_del_pressure()
        x_lst, y_lst = [], []
        count = 0
        while np.abs(dP_reservoir) > self._CONVERGENCE_CRIT_DP_RESERVOIR:
            if self.max_itr_reached(count):
                break
            x_lst.append(copy.deepcopy(self.state.injection_well.inlet_fluid.P))
            y_lst.append(dP_reservoir)
            if len(x_lst) == 1:  # first call
                root = x_lst[0] + dP_reservoir
            else:
                root = utils.newton(x_lst, y_lst)
                x_lst.pop(0), y_lst.pop(0)
            self.state.injection_well.update_inlet_fluid_state_PT(P=root)
            self.injection_well.execute(state=self.state.injection_well)
            self.reservoir.execute(state=self.state.reservoir)
            dP_reservoir = self.state.reservoir.get_del_pressure()
            count += 1


    def _update_production_well_pump(self) -> None:
        """Local iterations to update dP_pump in production well with pump"""
        dP_pump = self.state.production_well_pump.get_dP_pump()
        dP_surface = self.state.surface.get_del_pressure()
        if dP_pump == 0. and dP_surface >= 0:
            return # no pummping needed----------
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
                root = utils.newton(x_lst, y_lst)
                x_lst.pop(0), y_lst.pop(0)
            self.state.production_well_pump.set_dP_pump(root)
            self.state.production_well_pump.update_inlet_fluid_state_with_pump()
            self.production_well_pump.update(state=self.state.production_well_pump)
            self.surface.overwrite_state_pipe(state=self.state.surface)
            dP_pump = self.state.production_well_pump.get_dP_pump()
            dP_surface = self.state.surface.get_del_pressure()
            count += 1
        self.state.surface.w_downhole_pump = self.state.production_well_pump.get_w_pump()


    def _update_injection_well_inlet_T(self) -> None:
        """Local iterations to update temperature at injection well"""
        dT_surface = self.state.injection_well.get_del_temperature()
        self.x_lst.append(copy.deepcopy(self.state.injection_well.get_inlet_temperature_tmp()))
        self.y_lst.append(dT_surface)
        if len(self.x_lst) == 1: # first call
            root = self.state.surface.outlet_fluid.T
        else:
            try:
                root = utils.newton(self.x_lst, self.y_lst)
            except:
                root= -1. # dummy
            root = max(root, MIN_INJ_TEMPERATURE)
            self.x_lst.pop(0)
            self.y_lst.pop(0)
        self.state.injection_well.update_inlet_fluid_state_PT(T=root)
        self.state.injection_well.update_inlet_temperature_tmp()


    def balanced(self) -> bool:
        dP_reservoir = self.state.reservoir.get_del_pressure()
        dP_surface = self.state.surface.get_del_pressure()
        dT_surface = self.state.injection_well.get_del_temperature()
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

            self.production_well.execute(state=self.state.production_well)

            self.production_well_pump.execute(state=self.state.production_well_pump)

            self._update_production_well_pump()

            self.surface.execute(state=self.state.surface)

            self._update_injection_well_inlet_T()

            count += 1


    def update_time_dependent_vars(self) -> None:
        self.x_lst.clear()
        self.y_lst.clear()
        self.state.reservoir.update_pressure_old()
        self.state.reservoir.update_energy_extracted_old()
        self.state.injection_well.update_dimensionless_time_old()
        self.state.production_well.update_dimensionless_time_old()
        self.state.production_well_pump.update_dimensionless_time_old()