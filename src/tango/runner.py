import copy
import itertools
import logging
import os
import shutil
import time
import uuid

import numpy as np
from tqdm import tqdm

from tango.utils import load_from_yaml_with_overrides
from tango.core.errors import CoolPropError
from tango.core.abstracts.workflow import Workflow
from tango.core.abstracts.unit import FlowResistance
from tango.workflows.cmg_workflow import CMGWorkflow
from tango.workflows.native_workflow import NativeWorkflow
from tango.optimizerr import Optimizer

WORKFLOW_OPTIONS: dict[str, type[Workflow]] = {
    "native": NativeWorkflow,
    "cmg": CMGWorkflow,
}


def get_workflow_class(type_: str) -> type[Workflow]:
    """Retrieve the workflow class based on the specified type.

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
    return WORKFLOW_OPTIONS[type_.lower()]


class BatchSimulation:
    """Handles batch simulations with parameter ranges.
    """

    def __init__(self, base_specs: dict, batch_config: dict):
        """Initialize batch simulation.
        
        Args:
            base_specs (dict): Base specifications
            batch_config (dict): Batch simulation configuration

        """
        self.base_specs = base_specs
        self.batch_config = batch_config
        self.inputs_list = batch_config.get("inputs_list", {})
        self.outputs_list = batch_config.get("outputs_list", [])
        self.time_steps = batch_config.get("time_steps", [])
        self.output_file_name = batch_config.get("output_file_name", "batch_simulation.csv")

    def generate_parameter_combinations(self):
        """Generate all parameter combinations from the ranges.
        
        Returns:
            list: List of parameter dictionaries for each simulation

        """
        param_values = {}

        flattened_params = self._flatten_inputs_list()

        for param_path, range_config in flattened_params.items():
            min_val = range_config["min"]
            max_val = range_config["max"]
            points = range_config["points"]

            print(f"Processing parameter range: {param_path}")
            print(f"  Original values - min: {min_val} ({type(min_val)}), max: {max_val} ({type(max_val)}), points: {points} ({type(points)})")

            try:
                if isinstance(min_val, str):
                    if "e" in min_val.lower():
                        min_val = float(min_val)
                    else:
                        min_val = float(min_val)
                if isinstance(max_val, str):
                    if "e" in max_val.lower():
                        max_val = float(max_val)
                    else:
                        max_val = float(max_val)
                if isinstance(points, str):
                    points = int(points)

                print(f"  Converted values - min: {min_val} ({type(min_val)}), max: {max_val} ({type(max_val)}), points: {points} ({type(points)})")

            except (ValueError, TypeError) as e:
                print(f"Error converting parameter {param_path}: {e}")
                print(f"  min_val: {min_val} (type: {type(min_val)})")
                print(f"  max_val: {max_val} (type: {type(max_val)})")
                print(f"  points: {points} (type: {type(points)})")
                continue

            if points == 1:
                param_values[param_path] = [min_val]
            else:
                param_values[param_path] = np.linspace(min_val, max_val, points).tolist()

            print(f"  Generated values: {param_values[param_path]}")

        param_names = list(param_values.keys())
        param_value_lists = list(param_values.values())

        combinations = []
        for combination in itertools.product(*param_value_lists):
            param_dict = dict(zip(param_names, combination))
            combinations.append(param_dict)

        print(f"Generated {len(combinations)} parameter combinations")
        return combinations

    def _flatten_inputs_list(self):
        """Flatten the nested inputs_list structure to get parameter paths.
        
        Returns:
            dict: Dictionary with parameter paths as keys and range configs as values

        """
        flattened = {}

        for section_name, section_config in self.inputs_list.items():
            if isinstance(section_config, dict):
                for param_name, param_config in section_config.items():
                    if isinstance(param_config, dict) and "min" in param_config and "max" in param_config and "points" in param_config:
                        param_path = f"{section_name}.{param_name}"
                        flattened[param_path] = param_config
                    elif isinstance(param_config, dict):
                        for nested_param_name, nested_param_config in param_config.items():
                            if isinstance(nested_param_config, dict) and "min" in nested_param_config and "max" in nested_param_config and "points" in nested_param_config:
                                param_path = f"{section_name}.{param_name}.{nested_param_name}"
                                flattened[param_path] = nested_param_config

        return flattened

    def set_nested_parameter(self, specs: dict, param_path: str, value):
        """Set a nested parameter in the specifications.
        
        Args:
            specs (dict): Specifications to modify
            param_path (str): Parameter path (e.g., 'injection_well.diameter')
            value: Value to set

        """
        if "." in param_path:
            parts = param_path.split(".")
            current = specs
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        else:
            specs[param_path] = value

    def run_batch_simulation(self, input_file: str):
        """Run the batch simulation.
        
        Args:
            input_file (str): Input file path

        """
        combinations = self.generate_parameter_combinations()
        total_simulations = len(combinations)

        print(f"Starting batch simulation with {total_simulations} parameter combinations:")
        for i, combo in enumerate(combinations):
            print(f"  Simulation {i + 1}: {combo}")

        self.prepare_csv_file(combinations)

        for i, param_combo in enumerate(tqdm(combinations, desc="Batch Simulation Progress")):
            print(f"\n--- Running Simulation {i + 1}/{total_simulations} ---")
            print(f"Parameters: {param_combo}")

            modified_specs = copy.deepcopy(self.base_specs)

            for param_path, value in param_combo.items():
                self.set_nested_parameter(modified_specs, param_path, value)

            tango = Tango(input_file, specs=modified_specs)
            tango.execute()

            self.write_simulation_results(tango, param_combo, i + 1)

    def prepare_csv_file(self, combinations):
        """Prepare the CSV file with headers.
        
        Args:
            combinations (list): List of parameter combinations

        """
        import csv

        headers = []

        for param_name in combinations[0].keys():
            headers.append(param_name)

        economic_outputs = ["LCOE", "CAPEX_well", "CAPEX_surface_pipe", "CAPEX_power_plant",
                           "CAPEX_permitting", "CAPEX_exploration", "CAPEX_wells", "CAPEX_total"]

        for output_name in self.outputs_list:
            if output_name in economic_outputs:
                headers.append(output_name)
            else:
                for time_step in self.time_steps:
                    headers.append(f"{output_name}_{time_step}")

        try:
            with open(self.output_file_name, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(headers)
            print(f"Created CSV file: {self.output_file_name}")
        except Exception as e:
            print(f"Error creating CSV file: {e}")

    def write_simulation_results(self, tango, param_combo, simulation_number):
        """Write results for a single simulation to CSV.
        
        Args:
            tango: Tango instance with completed simulation
            param_combo (dict): Parameter combination used
            simulation_number (int): Simulation number

        """
        import csv

        input_values = list(param_combo.values())

        output_values = []
        economic_outputs = ["LCOE", "CAPEX_well", "CAPEX_surface_pipe", "CAPEX_power_plant",
                           "CAPEX_permitting", "CAPEX_exploration", "CAPEX_wells", "CAPEX_total"]

        for output_name in self.outputs_list:
            if output_name in economic_outputs:
                if hasattr(tango.workflow, "economic") and tango.workflow.economic:
                    if output_name in tango.workflow.economic._results:
                        output_values.append(tango.workflow.economic._results[output_name])
                    else:
                        output_values.append(None)
                else:
                    output_values.append(None)
            else:
                if output_name in tango.workflow._results:
                    values = tango.workflow._results[output_name]
                    for time_step in self.time_steps:
                        try:
                            ts_idx = int(time_step)
                        except (TypeError, ValueError):
                            output_values.append(None)
                            continue
                        # Interpret time_steps as 1-based indices if positive
                        idx = ts_idx - 1 if ts_idx > 0 else ts_idx
                        if -len(values) <= idx < len(values):
                            output_values.append(values[idx])
                        else:
                            output_values.append(None)
                else:
                    for _ in self.time_steps:
                        output_values.append(None)

        try:
            with open(self.output_file_name, "a", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                row_data = input_values + output_values
                writer.writerow(row_data)
        except Exception as e:
            print(f"Error writing to CSV: {e}")


class Tango:
    """A class for managing and executing TANGO workflows.

    This class handles loading input specifications, initializing the workflow,
    and executing the workflow simulation.

    Attributes:
    ----------
    specs : dict
        The specifications for the TANGO workflow, loaded from a YAML file or provided directly.
    input_file : str
        The path to the input YAML file.
    workflow : object
        The initialized workflow object, created based on the `runspec['workflow']` value.

    Example:
    -------
    >>> tango = Tango("input.yaml")
    >>> tango.execute()

    """

    def __init__(
        self,
        input_file: str,
        specs: dict | None = None,
        parameter_overrides: list | None = None,
        params_json: str | None = None,
        user_id: str | None = None,
    ):
        """Initializes the Tango object.

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
        user_id : str, optional
            User ID for database operations.

        """
        # these messages are here because the overrides are applied right after this
        if params_json is not None:
            print(f"Applying JSON parameter overrides: {params_json}")

        if parameter_overrides:
            print(f"Applying {len(parameter_overrides)} parameter overrides:")
            for override in parameter_overrides:
                print(f"  {override}")

        if specs is None:
            self.specs = load_from_yaml_with_overrides(input_file, parameter_overrides, params_json)
        else:
            from tango.utils import apply_parameter_overrides
            self.specs = apply_parameter_overrides(specs, parameter_overrides, params_json)

        self.input_file = input_file
        self.user_id = user_id

        # Generate unique run ID for file naming
        self.run_id = str(uuid.uuid4())[:8]  # Short unique ID

        # Create gen_files directory if it doesn't exist
        self.gen_files_dir = os.path.join(os.path.dirname(__file__), "gen_files")
        os.makedirs(self.gen_files_dir, exist_ok=True)

        # Create run-specific subdirectory
        self.run_dir = os.path.join(self.gen_files_dir, f"run_{self.run_id}")
        os.makedirs(self.run_dir, exist_ok=True)

        logging.info(f"Created unique run directory: {self.run_dir}")

    def _initialize_workflow(self) -> None:
        """Initializes the workflow based on the specifications.

        Notes
        -----
        - The workflow type is specified in `runspec['workflow']` in the specifications.
        - Retrieves the workflow class using `get_workflow_class()`.

        Raises
        ------
        ValueError
            If the workflow type is not supported.

        """
        workflow_class  = get_workflow_class(self.specs["runspec"]["workflow"])
        # print('self.specs',self.specs)
        self.workflow: Workflow = workflow_class(self.specs, self.input_file, self.user_id, self.run_id, self.run_dir)

    def execute(self) -> None:
        """Execute the TANGO workflow.

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

        try:
            self.workflow.execute()
        except CoolPropError as cpe:
            res_dict = {
                k: v.flow_res() for (k, v) in
                    self.workflow.orchestrator.unit.__dict__.items() if isinstance(v, FlowResistance)
            }
            res_denom = sum(res_dict.values())
            res_str = "\n\t\t".join(
                [f"{k}: {v / res_denom:.3%}" for (k, v) in res_dict.items()])
            new_err = (
                str(cpe)
                + "\n\tApprox. flow resistances, scaled relative to sum of module resistances"
                + "\n\tNOTES:"
                + "\n\t- the reservoir is expected to dominate total system resistance"
                + "\n\t- Resistances are calculated based solely on system specs to avoid needing"
                + "\n\t  fluid properties, in case property calculations fail, and should thus be "
                + "\n\t  considered approximate."
                + "\n\t- Total injection well resistance and production well resistance should"
                + "\n\t  be of similar magnitude\n"
                + "\n\tVALUES:\n\t\t"
                + res_str
            )
            raise type(cpe)(new_err) from cpe

        logging.info(f"Simulation finished normally. Elapsed time: {time.time() - self._start_time:.2f} seconds.")

        # Cleanup generated run directory after successful completion
        try:
            if os.path.isdir(self.run_dir):
                # Only remove if the run_dir is within the gen_files directory for safety
                gen_files_abs = os.path.abspath(self.gen_files_dir)
                run_dir_abs = os.path.abspath(self.run_dir)
                if run_dir_abs.startswith(gen_files_abs + os.sep):
                    shutil.rmtree(self.run_dir, ignore_errors=True)
                    logging.info(f"Cleaned up run directory: {self.run_dir}")
                else:
                    logging.warning(f"Skipped cleanup for unexpected path: {self.run_dir}")
        except Exception as cleanup_err:
            logging.error(f"Failed to cleanup run directory {self.run_dir}: {cleanup_err}")

    def execute_batch_simulation(self) -> None:
        """Executes batch simulation if configured.
        """
        if "batch_simulation" in self.specs and self.specs["batch_simulation"].get("enabled", False):
            batch_sim = BatchSimulation(self.specs, self.specs["batch_simulation"])
            batch_sim.run_batch_simulation(self.input_file)
        else:
            self.execute()


