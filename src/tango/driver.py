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
from tango.workflows.cmg_workflow import *


def get_workflow_class(type_: str) -> object:
    try:
        return eval(WORKFLOW_OPTIONS[type_.lower()])
    except:
        raise ValueError(f"workflow type: {type_} is not supported.")


class Tango:

    def __init__(self,
                 input_file: str,
                 specs: dict = None):
        self.specs = load_from_yaml(input_file) if specs == None else specs
        self.input_file = input_file
        # self._initialize_workflow()


    def _initialize_workflow(self) -> None:
        Workflow = get_workflow_class(self.specs['runspec']['workflow'])
        self.workflow = Workflow(self.specs, self.input_file)


    def execute(self) -> None:

        logging.info(f"Running TANGO using {self.input_file}")

        self._initialize_workflow()

        self._start_time = time.time()

        self.workflow.execute()

        logging.info("Simulation finished normally. Elapsed time: {:.2f} seconds.".format(time.time() - self._start_time))
