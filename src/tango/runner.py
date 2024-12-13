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
    """
    Retrieves the workflow class corresponding to the given type.

    Args:
        type_ (str): The type of workflow to retrieve.

    Returns:
        object: The workflow class corresponding to the specified type.

    Raises:
        ValueError: If the specified workflow type is not supported.

    Example:
        >>> workflow_class = get_workflow_class("example_type")
    """
    try:
        return eval(WORKFLOW_OPTIONS[type_.lower()])
    except:
        raise ValueError(f"workflow type: {type_} is not supported.")


class Runner:
    """
    Runner class to execute workflows based on input specifications.

    Attributes:
        _specs (dict): Specifications loaded from the input YAML file.
        _input_file (str): Path to the input file.
    """

    def __init__(self, input_file: str):
        """
        Initializes the Runner object by loading specifications from the input file.

        Args:
            input_file (str): Path to the input YAML file containing specifications.
        """
        self._specs = load_from_yaml(input_file)
        self._input_file = input_file
        logging.debug(f"Input summary:\n{json.dumps(self._specs, indent=4)}")

    def _initialize_workflow(self) -> None:
        """
        Initializes the workflow instance using the workflow class specified in the input file.

        The workflow type is retrieved from `self._specs['runspec']['workflow']`.

        Returns:
            None
        """
        Workflow = get_workflow_class(self._specs['runspec']['workflow'])
        self._workflow = Workflow(self._specs, self._input_file)

    def start(self) -> None:
        """
        Starts the workflow execution.

        Logs the start time and executes the workflow specified in the input file.

        Returns:
            None
        """
        logging.info(f"Running TANGO using {self._input_file}")
        self._start_time = time.time()

        self._initialize_workflow()
        self._workflow.execute()

        logging.info("Simulation finished normally. Elapsed time: {:.2f} seconds.".format(time.time() - self._start_time))
