import copy
import itertools
import logging
import os
import shutil
import time
import uuid
from typing import Any
from dataclasses import dataclass, field
import CoolProp as CP

import numpy as np
from tqdm import tqdm

from tango.utils import load_from_yaml_with_overrides
from tango.core.errors import (
    PressureError,
    TangoError,
    CoolPropError,
    SaturationPressureError,
    MassFlowRateError,
    FlowResistanceError,
    ProPumpInletFlashError,
    P_SAT_ERR_TEST,
)
from tango.core.abstracts.workflow import Workflow
from tango.core.abstracts.unit import SimplePressureDrop
from tango.workflows.cmg_workflow import CMGWorkflow
from tango.units.native.well import WellUnitNative
from tango.workflows.native_workflow import NativeWorkflow
from tango.core.fluidstate import FluidState
from tango.optimizerr import Optimizer
from tango.core.constants import GRAVITY_ACCELERATION

WORKFLOW_OPTIONS: dict[str, type[Workflow]] = {
    "native": NativeWorkflow,
    "cmg": CMGWorkflow,
}


# define strings for frequently used dict keys to reduce likelihood of typos
injection_well = "injection_well"
reservoir = "reservoir"
production_well = "production_well"
production_well_pump = "production_well_pump"
production_well_upper = "production_well_upper"
surface = "surface"
ordered_subsurface = [
    injection_well,
    reservoir,
    production_well,
]
ordered_surface = [
    production_well_pump,
    production_well_upper,
    surface,
]


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


@dataclass
class InletBCs:
    """Class for storing pressure and temperature used as inlet BCs

    # Attributes
    # - `p`: pressure at inlet for current module
    # - `te`: temperature at inlet for current module
    """

    p: float
    te: float


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
            if not isinstance(cpe, SaturationPressureError) and P_SAT_ERR_TEST.search(str(cpe)) is not None:
                cpe = SaturationPressureError(cpe)
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
        # dictionary of module names and corresponding instances that inhherit `SimplePressureDrop`
        p_simple_inst_dict: dict[str, SimplePressureDrop] = {
            k: v for (k, v) in unit.__dict__.items()
                if isinstance(v, SimplePressureDrop)
        }

        breakpoint()

        # NOTE: check if `self.specs['schedule']['mass_flow_rate']` will work for a case where
        # `self.specs['schedule']['mass_rate']['type']` is not "manual"
        mdot = self.specs['schedule']['mass_flow_rate']

        # module key and corresponding saturation pressure, given assumed boundary conditions
        p_sat_assumed: dict[str, float] = {}

        # module key and corresponding difference between optimum outlet pressure and error state (i.e.
        # pressure below saturation pressure or zero, whichever is greater)
        p_out_opt_margin: dict[str, float] = {}

        # fractional margin above saturation pressure at which error is triggered
        # NOTE: this should eventually be configurable
        p_sat_frac_margin = 1.0

        # module keys and corresponding errors that will be handled
        standalone_mod_errs: dict[str, TangoError] = {}

        # state for ad hoc calculations
        state_ad_hoc = FluidState.copy(p_simple_inst_dict[injection_well].fluid_state_init)
        if not state_ad_hoc.rho > 0.0:
            # should not be reachable
            raise ValueError("`state_ad_hoc` should have been updated.  Report this error to TANGO team.")

        dp_dict, opt_inlet_bcs, act_inlet_bcs = get_dp_and_opt_bcs(
            unit,
            p_simple_inst_dict,
            mdot,
            state_ad_hoc,
        )

        for (k, v) in opt_inlet_bcs.items():
            state_ad_hoc.updatePT(v.p, v.te)
            p_sat_for_k = CP.CoolProp.PropsSI("P", "T", v.te, "Q", 0, state_ad_hoc.fluidname)
            p_sat_assumed[k] = p_sat_for_k
            # calculate outlet pressure based on optimistically high inlet pressure
            p_out_for_k = opt_inlet_bcs[k].p - dp_dict[k]
            # negative means that `k` module is a bottleneck
            p_out_delta_above_err_for_k = p_out_for_k - p_sat_for_k
            p_out_opt_margin[k] = p_out_delta_above_err_for_k
            if p_out_delta_above_err_for_k <= (p_sat_frac_margin * p_sat_for_k):
                standalone_mod_errs[k] = SaturationPressureError(
                    f"For flow rate {mdot} kg/s, module {k} as a standalone component will trigger saturation"
                    + "pressure errors, assuming optimistic inlet BCs",
                )

        # module names and corresponding pipe diameters
        diameters: dict[str, float] = {}
        for (k, v) in p_simple_inst_dict.items():
            if k == injection_well:
                diameters[k] = unit.__dict__[k]._specs.__dict__["diameter"]
            elif k == reservoir:
                continue
            elif k in (production_well, production_well_pump):
                diameters[k] = unit.__dict__[k]._specs.__dict__["diameter"]
            elif k == surface:
                # TODO resolve the discrepancy between `_specs` and `specs` in surface and wellbores
                diameters[k] = unit.__dict__[k].specs.__dict__["pipe_diameter"]
            else:
                # should be unreachable
                raise ValueError(f"Unexpected key: {k}. Report this to the TANGO team")

        if len(standalone_mod_errs) == 1:
            k = next(iter(standalone_mod_errs.keys()))

            # Need to reduce dp by -p_out_delta_above_err[k] + margin
            # For fully developed turbulence (i.e. flat part of the Moody chart) dp scales with D^-5, so...
            d_res_needed = -p_out_opt_margin[k] / dp_dict[k]
            # TODO: check this against the the max allowed diameter
            d_new = diameters[k] * (1.0 - d_res_needed) ** (-0.2)
            assert d_new > diameters[k]
            d_max = max(diameters.values())
            mods_with_d_max: list[str] = [k for (k, v) in diameters.items() if v == d_max]
            raise FlowResistanceError(
                f"\n\tModule {k} has excessive standalone flow resistance."
                    + f"\n\tcurrent diameter: {diameters[k]:.3f} m"
                    + f"\n\tModules with max diameter ({d_max:.3f} m): {mods_with_d_max}"
                        if d_max > d_new else ""
                    + f"\n\t(Try changing diameter to match: {d_max:.3f} m)" if d_max > d_new else ""
                    + f"\n\t(Try changing diameter to: {d_new:.3f} m)" if d_new > d_max else "",
            ) from cpe

        check_complex_err(
            unit,
            p_simple_inst_dict,
            diameters,
            mdot,
            state_ad_hoc,
            cpe,
            p_sat_frac_margin,
        )


