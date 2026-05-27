import copy
import hashlib
import itertools
import json
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
from tqdm import tqdm

from tango.core.abstracts.workflow import Workflow
from tango.optimizerr import Optimizer
from tango.utils import load_from_yaml_with_overrides, set_logger, set_nested_value
from tango.workflows.cmg_workflow import CMGWorkflow
from tango.workflows.native_workflow import NativeWorkflow

WORKFLOW_MAP: dict[str, type[Workflow]] = {
    "native": NativeWorkflow,
    "cmg": CMGWorkflow,
}


class BatchSimulation:
    """Handles batch simulations with parameter ranges."""

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

            logging.debug(f"Processing parameter range: {param_path}")
            logging.debug(
                f"  Original values - min: {min_val} ({type(min_val)}), "
                f"max: {max_val} ({type(max_val)}), points: {points} ({type(points)})",
            )

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

                logging.debug(
                    f"  Converted values - min: {min_val} ({type(min_val)}), "
                    f"max: {max_val} ({type(max_val)}), points: {points} ({type(points)})",
                )

            except (ValueError, TypeError) as e:
                raise type(e)(
                    f"Error converting parameter {param_path}: {e}\n"
                    f"  min_val: {min_val} (type: {type(min_val)})\n"
                    f"  max_val: {max_val} (type: {type(max_val)})\n"
                    f"  points: {points} (type: {type(points)})",
                ) from e

            if points == 1:
                param_values[param_path] = [min_val]
            else:
                param_values[param_path] = np.linspace(min_val, max_val, points).tolist()

            logging.debug(f"  Generated values: {param_values[param_path]}")

        param_names = list(param_values.keys())
        param_value_lists = list(param_values.values())

        combinations = []
        for combination in itertools.product(*param_value_lists):
            param_dict = dict(zip(param_names, combination))
            combinations.append(param_dict)

        logging.info(f"Generated {len(combinations)} parameter combinations")
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
                    if (
                        isinstance(param_config, dict)
                        and "min" in param_config
                        and "max" in param_config
                        and "points" in param_config
                    ):
                        param_path = f"{section_name}.{param_name}"
                        flattened[param_path] = param_config
                    elif isinstance(param_config, dict):
                        for nested_param_name, nested_param_config in param_config.items():
                            if (
                                isinstance(nested_param_config, dict)
                                and "min" in nested_param_config
                                and "max" in nested_param_config
                                and "points" in nested_param_config
                            ):
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

        logging.info(f"Starting batch simulation with {total_simulations} parameter combinations:")
        for i, combo in enumerate(combinations):
            logging.debug(f"  Simulation {i + 1}: {combo}")

        self.prepare_csv_file(combinations)

        disable_progress = logging.getLogger().getEffectiveLevel() > logging.INFO
        for i, param_combo in enumerate(
            tqdm(combinations, desc="Batch Simulation Progress", disable=disable_progress),
        ):
            logging.info(f"\n--- Running Simulation {i + 1}/{total_simulations} ---")
            logging.debug(f"Parameters: {param_combo}")

            modified_specs = copy.deepcopy(self.base_specs)

            for param_path, value in param_combo.items():
                self.set_nested_parameter(modified_specs, param_path, value)

            # TODO: instantiate TANGO then modify specs because there's no need
            # to pass specs in as an argument since the `update_params` method
            # was created
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

        economic_outputs = [
            "LCOE",
            "CAPEX_well",
            "CAPEX_surface_pipe",
            "CAPEX_power_plant",
            "CAPEX_permitting",
            "CAPEX_exploration",
            "CAPEX_wells",
            "CAPEX_total",
        ]

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
            logging.info(f"Created CSV file: {self.output_file_name}")
        except Exception as e:
            raise type(e)(f"Error creating CSV file: {e}") from e

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
        economic_outputs = [
            "LCOE",
            "CAPEX_well",
            "CAPEX_surface_pipe",
            "CAPEX_power_plant",
            "CAPEX_permitting",
            "CAPEX_exploration",
            "CAPEX_wells",
            "CAPEX_total",
        ]

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
            raise type(e)(f"Error writing to CSV: {e}") from e


