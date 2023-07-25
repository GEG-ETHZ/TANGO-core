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
        self.start_time = time.time()
        logging.debug(f"Input summary:\n{json.dumps(self.specs, indent=4)}")


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
                            results_econ=self.workflow.economic.results)

        logging.info(
            "Simulation finished normally. Elapsed time: {:.2f} seconds.".format(time.time() - self.start_time))


    def start(self) -> None:

        self.set_workflow()

        self.run_models()

        self.post_processing()