def get_dp_and_opt_bcs(
    unit,
    p_simple_inst_dict: dict[str, SimplePressureDrop],
    mdot: float,
    state_ad_hoc: FluidState
) -> tuple[dict[str, float], dict[str, InletBCs], dict[str, InletBCs | None]]:
    """Get module-wise estimated pressure drop for a given mass flow rate

    # Returns
    # - estimated pressure drop for each module
    # - optimal inlet BCs for each module to check for individual model excess flow resistance
    # - minimal inlet BCs for each module to avoid saturation
    """
    # dictionary of module names and corresponding pressure drops [Pa]
    dp_dict: dict[str, float] = {}

    # dictionary of module names and corresponding optimal BCs to use in calculating outlet pressure
    opt_inlet_bcs: dict[str, InletBCs] = {}
    # dictionary of module names and corresponding BCs from whatever portion of TANGO successfully
    # simulated
    act_inlet_bcs: dict[str, InletBCs | None] = {}

    # NOTE: these values will be approximate because they're not using numerical simulations, but
    # they'll be guaranteed to work even if the simulation has failed before completing the loop
    # Also, they'll work reasonably well for liquids with minimal property dependence on pressure and
    # may not work as well for gases
    #
    # Determine temperatue and pressure to be used in calculating properties for calculating dP for each
    # module in TANGO loop
    for k, v in p_simple_inst_dict.items():
        if k == injection_well:
            te = v.fluid_state_init.T
            # averaged over inlet and outlet for property calculations
            p = 0.5 * (
                v.fluid_state_init.P
                    + unit.reservoir.specs.hydro_static_pressure
            )
            dp_for_module = v.get_dp_simple(
                te=te,
                p=p,
                mdot=mdot,
            )
            dp_dict[k] = dp_for_module
            opt_inlet_bcs[k] = InletBCs(
                te=te,
                # this gets updated after an iteration, but if it fails before one iteration is
                # complete, then there's not a clear best choice for assuming an optimum inlet
                # pressure here
                p=v.fluid_state_init.P
            )
            del te, p
            try:
                act_inlet_bcs[k] = InletBCs(
                    te=v.inlet_fluid.T,
                    # this gets updated after an iteration, but if it fails before one iteration is
                    # complete, then there's not a clear best choice for assuming an optimum inlet
                    # pressure here
                    p=v.inlet_fluid.P
                )
            except Exception as err:
                act_inlet_bcs[k] = None

        ### for all other cases, the temperature and pressure must be approximated because the
        # state may not yet be available

        elif k == reservoir:
            depth_for_temp = p_simple_inst_dict[k].specs.reservoir_depth
            # this overestimates temperature for pressure drop calculation but is
            # reasonable for saturation pressure calclulation
            te = (
                p_simple_inst_dict[surface].specs.surface_temperature
                    + (p_simple_inst_dict[k].specs.thermal_gradient * depth_for_temp)
            )
            # NOTE: This assumes minimal pressure drop in the injection well.
            # This assumption is reasonable for calculating fluid properties
            # of fluids with viscosity and density that are pressure insensitive.
            p = unit.reservoir.specs.hydro_static_pressure
            dp_for_module = v.get_dp_simple(
                te=te,
                p=p,
                mdot=mdot,
            )
            dp_dict[k] = dp_for_module
            opt_inlet_bcs[k] = InletBCs(
                te=te,
                # this assumes the injection well head pressure and resistances are high enough and
                # low enough, respectively, to feed the reservoir its maximum allowed inlet pressure
                p=unit.reservoir.specs.hydro_static_pressure * (
                    1.0 + unit.reservoir.specs.over_pressure_percentage
                )
            )
            del te, p
            try:
                act_inlet_bcs[k] = InletBCs(
                    te=v.inlet_fluid.T,
                    # this gets updated after an iteration, but if it fails before one iteration is
                    # complete, then there's not a clear best choice for assuming an optimum inlet
                    # pressure here
                    p=v.inlet_fluid.P
                )
            except Exception as err:
                act_inlet_bcs[k] = None
        elif k == production_well:
            # NOTE: assumes that production well bottom is always at same depth as injection
            # well bottom
            depth_for_temp = p_simple_inst_dict['injection_well']._well_length
            # NOTE: this assumes fluid temperature is equilibrated with reservoir and that
            # reservoir temperature has not decreased over time
            te = (
                p_simple_inst_dict[surface].specs.surface_temperature
                    + (p_simple_inst_dict['production_well']._specs.thermal_gradient * depth_for_temp)
            )
            # NOTE: This assumes no pressure drop in the injection well or reservoir, which
            # will overestimate the pressure. This assumption is reasonable for hydrothermal
            # systems but needs reassessment for CPG systems.
            # averaged over inlet (reservoir depth) and outlet (production_well_pump length) for property
            # calculation
            p = 0.5 * (
                unit.reservoir.specs.hydro_static_pressure
                    + p_simple_inst_dict['production_well_pump']._well_length * GRAVITY_ACCELERATION
                        * state_ad_hoc.rho
            )
            dp_for_module = v.get_dp_simple(
                te=te,
                p=p,
                mdot=mdot,
            )
            dp_dict[k] = dp_for_module
            opt_inlet_bcs[k] = InletBCs(
                te=te,
                # this assumes the injection well head pressure and resistances are high enough and
                # low enough, respectively, to feed the reservoir its maximum allowed inlet pressure
                p=unit.reservoir.specs.hydro_static_pressure * (
                    1.0 + unit.reservoir.specs.over_pressure_percentage
                )
            )
            del te, p
            try:
                act_inlet_bcs[k] = InletBCs(
                    te=v.inlet_fluid.T,
                    # this gets updated after an iteration, but if it fails before one iteration is
                    # complete, then there's not a clear best choice for assuming an optimum inlet
                    # pressure here
                    p=v.inlet_fluid.P
                )
            except Exception as err:
                act_inlet_bcs[k] = None
        elif k == production_well_pump:
            # NOTE: this assumes no temperature decrease has occurred from the reservoir
            # temperature, which will overestimate the actual temperature, and it's a good
            # idea to revisit the assumption in the future
            # This also assumes that injection well length and reservoir length are the same, which is
            # usually the case but may need future revision
            depth_for_temp = p_simple_inst_dict['injection_well']._well_length
            te = (
                p_simple_inst_dict[surface].specs.surface_temperature
                    + (p_simple_inst_dict['production_well_pump']._specs.thermal_gradient * depth_for_temp)
            )
            # averaged over inlet (production_well_pump length) and outlet (surface)
            p = 0.5 * (
                unit.reservoir.specs.hydro_static_pressure
            )
            dp_for_module = v.get_dp_simple(
                te=te,
                p=p,
                mdot=mdot,
            )
            dp_dict[k] = dp_for_module
            opt_inlet_bcs[k] = InletBCs(
                p=unit.reservoir.specs.hydro_static_pressure - (
                    unit.production_well.specs['well_length']
                        - unit.production_well_pump.specs['well_length']
                ) * GRAVITY_ACCELERATION * state_ad_hoc.rho,
                te=te,
            )
            del te, p
            try:
                act_inlet_bcs[k] = InletBCs(
                    te=v.inlet_fluid.T,
                    # this gets updated after an iteration, but if it fails before one iteration is
                    # complete, then there's not a clear best choice for assuming an optimum inlet
                    # pressure here
                    p=v.inlet_fluid.P
                )
            except Exception as err:
                act_inlet_bcs[k] = None
        elif k == surface:
            # NOTE: this assumes no temperature decrease has occurred from the reservoir
            # temperature, which will overestimate the actual temperature, and it's a good
            # idea to revisit the assumption in the future
            depth = p_simple_inst_dict[production_well_pump]._well_length
            te = (
                p_simple_inst_dict[surface].specs.surface_temperature
                    + (p_simple_inst_dict[reservoir].specs.thermal_gradient * depth)
            )
            p = unit.reservoir.specs.hydro_static_pressure
            p_out_pro_well_pump = unit.production_well_pump.specs["target_extraction_pressure"]
            dp_for_module = v.get_dp_simple(
                te=te,
                p=p,
                mdot=mdot,
            )
            dp_dict[k] = dp_for_module
            opt_inlet_bcs[surface] = InletBCs(p=p_out_pro_well_pump, te=te)
            del te, p
            try:
                act_inlet_bcs[k] = InletBCs(
                    te=v.inlet_fluid.T,
                    # this gets updated after an iteration, but if it fails before one iteration is
                    # complete, then there's not a clear best choice for assuming an optimum inlet
                    # pressure here
                    p=v.inlet_fluid.P
                )
            except Exception as err:
                act_inlet_bcs[k] = None
        else:
            # should be unreachable
            raise ValueError(f"Invalid k: {k}.  Report this to the TANGO team.")

    return dp_dict, opt_inlet_bcs, act_inlet_bcs


