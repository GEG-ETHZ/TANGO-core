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
from tango.utils import load_from_yaml
from tango.workflows.native_workflow import *


def get_workflow_class(type_: str) -> object:
    try:
        return eval(WORKFLOW_OPTIONS[type_])
    except:
        raise ValueErrorr(f"workflow type: {type_} is not supported.")


class Runner:

    def __init__(self, input_file: str):
        self._specs = load_from_yaml(input_file)
        self._input_file = input_file
        logging.debug(f"Input summary:\n{json.dumps(self._specs, indent=4)}")


    def _initialize_workflow(self) -> None:
        Workflow = get_workflow_class(self._specs['runspec']['workflow'])
        self._workflow = Workflow(self._specs, self._input_file)
        self._workflow.initialize()


    def start(self) -> None:

        logging.info(f"Running TANGO using {self._input_file}")

        self._start_time = time.time()

        self._initialize_workflow()

        self._workflow.execute()

        logging.info("Simulation finished normally. Elapsed time: {:.2f} seconds.".format(time.time() - self._start_time))
