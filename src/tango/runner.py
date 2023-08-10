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

# @dataclass
# class RunnerSpecs():
#     workflow: dict # workflow

class Runner:

    def __init__(self,
                 specs: dict,
                 input_file: str):
        self._specs = specs
        self._input_file = input_file
        self._dt_months = np.round(self._specs['common']['dt'] * YEAR_TO_MONTH)
        self._num_time_steps = self._specs['common']['num_tsteps']
        self._start_date = datetime.strptime(self._specs['common']['start_date'], DATETIME_FMT)

        self._results = dict()
        self._start_time = time.time()
        logging.debug(f"Input summary:\n{json.dumps(self._specs, indent=4)}")


    def _set_workflow(self) -> None:
        try:
            state = WorkflowState(self._specs['runspec']['workflow'])
            self._workflow = Workflow(self._specs)
            self._workflow.initialize(state)
        except:
            raise ValueError(f"Something went wrong while setting up workflow.")


    def _step(self) -> None:
        """ Advance one time step"""
        count = 0
        while True:
            if self._workflow.system.max_itr_reached(count):
                break
            count += 1
            self._workflow.execute()
            if self._workflow.system.balanced():
                logging.debug(f"System balanced after {count} iterations")
                break
            self._workflow.system.update()
        self._workflow.system.update_time_dependent_vars()


    def _save_results(self, current_date: datetime) -> None:
        """update self.results"""
        utils.parse_results(d=self._results,
                            state=self._workflow.state,
                            current_date=current_date.strftime(DATETIME_FMT))


    def _run_models(self) -> None:

        logging.info(f"Running TANGO using {self._input_file}")

        """
            loop over project lifetime
        """

        current_date = self._start_date
        for i in tqdm(range(self._num_time_steps), desc="Progress: ", ncols = 100, file=sys.stdout):
            try:
                self._step()
            except:
                raise RuntimeError(f"Something went wrong at time step: {current_date}")
            self._save_results(current_date)
            current_date = current_date + relativedelta(months=self._dt_months)

        if self._workflow.economic is not None:
            self._workflow.economic.execute(self._results)


    def _post_processing(self) -> None:
        utils.write_results(input_file=self._input_file,
                            results_physics=self._results,
                            results_econ= self._workflow.economic.get_results() if self._workflow.economic != None else None)
        logging.info("Simulation finished normally. Elapsed time: {:.2f} seconds.".format(time.time() - self._start_time))


    def start(self) -> None:

        self._set_workflow()

        self._run_models()

        self._post_processing()
