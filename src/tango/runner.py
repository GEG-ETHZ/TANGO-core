import copy
import logging
import sys
import time
import json
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
from tqdm import tqdm

from dataclasses import dataclass
from tango.core.config import *
from tango.core.constants import *
from tango.workflow import *
from tango import utils

@dataclass
class RunnerSpecs():
    workflow: dict # workflow option
    # convergence criteria
    max_num_itr: int = 20
    dP_reservoir_threshold: float = 1000. # (Pa)
    dT_surface_threshold: float = 0.5  # (K)
    dP_surface_threshold: float = 100 # (Pa)


class Runner:

    def __init__(self,
                 specs: dict,
                 input_file: str):
        self.specs = specs
        self.input_file = input_file
        self.runspec = RunnerSpecs(**self.specs['runspec'])
        self.results = dict()
        self.set_func()
        self.start_time = time.time()
        logging.debug(f"Input summary:\n{json.dumps(self.specs, indent=4)}")


    def set_func(self) -> None:
        try:
            surface_facility_type = MAP_MODELNAME_TO_SURFACE_PLANT_DESIGN[self.specs['runspec']['workflow']['surface']]
        except:
            raise RuntimeError(f"Surface model: {self.specs['runspec']['workflow']['surface']} is not supported.")
        self.x_lst, self.y_lst = [], []
        self.x1_lst, self.y1_lst = [], []
        self.x2_lst, self.y2_lst = [], []
        self.x3_lst, self.y3_lst = [], []
        self.converged = getattr(self, f"converged_{surface_facility_type}")
        self.update_primary_variables = getattr(self, f"update_primary_variables_{surface_facility_type}")


    def set_workflow(self) -> None:
        try:
            self.state = WorkflowState(self.runspec.workflow)
            self.workflow = Workflow(self.specs, self.runspec.workflow)
            self.workflow.initialize(self.state)
        except:
            raise ValueError(f"Something went wrong while setting up workflow: {self.runspec.workflow}")


    def step(self) -> None:
        count = 0
        for j in range(self.runspec.max_num_itr):
            count += 1
            self.workflow.execute(self.state)
            if self.converged():
                logging.debug(f"Converged after {count} iterations")
                break
        if count == self.runspec.max_num_itr:
            logging.warning(f"Max number of iteration (={count}) has reached. Exiting iteration.")


    def save_results(self, current_date: datetime) -> None:
        """update self.results"""
        utils.parse_results(d=self.results,
                            state=self.state,
                            current_date=current_date.strftime(DATETIME_FMT))


    def run_models(self) -> None:

        logging.info(f"Running TANGO using {self.input_file}")

        logging.info(f"Executing physics-based models: {list(self.workflow.model_dict.keys())}")

        dt_months = np.round(self.specs['common']['dt'] * YEAR_TO_MONTH)
        num_time_steps = self.specs['common']['num_tsteps']
        current_date = datetime.strptime(self.specs['common']['start_date'], DATETIME_FMT)

        """
            loop over project lifetime
        """
        for i in tqdm(range(num_time_steps), desc="Progress: ", ncols = 100, file=sys.stdout):
            try:
                self.step()
            except:
                raise RuntimeError(f"Something went wrong at time step: {current_date}")
            self.save_results(current_date)
            self.update_primary_variables()
            current_date = current_date + relativedelta(months=dt_months)

        if self.workflow.economic is not None:
            logging.info(f"Executing economic models.")
            self.workflow.economic.execute(self.results)


    def post_processing(self) -> None:

        utils.write_results(input_file=self.input_file,
                            results_physics=self.results,
                            results_econ= self.workflow.economic.results if self.workflow.economic != None else None)

        logging.info(
            "Simulation finished normally. Elapsed time: {:.2f} seconds.".format(time.time() - self.start_time))


    def start(self) -> None:

        self.set_workflow()

        self.run_models()

        self.post_processing()


    """ 
        functions for CPG  
    """

    def converged_CPG(self) -> bool:

        dP_reservoir = self.state.reservoir.pressure_old - self.state.reservoir.outlet_fluid.P

        if np.abs(dP_reservoir) < self.runspec.dP_reservoir_threshold:
            return True

        self.x_lst.append(copy.deepcopy(self.state.surface.dP_pump))
        self.y_lst.append(dP_reservoir)
        if len(self.x_lst) == 1: # first call
            self.state.surface.dP_pump = 0.5 * dP_reservoir
        else:
            self.state.surface.dP_pump = utils.newton(self.x_lst, self.y_lst)
            self.x_lst.pop(0)
            self.y_lst.pop(0)

        self.workflow.surface.overwrite_pump_state(state=self.state.surface)

        return False


    def update_primary_variables_CPG(self) -> None:
        self.x_lst.clear()
        self.y_lst.clear()
        self.state.reservoir.pressure_old = copy.deepcopy(self.state.reservoir.outlet_fluid.P)
        self.state.reservoir.energy_extracted_old = copy.deepcopy(self.state.reservoir.energy_extracted)
        self.state.reservoir.energy_extracted_old = copy.deepcopy(self.state.reservoir.energy_extracted)


    """ 
        functions for ORC  
    """

    def converged_ORC(self) -> bool:

        dP_reservoir = self.state.reservoir.pressure_old - self.state.reservoir.outlet_fluid.P
        dT_surface = self.state.surface.outlet_temperature_tmp - self.state.surface.outlet_fluid.T
        dP_surface = self.state.surface.inlet_fluid.P - self.state.surface.outlet_fluid.P - self.state.surface.dP_pipe

        if np.abs(dP_reservoir) < self.runspec.dP_reservoir_threshold and \
           np.abs(dT_surface) < self.runspec.dT_surface_threshold and \
           np.abs(dP_surface) < self.runspec.dP_surface_threshold:
            return True

        self.x1_lst.append(copy.deepcopy(self.state.surface.outlet_fluid.P))
        self.x2_lst.append(copy.deepcopy(self.state.surface.outlet_fluid.T))
        self.x3_lst.append(copy.deepcopy(self.state.production_well_pump.dP_pump))
        self.y1_lst.append(dP_reservoir)
        self.y2_lst.append(dT_surface)
        self.y3_lst.append(dP_surface)
        if len(self.x1_lst) == 1: # first call
            root1 = self.state.surface.outlet_fluid.P + dP_reservoir
            root2 = self.state.surface.outlet_fluid.T
            root3 = -1.0 * dP_surface
        else:
            root1 = utils.newton(self.x1_lst, self.y1_lst) #TODO: try solving all together
            root2 = utils.newton(self.x2_lst, self.y2_lst)
            root3 = utils.newton(self.x3_lst, self.y3_lst)
            self.x1_lst.pop(0), self.x2_lst.pop(0), self.x3_lst.pop(0)
            self.y1_lst.pop(0), self.y2_lst.pop(0), self.y3_lst.pop(0)

        self.workflow.surface.overwrite_outlet_state(state=self.state.surface, P=root1, T=root2)
        self.state.production_well_pump.overwrite_state(state=self.state.production_well_pump,
                                                        dP_surface=dP_surface,
                                                        dP_pump=root3)

        return False


    def update_primary_variables_ORC(self) -> None:
        self.x1_lst.clear(), self.x2_lst.clear(), self.x3_lst.clear()
        self.y1_lst.clear(), self.y2_lst.clear(), self.y3_lst.clear()
        self.state.reservoir.pressure_old = copy.deepcopy(self.state.reservoir.outlet_fluid.P)
        self.state.reservoir.energy_extracted_old = copy.deepcopy(self.state.reservoir.energy_extracted)
        self.state.surface.outlet_temperature_tmp = copy.deepcopy(self.state.surface.outlet_fluid.T)
