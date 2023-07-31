from tango.models.base import *
from tango.core.config import *
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

    def __init__(self, state):
        super().__init__(state)
        self.x_lst, self.y_lst = [], []
        self.max_num_itr = CONVERGENCE_CRITERIA['max_num_itr']

    def max_itr_reached(self, count) -> bool:
        if count > self.max_num_itr:
            logging.warning(f"Max number of iteration (={count}) has reached in {inspect.stack()[1][3]}. Exiting iteration.")
            return True
        return False


class SystemCPGAdams(SystemAdams):

    def __init__(self, state, models):
        super().__init__(state)
        self.surface_model = models['surface']
        self.set_convergence_criteria()


    def set_convergence_criteria(self) -> None:
        self.dP_reservoir_threshold: float = CONVERGENCE_CRITERIA['dP_reservoir']


    def balanced(self) -> bool:
        self.dP_reservoir = self.state.reservoir.pressure_old - self.state.reservoir.outlet_fluid.P
        if np.abs(self.dP_reservoir) < self.dP_reservoir_threshold:
            return True
        return False


    def update(self) -> None:
        """update unknown to balance the system"""
        self.x_lst.append(copy.deepcopy(self.state.surface.dP_pump))
        self.y_lst.append(self.dP_reservoir)
        if len(self.x_lst) == 1: # first call
            self.state.surface.dP_pump = 0.5 * self.dP_reservoir
        else:
            self.state.surface.dP_pump = utils.newton(self.x_lst, self.y_lst)
            self.x_lst.pop(0)
            self.y_lst.pop(0)
        self.surface_model.overwrite_pump_state(state=self.state.surface)


    def update_time_dependent_vars(self) -> None:
        self.x_lst.clear()
        self.y_lst.clear()
        self.state.reservoir.pressure_old = copy.deepcopy(self.state.reservoir.outlet_fluid.P)
        self.state.reservoir.energy_extracted_old = copy.deepcopy(self.state.reservoir.energy_extracted)


class SystemORCAdams(SystemAdams):

    def __init__(self, state, models):
        super().__init__(state)
        self.set_models(models)
        self.set_convergence_criteria()


    def set_models(self, models: dict) -> None:
        for name in models.keys():
            setattr(self, name, models[name])


    def set_convergence_criteria(self) -> None:
        self.dP_reservoir_threshold: float = CONVERGENCE_CRITERIA['dP_reservoir']
        self.dP_surface_threshold: float = CONVERGENCE_CRITERIA['dP_surface']
        self.dT_surface_threshold: float = CONVERGENCE_CRITERIA['dP_surface']


    def balanced(self) -> bool:
        dP_reservoir = self.state.reservoir.pressure_old - self.state.reservoir.outlet_fluid.P
        dP_surface = self.state.surface.inlet_fluid.P - self.state.injection_well.inlet_fluid.P - self.state.surface.dP_pipe
        dT_surface = self.state.injection_well.inlet_fluid.T - self.state.surface.outlet_fluid.T
        if  np.abs(dP_reservoir) < self.dP_reservoir_threshold and \
            np.abs(dP_surface) < self.dP_surface_threshold and \
            np.abs(dT_surface) < self.dT_surface_threshold:
            return True
        return False


    def update(self) -> None:
        """update unknown to balance the system"""
        self.update_Pinj()

        self.production_well.execute()

        self.production_well_pump.execute()

        self.update_dP_pump()

        self.surface.execute(state=self.state.surface)

        self.update_Tinj()


    def update_Pinj(self) -> None:
        dP_reservoir = self.state.reservoir.pressure_old - self.state.reservoir.outlet_fluid.P
        x_lst, y_lst = [], []
        count = 0
        while np.abs(dP_reservoir) > self.dP_reservoir_threshold:
            if self.max_itr_reached(count):
                break
            x_lst.append(copy.deepcopy(self.state.injection_well.inlet_fluid.P))
            y_lst.append(dP_reservoir)
            if len(x_lst) == 1:  # first call
                root = x_lst[0] + dP_reservoir
            else:
                root = utils.newton(x_lst, y_lst)
                x_lst.pop(0), y_lst.pop(0)

            self.injection_well.overwrite_inlet_fluid_state_PT(P=root)
            self.injection_well.execute()
            self.reservoir.execute(state=self.state.reservoir)
            dP_reservoir = self.state.reservoir.pressure_old - self.state.reservoir.outlet_fluid.P
            count += 1


    def update_dP_pump(self) -> None:
        dP_surface = self.state.surface.inlet_fluid.P - self.state.injection_well.inlet_fluid.P - self.state.surface.dP_pipe
        if self.state.production_well_pump.dP_pump == 0. and dP_surface >= 0:
            return # no pummping needed
        x_lst, y_lst = [], []
        count = 0
        while np.abs(dP_surface) > self.dP_surface_threshold:
            if self.max_itr_reached(count):
                break
            x_lst.append(copy.deepcopy(self.state.production_well_pump.dP_pump))
            y_lst.append(dP_surface)
            if len(x_lst) == 1:  # first call
                root = -1.0 * dP_surface
            else:
                root = utils.newton(x_lst, y_lst)
                x_lst.pop(0), y_lst.pop(0)

            self.production_well_pump.overwrite_inlet_fluid_state_P(state=self.state.production_well_pump,
                                                                    dP_pump=root)
            self.production_well_pump.execute()
            self.surface.update_state_pipe(state=self.state.surface)

            dP_surface = self.state.production_well_pump.outlet_fluid.P \
                       - self.state.injection_well.inlet_fluid.P \
                       - self.state.surface.dP_pipe
            count += 1
        self.production_well_pump.update_w_pump(state=self.state.production_well_pump)


    def update_Tinj(self) -> None:
        dT_surface = self.state.injection_well.inlet_fluid.T - self.state.surface.outlet_fluid.T
        self.x_lst.append(copy.deepcopy(self.state.injection_well.inlet_fluid.T))
        self.y_lst.append(dT_surface)
        if len(self.x_lst) == 1: # first call
            root = self.state.surface.outlet_fluid.T
        else:
            root = utils.newton(self.x_lst, self.y_lst)
            self.x_lst.pop(0)
            self.y_lst.pop(0)
        self.injection_well.overwrite_inlet_fluid_state_PT(T=root)


    def update_time_dependent_vars(self) -> None:
        self.x_lst.clear()
        self.y_lst.clear()
        self.state.reservoir.pressure_old = copy.deepcopy(self.state.reservoir.outlet_fluid.P)
        self.state.reservoir.energy_extracted_old = copy.deepcopy(self.state.reservoir.energy_extracted)
        self.state.surface.outlet_temperature_tmp = copy.deepcopy(self.state.surface.outlet_fluid.T) # todo: not sure if this is needed