class Tango:
    """A class for managing and executing TANGO workflows.

    This class handles loading input specifications, initializing the workflow,
    and executing the workflow simulation.

    Attributes:
    ----------
    input_file : str
        The path to the input YAML file.
    workflow : object
        The initialized workflow object, created based on the `runspec['workflow']` value.

    Example:
    -------
    >>> tango = Tango("input.yaml")
    >>> tango.execute()

    """

    # TODO: update `Attributes` in the doc string above

    def __init__(
        self,
        input_file: Path,
        save_dir: Path | None,
        specs: dict | None = None,
        parameter_overrides: list | None = None,
        user_id: str | None = None,
    ):
        """Initialize the Tango object.

        Parameters
        ----------
        input_file : str
            The path to the input YAML file.
        specs : dict, optional
            A dictionary containing workflow specifications. If not provided, it is loaded from `input_file`.
        parameter_overrides : list, optional
            List of parameter override strings in format "section.parameter=value".
        user_id : str, optional
            User ID for database operations.

        """
        # TODO: update the above args to match function signature
        if parameter_overrides:
            logging.info(f"Applying {len(parameter_overrides)} parameter overrides:")
            for override in parameter_overrides:
                logging.debug(f"  {override}")

        if specs is None:
            self.specs = load_from_yaml_with_overrides(input_file, parameter_overrides)
        else:
            from tango.utils import apply_parameter_overrides

            self.specs = apply_parameter_overrides(specs, parameter_overrides)

        self.input_file = (Path().cwd() / input_file).resolve()
        self.user_id = user_id

        # Create gen_files directory if it doesn't exist
        if save_dir is not None:
            self.gen_files_dir: Path | None = Path(save_dir) / "gen_files"
            self.gen_files_dir.mkdir(exist_ok=True, parents=True)
        else:
            self.gen_files_dir = None

        self._setup_run_directory()

    def get_hash_from_specs(self) -> str:
        """Generate a deterministic hash from specs."""
        specs_str = json.dumps(self.specs, sort_keys=True)
        return hashlib.sha256(specs_str.encode("utf-8")).hexdigest()[:8]

    def _setup_run_directory(self) -> None:
        """Generate a unique run ID and create the run directory."""
        self.run_id = self.get_hash_from_specs()
        if self.gen_files_dir is not None:
            self.run_dir: Path | None = self.gen_files_dir / f"run_{self.run_id}"
            self.run_dir.mkdir(exist_ok=True, parents=True)
        else:
            self.run_dir = None

        logging.info(f"Created unique run directory: {self.run_dir}")

    def _initialize_workflow(self) -> None:
        """Initialize the workflow based on the specifications.

        Notes
        -----
        - The workflow type is specified in `runspec['workflow']` in the specifications.
        - Retrieves the workflow class using `get_workflow_class()`.

        Raises
        ------
        ValueError
            If the workflow type is not supported.

        """
        from tango.units.registry import UNIT_OPTIONS

        workflow_class = WORKFLOW_MAP[self.specs["runspec"]["workflow"].lower()]
        self.workflow: Workflow = workflow_class(
            self.specs,
            self.input_file,
            self.run_dir,
            UNIT_OPTIONS,
            self.user_id,
            self.run_id,
        )

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

        self.workflow.execute()

        logging.info(
            f"Simulation finished normally. Elapsed time: {time.time() - self._start_time:.2f} seconds.",
        )

    def execute_batch_simulation(self) -> None:
        """Executes batch simulation if configured."""
        if "batch_simulation" in self.specs and self.specs["batch_simulation"].get("enabled", False):
            batch_sim = BatchSimulation(self.specs, self.specs["batch_simulation"])
            batch_sim.run_batch_simulation(self.input_file)
        else:
            self.execute()

    def update_parameters(self, parameters: dict[str, Any] | None = None) -> None:
        """Update specifications with new parameters and regenerate run ID.

        Args:
            parameters (dict, optional): Dictionary of parameter paths and values to update.
                                       Format: {"section.parameter": value}.
                                       If None, only regenerates run ID (assumes specs updated directly).

        """
        if parameters:
            for param_path, value in parameters.items():
                path_list = param_path.split(".")
                set_nested_value(self.specs, path_list, value)

        # Regenerate run ID and directory for the modified run
        self._setup_run_directory()


class Runner:
    """Wrapper class for `Tango` and `Optimizer`"""

    def __init__(
        self,
        input_file: str | Path,
        save_dir: Path | str | None = None,
        no_save: bool = False,
        parameter_overrides: list | None = None,
        user_id: str | None = None,
        log_level: str = "INFO",
    ):
        """Initialize the Runner.

        Args:
            input_file: Path to the input YAML file.
            save_dir: Directory to save output files. Defaults to current directory.
            no_save: If True, suppress all file saving.
            parameter_overrides: List of parameter override strings.
            user_id: User ID for database operations.
            log_level: Logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL, NONE).

        """
        # Set up logging first
        set_logger(log_level, input_file)

        if no_save:
            # if `no_save` is True, set `save_dir = None`, and this will make it so
            # that no files are saved
            save_dir = None
        else:
            # otherwise, make `save_dir` the current working directory
            save_dir = Path(save_dir) if save_dir is not None else Path().cwd()

        self.tango = Tango(
            Path(input_file),
            save_dir,
            parameter_overrides=parameter_overrides,
            user_id=user_id,
        )
        self._setup_optimizer()

    def _setup_optimizer(self) -> None:
        """Initialize the optimizer if configured in specs."""
        self._optimizer = None
        if "optimization" in self.tango.specs:
            self._optimizer = Optimizer(self.tango, self.tango.specs)

    def start(self) -> None:
        """Start the execution of the workflow. If 'optimization' is present in the specs,
        use the optimizer. Otherwise, check for batch simulation or use regular Tango execution.
        """
        # NOTE: we should probably make sure that if `self._optimizer is not None` and
        # ```
        # "batch_simulation" in self.tango.specs and self.tango.specs["batch_simulation"].get(
        #     "enabled", False
        # )
        # ```
        # that an error is thrown because that combination does not make sense
        # because it's not possible to do both
        if self._optimizer is not None:
            logging.info("Optimization detected. Executing optimizer...")
            self._optimizer.execute()
        elif "batch_simulation" in self.tango.specs and self.tango.specs["batch_simulation"].get(
            "enabled",
            False,
        ):
            logging.info("Batch simulation detected. Executing batch simulation...")
            self.tango.execute_batch_simulation()
        else:
            logging.info("No optimization or batch simulation detected. Executing Tango workflow...")
            self.tango.execute()

    def clone(self) -> "Runner":
        """Create a deep copy of the Runner instance.

        Returns:
            Runner: A new Runner instance with identical state.

        """
        return copy.deepcopy(self)

    def update_parameters(self, parameters: dict[str, Any] | None = None) -> None:
        """Update parameters in the underlying Tango instance.

        Args:
            parameters (dict, optional): Dictionary of parameter paths and values to update.
                                       Format: {"section.parameter": value}.
                                       If None, assumes specs were updated directly.

        """
        self.tango.update_parameters(parameters)
        self._setup_optimizer()