def check_complex_err(
    unit,
    p_simple_inst_dict: dict[str, SimplePressureDrop],
    diameters: dict[str, float],
    mdot: float,
    state_ad_hoc: FluidState,
    cpe: CoolPropError,
    p_sat_frac_margin: float,
):
    """Check for errors that involve more than one component -- e.g. production well pump inlet flashing
    because of flow restriction in injection well

    # Arguments
    # - `opt_inlet_bcs`: optimal inlet BCs -- only temperature is used to calculate conservative estimate of
    #   saturation pressure
    # - `mdot`: mass flow rate [kg/s]

    """
    breakpoint()
    # determine component in which CoolProp error occurred
    if f"unit: {injection_well}" in str(cpe):
        cp_err_inlet = injection_well
    elif f"unit: {production_well}" in str(cpe):
        cp_err_inlet = production_well
    elif f"unit: {reservoir}" in str(cpe):
        cp_err_inlet = reservoir
    elif isinstance(cpe, ProPumpInletFlashError):
        cp_err_inlet = production_well
    elif f"unit: {production_well_pump}" in str(cpe):
        cp_err_inlet = production_well_pump
    elif f"unit: {surface}" in str(cpe):
        cp_err_inlet = surface
    else:
        raise Exception("Unable to determine location of failure from previous errors")

    if cp_err_inlet in ordered_subsurface:
        idx_cp_err = ordered_subsurface.index(cp_err_inlet)
        # subset of ordered_subsurface to check
        ord_sub_subset = ordered_subsurface[:idx_cp_err + 1]
        diam_subset = {k: v for k, v in diameters.items() if k in ord_sub_subset}
    elif cp_err_inlet in ordered_surface:
        idx_cp_err = ordered_surface.index(cp_err_inlet)
        # subset of ordered_surface to check
        ord_surf_subset = ordered_surface[:idx_cp_err + 1]
        diam_subset = {k: v for k, v in diameters.items() if k in ord_surf_subset}
    else:
        raise cpe

    d_max_in_sys = max(diameters.values())
    comps_with_less_than_d_max = {k: v for (k, v) in diam_subset.items() if v < d_max_in_sys}

    dp_dict, opt_inlet_bcs, act_inlet_bcs = get_dp_and_opt_bcs(
        unit,
        p_simple_inst_dict,
        mdot,
        state_ad_hoc,
    )

    if len(comps_with_less_than_d_max) == 1:
        comp_with_narrow_d = next(iter(comps_with_less_than_d_max.keys()))
        narrow_d = next(iter(comps_with_less_than_d_max.values()))
        # adjusting one component might solve the problem
        # inlet pressure for current component that will not cause saturation
        p_min_inlet: dict[str, float] = {}

        p_min_to_avoid_sat = CP.CoolProp.PropsSI(
            "P", "T", opt_inlet_bcs[production_well_pump].te, "Q", 0, state_ad_hoc.fluidname
        ) * (1.0 + p_sat_frac_margin)
        first_iter = False
        if cp_err_inlet in ordered_subsurface:
            # minimum pressure at production well outlet (pump inlet) to avoid saturation
            for i in range(len(ord_sub_subset)):
                # iterate backward from the component that failed toward the previous specified BC
                # estimated saturation pressure entering production well pump
                # index for reversing direction
                irev = len(ord_sub_subset) - 1 - i
                key_curr = ord_sub_subset[irev]
                if first_iter:
                    # after the first iteraton
                    key_prev = ord_sub_subset[irev + 1]
                else:
                    key_prev = None
                first_iter = True

                if key_prev is None:
                    p_min_inlet[key_curr] = p_min_to_avoid_sat + dp_dict[key_curr]
                else:
                    p_min_inlet[key_curr] = p_min_inlet[key_prev] + dp_dict[key_curr]
        elif cp_err_inlet in ordered_surface:
            # TODO: check this branch
            # minimum pressure at production well outlet (pump inlet) to avoid saturation
            for i in range(len(ord_surf_subset)):
                # iterate backward from the component that failed toward the previous specified BC
                # estimated saturation pressure entering production well pump
                # index for reversing direction
                irev = len(ord_surf_subset) - 1 - i
                key_curr = ord_surf_subset[irev]
                if first_iter:
                    # after the first iteraton
                    key_prev = ord_surf_subset[irev + 1]
                else:
                    key_prev = None
                first_iter = True

                if key_prev is None:
                    p_min_inlet[key_curr] = p_min_to_avoid_sat + dp_dict[key_curr]
                else:
                    p_min_inlet[key_curr] = p_min_inlet[key_prev] + dp_dict[key_curr]
        else:
            raise Exception("Should be unreachable. Notify TANGO team")

        # reduction in pressure needed to avoid saturation downstream
        if isinstance(unit.__dict__[comp_with_narrow_d], WellUnitNative):
            if comp_with_narrow_d == production_well:
                depth = (
                    unit.__dict__[production_well_pump]._well_length
                        + unit.__dict__[comp_with_narrow_d]._well_length
                )
            else:
                depth = unit.__dict__[comp_with_narrow_d]._well_length
            dp_needed = (
                p_min_inlet[comp_with_narrow_d] - unit.__dict__[comp_with_narrow_d].inlet_fluid.P
            ) / (dp_dict[comp_with_narrow_d] + GRAVITY_ACCELERATION * depth * state_ad_hoc.rho)
        else:
            dp_needed = (
                p_min_inlet[comp_with_narrow_d] - unit.__dict__[comp_with_narrow_d].inlet_fluid.P
            ) / dp_dict[comp_with_narrow_d]
        d_curr = narrow_d
        d_margin = 0.3
        d_new = d_curr * (1.0 - dp_needed) ** (-0.2) * (1.0 + d_margin)
        raise FlowResistanceError(
            f"\n\t`{comp_with_narrow_d}` has too much flow resistance."
            + f"\n\tThis could by fixed, for example, by increasing the diameter (currently {d_curr:.3f} m)"
            + f" to at least {d_new:.3f} m"
            + f"\n\tor matching the diameter used elsewhere in the system: {d_max_in_sys:.3f} m"
        ) from cpe

        # TODO: see what happens if pump depth is modulated and make sure it gets handled appropriately

    else:
        figure_out_mass_flow_that_works




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
        # NOTE: we should probably make sure that if `self._optimizer is not None` and
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
