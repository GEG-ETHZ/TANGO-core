import copy
import logging
import sys
import time
import json
import numpy as np
import inspect
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
    # title: str = 'title' # title of run
    workflow: dict # workflow option


class Runner:

    def __init__(self,
                 specs: dict,
                 input_file: str):
        self.specs = specs
        self.input_file = input_file
        self.runspec = RunnerSpecs(**self.specs['runspec'])
        self.results = dict()
        self.start_time = time.time()
        logging.debug(f"Input summary:\n{json.dumps(self.specs, indent=4)}")


    def set_workflow(self) -> None:
        try:
            state = WorkflowState(self.runspec.workflow)
            self.workflow = Workflow(self.specs, self.runspec.workflow)
            self.workflow.initialize(state)
        except:
            raise ValueError(f"Something went wrong while setting up workflow: {self.runspec.workflow}")


    def step(self) -> None:
        """ Advance one time step"""
        count = 0
        while True:
            if self.workflow.system.max_itr_reached(count):
                break
            count += 1
            self.workflow.execute()
            if self.workflow.system.balanced():
                logging.debug(f"System balanced after {count} iterations")
                break
            self.workflow.system.update()
        self.workflow.system.update_time_dependent_vars()


    def save_results(self, current_date: datetime) -> None:
        """update self.results"""
        utils.parse_results(d=self.results,
                            state=self.workflow.state,
                            current_date=current_date.strftime(DATETIME_FMT))


    def run_models(self) -> None:

        logging.info(f"Running TANGO using {self.input_file}")

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
            current_date = current_date + relativedelta(months=dt_months)

        if self.workflow.economic is not None:
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
        functions for ORC  
    """

    def local_loop_Pinj(self) -> None:
        dP_reservoir = self.state.reservoir.pressure_old - self.state.reservoir.outlet_fluid.P
        x_lst, y_lst = [], []
        count = 0
        while np.abs(dP_reservoir) > self.runspec.dP_reservoir_threshold:
            if self.max_itr_reached(count):
                break
            x_lst.append(copy.deepcopy(self.state.injection_well.inlet_fluid.P))
            y_lst.append(dP_reservoir)
            if len(x_lst) == 1:  # first call
                root = x_lst[0] + dP_reservoir
            else:
                root = utils.newton(x_lst, y_lst)
                x_lst.pop(0), y_lst.pop(0)

            self.workflow.injection_well.overwrite_inlet_fluid_state_PT(P=root)
            self.workflow.injection_well.execute()
            self.workflow.reservoir.execute(state=self.state.reservoir)
            dP_reservoir = self.state.reservoir.pressure_old - self.state.reservoir.outlet_fluid.P
            count += 1


    def local_loop_dP_pump(self) -> None:
        dP_surface = self.state.surface.inlet_fluid.P - self.state.injection_well.inlet_fluid.P - self.state.surface.dP_pipe
        if self.state.production_well_pump.dP_pump == 0. and dP_surface >= 0:
            return # no pummping needed
        x_lst, y_lst = [], []
        count = 0
        while np.abs(dP_surface) > self.runspec.dP_surface_threshold:
            if self.max_itr_reached(count):
                break
            x_lst.append(copy.deepcopy(self.state.production_well_pump.dP_pump))
            y_lst.append(dP_surface)
            if len(x_lst) == 1:  # first call
                root = -1.0 * dP_surface
            else:
                root = utils.newton(x_lst, y_lst)
                x_lst.pop(0), y_lst.pop(0)

            self.workflow.production_well_pump.overwrite_inlet_fluid_state_P(state=self.state.production_well_pump,
                                                                             dP_pump=root)
            self.workflow.production_well_pump.execute()
            self.workflow.surface.update_state_pipe(state=self.state.surface)

            dP_surface = self.state.production_well_pump.outlet_fluid.P \
                       - self.state.injection_well.inlet_fluid.P \
                       - self.state.surface.dP_pipe
            count += 1
        self.workflow.production_well_pump.update_w_pump(state=self.state.production_well_pump)


    def converged_ORC(self) -> bool:

        dT_surface = self.state.injection_well.inlet_fluid.T - self.state.surface.outlet_fluid.T
        if np.abs(dT_surface) < self.runspec.dT_surface_threshold:
            return True

        self.local_loop_Pinj()

        self.workflow.production_well.execute()

        self.local_loop_dP_pump()

        self.workflow.surface.execute(state=self.state.surface)

        return False

    def update_primary_variables_ORC(self) -> None:
        self.x1_lst.clear(), self.x2_lst.clear(), self.x3_lst.clear()
        self.y1_lst.clear(), self.y2_lst.clear(), self.y3_lst.clear()
        self.state.reservoir.pressure_old = copy.deepcopy(self.state.reservoir.outlet_fluid.P)
        self.state.reservoir.energy_extracted_old = copy.deepcopy(self.state.reservoir.energy_extracted)
        self.state.surface.outlet_temperature_tmp = copy.deepcopy(self.state.surface.outlet_fluid.T)

    #TODO: Implement AGS. Test cases with multiple compute nodes with the same name (e.g., inj_well-inj_well)
