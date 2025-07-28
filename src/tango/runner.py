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
from tango.utils import load_from_yaml_with_overrides
from tango.workflows.native_workflow import NativeWorkflow
from tango.workflows.cmg_workflow import CMGWorkflow


WORKFLOW_OPTIONS = {
    "native": "NativeWorkflow",
    "cmg": "CMGWorkflow"
}


def get_workflow_class(type_: str) -> object:
    """
    Retrieves the workflow class based on the specified type.

    This function looks up the `WORKFLOW_OPTIONS` dictionary to find and
    return the corresponding workflow class for the provided type.

    Parameters
    ----------
    type_ : str
        The workflow type (case-insensitive).

    Returns
    -------
    object
        The workflow class associated with the specified type.

    Raises
    ------
    ValueError
        If the specified workflow type is not supported.

    Example
    -------
    >>> workflow_class = get_workflow_class("example")
    >>> print(workflow_class)
    <class 'ExampleWorkflow'>
    """
    try:
        return eval(WORKFLOW_OPTIONS[type_.lower()])
    except:
        raise ValueError(f"workflow type: {type_} is not supported.")


class Tango:
    """
    A class for managing and executing TANGO workflows.

    This class handles loading input specifications, initializing the workflow,
    and executing the workflow simulation.

    Attributes
    ----------
    specs : dict
        The specifications for the TANGO workflow, loaded from a YAML file or provided directly.
    input_file : str
        The path to the input YAML file.
    workflow : object
        The initialized workflow object, created based on the `runspec['workflow']` value.

    Example
    -------
    >>> tango = Tango("input.yaml")
    >>> tango.execute()
    """

    def __init__(self, input_file: str, specs: dict = None, parameter_overrides: list = None, params_json: str = None):
        """
        Initializes the Tango object.

        Parameters
        ----------
        input_file : str
            The path to the input YAML file.
        specs : dict, optional
            A dictionary containing workflow specifications. If not provided, it is loaded from `input_file`.
        parameter_overrides : list, optional
            List of parameter override strings in format "section.parameter=value".
        params_json : str, optional
            JSON string with multiple parameter overrides.
        """
        if specs is None:
            self.specs = load_from_yaml_with_overrides(input_file, parameter_overrides, params_json)
        else:
            from tango.utils import apply_parameter_overrides
            self.specs = apply_parameter_overrides(specs, parameter_overrides, params_json)
        
        self.input_file = input_file

    def _initialize_workflow(self) -> None:
        """
        Initializes the workflow based on the specifications.

        Notes
        -----
        - The workflow type is specified in `runspec['workflow']` in the specifications.
        - Retrieves the workflow class using `get_workflow_class()`.

        Raises
        ------
        ValueError
            If the workflow type is not supported.
        """
        Workflow = get_workflow_class(self.specs['runspec']['workflow'])
        # print('self.specs',self.specs)
        self.workflow = Workflow(self.specs, self.input_file)

    def execute(self) -> None:
        """
        Executes the TANGO workflow.

        Logs the start time, initializes the workflow, and executes it.
        Also logs the elapsed time after the simulation is complete.

        Raises
        ------
        Exception
            If an error occurs during the workflow execution.

        Logs
        ----
        - Workflow execution start and end times.
        - Total elapsed time for the simulation.
        """
        logging.info(f"Running TANGO using {self.input_file}")

        self._initialize_workflow()

        self._start_time = time.time()

        self.workflow.execute()

        logging.info("Simulation finished normally. Elapsed time: {:.2f} seconds.".format(time.time() - self._start_time))