class Runner:
    """Wrapper class for `Tango` and `Optimizer`"""

    def __init__(
        self,
        input_file: str,
        parameter_overrides: list | None = None,
        params_json: str | None = None,
        user_id: str | None = None,
    ):
        """Initialize the Runner"""
        self._tango = Tango(
            input_file,
            parameter_overrides=parameter_overrides,
            params_json=params_json,
            user_id=user_id,
        )
        self._optimizer = None
        if "optimization" in self._tango.specs:
            self._optimizer = Optimizer(self._tango, self._tango.specs)

    def start(self) -> None:
        """Start the execution of the workflow. If 'optimization' is present in the specs,
        use the optimizer. Otherwise, check for batch simulation or use regular Tango execution.
        """
        # TODO: we should probably make sure that if `self._optimizer is not None` and
        # ```
        # "batch_simulation" in self._tango.specs and self._tango.specs["batch_simulation"].get(
        #     "enabled", False
        # )
        # ```
        # that an error is thrown because that combination does not make sense
        # because it's not possible to do both
        if self._optimizer is not None:
            print("Optimization detected. Executing optimizer...")
            self._optimizer.execute()
        elif "batch_simulation" in self._tango.specs and self._tango.specs["batch_simulation"].get(
            "enabled", False
        ):
            print("Batch simulation detected. Executing batch simulation...")
            self._tango.execute_batch_simulation()
        else:
            print("No optimization or batch simulation detected. Executing Tango workflow...")
            self._tango.execute()
