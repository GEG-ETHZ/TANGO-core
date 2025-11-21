import copy
import itertools
import logging
import os
import shutil
import time
import uuid
from typing import Any
from dataclasses import dataclass, field

import numpy as np
from tqdm import tqdm

from tango.utils import load_from_yaml_with_overrides
from tango.core.errors import PressureError, TangoError, CoolPropError
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
        except PressureError as cpe:
            self.handle_convergence_err(cpe)

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

    def handle_convergence_err(self, cpe: CoolPropError):
        """Handle convergence error to provide troubleshooting context"""
        unit = self.workflow.orchestrator.unit
        # dictionary of module names and corresponding instances
        res_inst_dict: dict[str, FlowResistance] = {
            k: v for (k, v) in unit.__dict__.items()
                if isinstance(v, FlowResistance)
        }

        # dictionary of module names and corresponding resistances 
        res_dict: dict[str, float] = {}

        @dataclass
        class InletBCs(object):
            """Class for storing pressure and temperature"""
            p: float = field(init=False)
            te: float

        opt_inlet_bcs: dict[str, InletBCs] = {}

        # NOTE: these values will be approximate because they're not using numerical simulations, but
        # they'll be guaranteed to work even if the simulation has failed before completing the loop
        # Also, they'll work reasonably well for liquids with minimal property dependence on pressure and
        # may not work as well for gases, dependening on the quality of the assumptions
        for k, v in res_inst_dict.items():
            te: float | None = None
            p: float | None = None
            match k:
                case "injection_well":
                    te = v.fluid_state_init.T
                    # averaged over inlet and outlet
                    p = 0.5 * (
                        v.fluid_state_init.P
                            + unit.reservoir.specs.hydro_static_pressure
                    )

                ### for all other cases, the temperature and pressure must be approximated because the
                # state may not yet be available

                case "reservoir":
                    depth_for_temp = res_inst_dict['reservoir'].specs.reservoir_depth
                    te = (
                        res_inst_dict['reservoir'].specs.surface_temperature
                            + (res_inst_dict['reservoir'].specs.thermal_gradient * depth_for_temp)
                    )
                    # NOTE: This assumes no pressure drop in the injection well, which will
                    # overestimate the pressure. This assumption is reasonable for fluids with
                    # viscosity and density that are pressure insensitive.
                    p = unit.reservoir.specs.hydro_static_pressure
                case "production_well":
                    # NOTE: assumes that production well bottom is always at same depth as injection
                    # well bottom
                    depth_for_temp = res_inst_dict['injection_well']._well_length
                    # NOTE: this assumes fluid temperature is equilibrated with reservoir and that
                    # reservoir temperature has not decreased over time
                    te = (
                        res_inst_dict['production_well']._specs.surface_temperature
                            + (res_inst_dict['production_well']._specs.thermal_gradient * depth_for_temp)
                    )
                    # NOTE: This assumes no pressure drop in the injection well or reservoir, which
                    # will overestimate the pressure. This assumption is reasonable for hydrothermal
                    # systems but needs reassessment for CPG systems.
                    # averaged over inlet (reservoir depth) and outlet (production_well_pump length)
                    p = 0.5 * (
                        unit.reservoir.specs.hydro_static_pressure
                            + res_inst_dict['production_well_pump']._well_length
                    )
                case "production_well_pump":
                    # NOTE: this assumes no temperature decrease has occurred from the reservoir
                    # temperature, which will overestimate the actual temperature, and it's a good
                    # idea to revisit the assumption in the future
                    depth_for_temp = res_inst_dict['injection_well']._well_length
                    te = (
                        res_inst_dict['production_well_pump']._specs.surface_temperature
                            + (res_inst_dict['production_well_pump']._specs.thermal_gradient
                                * depth_for_temp)
                    )
                    # averaged over inlet (production_well_pump length) and outlet (surface)
                    p = 0.5 * (
                        unit.reservoir.specs.hydro_static_pressure
                    )
                case "surface":
                    # NOTE: this assumes no temperature decrease has occurred from the reservoir
                    # temperature, which will overestimate the actual temperature, and it's a good
                    # idea to revisit the assumption in the future
                    depth = res_inst_dict['production_well_pump']._well_length
                    te = (
                        res_inst_dict['production_well_pump']._specs.surface_temperature
                            + (res_inst_dict['production_well_pump']._specs.thermal_gradient * depth)
                    )
                    p = unit.reservoir.specs.hydro_static_pressure

            if te is None:
                raise ValueError("`te` should be a float")
            if p is None:
                raise ValueError("`p` should be a float")

            opt_inlet_bcs[k] = InletBCs(te=te)

            # TODO: check if `self.specs['schedule']['mass_flow_rate']` will work for a case where
            # `self.specs['schedule']['mass_rate']['type']` is not "manual"
            flow_res = v.flow_res(
                te=te,
                p=p,
                mdot=self.specs['schedule']['mass_flow_rate'],
            )
            res_dict[k] = flow_res

        # TODO:
        # - change `flow_res` function to `get_p_out_simple`
        # - what's a typical injection well head pressure? injection well bottom pressure? same but temperatures?
        # - how is initial guess of injection well pressure specified?
        #
        # # Logic:
        # If pressure drops below either zero or saturation pressure in the injection well, then:
        # - the injection well has too high resistance
        # - the mass flow rate is too high for the injection well
        # - the injection well head pressure is too low -- this gets solved by iteration, but only if the
        #   first iteration doesn't trigger an error.  I think we should have the solver automatically
        #   handle this, but this is beyond the scope of task 1.
        #
        # If pressure drops below either zero or saturation pressure in the reservoir, then:
        # - assuming optimistically high inlet pressure (i.e. hydrostatic pressure + allowed over
        #   pressure):
        #     - the mass flow rate and/or impedance (i.e. well spacing) is too high in the reservoir, and
        #       reducing these results in less heat extraction or shorter reservoir life, respectively
        # - otherwise:
        #     - the mass flow rate and/or impedance (i.e. well spacing) is too high for the reservoir
        #       and the mass flow rate and/or flow resistance is too high in the injection well.
        #         - what inlet pressure would the reservoir need to work?
        #         - what injection well diameter would result in this pressure, subject to parameter
        #           limits?
        #     - the injection well head pressure is too low
        #
        # If pressure drops below either zero or saturation pressure in the production well, then:
        # - assuming optimistically high inlet pressure (i.e. hydrostatic pressure + allowed over
        #   pressure):
        #     - the mass flow rate and/or impedance (i.e. well spacing) is too high in the reservoir, and
        #       reducing these results in less heat extraction or shorter reservoir life, respectively
        # - otherwise:
        #     - the mass flow rate and/or impedance (i.e. well spacing) is too high for the reservoir
        #       and the mass flow rate and/or flow resistance is too high in the injection well and/or
        #       the production well.
        #         - what inlet pressure would the production well need to work?
        #         - what production well diameter would result in this pressure, subject to parameter
        #           limits? If it exceeds the limit, can injection wellbore diameter be increased?
        #     - the injection well head pressure is too low
        #
        # If pressure drops below either zero or saturation pressure in the production well pump, then:
        # - what change in production well diameter would fix this?

        # Optimistic pressures
        # pressure at injection well outlet
        p_out_injection_well = unit.injection_well.fluid_state_init.P
        opt_inlet_bcs["reservoir"].p = p_out_injection_well
        # pressure at reservoir outlet
        # assume optimistic pressure
        try:
            p_out_from_spec = unit.reservoir.specs.hydro_static_pressure * (
                1.0 + unit.reservoir.specs.over_pressure_percentage
            )
            p_out_res = max(
                unit.reservoir.inlet_fluid.P,
                p_out_from_spec,
            )
        except Exception:  # doesn't really matter what goes wrong above
            p_out_res = p_out_from_spec
        opt_inlet_bcs["production_well"].p = p_out_res
        # pressure at production well outlet
        try:
            p_out_pro_well = max(
                unit.production_well.inlet_fluid.P,
                unit.reservoir.specs.hydro_static_pressure,
            )
        except Exception:
            p_out_pro_well = unit.reservoir.specs.hydro_static_pressure
        opt_inlet_bcs["production_well_pump"].p = p_out_pro_well
        # pressure at production well pump outlet
        p_out_pro_well_pump = unit.production_well_pump.specs["target_extraction_pressure"]
        opt_inlet_bcs["surface"].p = p_out_pro_well_pump

        ordered_modules = [
            # "injection_well",
            "reservoir",
            "production_well",
            "production_well_pump",
            "surface"
        ]

        # list of errors that will be handled
        errs: list[TangoError] = []

        for (i, mod) in enumerate(ordered_modules):
            # which modules, if any, individually trigger pressure problems?
            p_mod_out = res_dict[mod]
            
        
        raise NotImplementedError("raise the right error here") from cpe


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
