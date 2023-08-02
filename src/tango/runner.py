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
