from datetime import datetime
from dateutil.relativedelta import relativedelta
from tqdm import tqdm
import numpy as np
import sys
import logging
import importlib
import os
import csv
from copy import deepcopy

from .arangodb_manager import ArangoDBManager
from tango.core.abstracts.workflow import Workflow
from tango.core.constants import *
from tango.core.config import *
from tango import utils
from tango.orchestrators.native import *
from tango.orchestrators.external import *
from tabulate import tabulate
from termcolor import colored
from itertools import cycle
from tango.function_evaluator import FunctionEvaluator
from tango.parameter_mappings import TARGET_PARAMETER_MAPPING, VARIABLE_PARAMETER_MAPPING
from tango.units.dataclasses import *

def get_system_class(type_: str) -> object:
    """
    Retrieves the system class corresponding to the given type.

    Args:
        type_ (str): The type of system.

    Returns:
        object: The system class.

    Raises:
        ValueError: If the system type is unsupported.

    Example:
        >>> get_system_class("surface_unit")
    """
    try:
        return eval(SYSTEM_OPTIONS[type_.lower()])
    except:
        raise ValueError(f"System type: {type_} is not supported.")


class NativeWorkflow(Workflow):
    """
    Implements the native workflow for TANGO based on genGEO.

    This class handles the initialization, execution, and results processing
    for the TANGO simulation framework.

    Attributes:
        _input_file (str): Path to the input file.
        _start_date (datetime): Start date of the simulation.
        _results (dict): Stores simulation results.
        _fluid_states (dict): Stores fluid states for diagram plotting.
        orchestrator (object): Manages system computations and updates.
        economic (object): Handles economic computations, if applicable.
        diagram_specs (DiagramSpecs): Diagram specifications for plotting.
    """

    def __init__(self, specs: dict, input_file: str, user_id: str = None, run_id: str = None, run_dir: str = None):
        """
        Initializes the NativeWorkflow object.

        Args:
            specs (dict): Specifications for the simulation.
            input_file (str): Path to the input file.
            user_id (str, optional): User ID for database operations.
            run_id (str, optional): Unique run ID for file naming.
            run_dir (str, optional): Directory for run-specific output files.

        Steps:
            - Initializes the physical and economic systems.
            - Sets up diagram specifications for plotting results.
        """
        super().__init__(specs)
        self._input_file = input_file
        self._user_id = user_id
        self._run_id = run_id or "default"
        self._run_dir = run_dir or os.getcwd()
        self._start_date = datetime.strptime(self.specs['schedule']['start_date'], DATETIME_FMT)
        self.dt_list = None
        self._init_system()
        self._init_econ_unit()
        self._results = dict()
        self.addons_manager()

        self.function_evaluator = FunctionEvaluator(
            target_mapping=TARGET_PARAMETER_MAPPING,
            variable_mapping=VARIABLE_PARAMETER_MAPPING,
            orchestrator=self.orchestrator,
            economic=self.economic
        )
        self.function_evaluator.set_context(self)
        
        if (hasattr(self.orchestrator, 'unit') and 
            hasattr(self.orchestrator.unit, 'surface') and 
            self.orchestrator.unit.surface and
            hasattr(self.orchestrator.unit.surface, 'set_context')):
            self.orchestrator.unit.surface.set_context(self)
        
        self.arango_manager = None
        arango_config = self.specs.get('arangodb', {})
        if arango_config.get('enabled', 'no') == 'yes':
            try:
                self.arango_manager = ArangoDBManager(arango_config, self._user_id)
                # Pass the modified specs (with parameter overrides) to store in database
                self._current_user_id, self._current_simulation_id = self.arango_manager.get_current_user_and_simulation(self, self.specs)
                if self._current_user_id and self._current_simulation_id:
                    logging.info(f"ArangoDB: User {self._current_user_id}, Simulation {self._current_simulation_id}")
                else:
                    logging.warning("ArangoDB: Failed to initialize user/simulation")
            except Exception as e:
                logging.error(f"Failed to initialize ArangoDB manager: {e}")
                self.arango_manager = None

    def write_to_arangodb(self, step_index: int, table_type: str = "main_graph", data_type: str = "timestep"):
        """
        Writes data to ArangoDB collections using the ArangoDB manager.
        
        Args:
            step_index (int): The time step index.
            table_type (str): Either "main_graph" or "power_plant" for data categorization.
            data_type (str): Type of data being written ("timestep", "power_plant", "economic").
        """
        if not hasattr(self, 'arango_manager') or not self.arango_manager:
            logging.debug("ArangoDB manager not available, skipping database write")
            return
            
        try:
            logging.debug(f"Routing ArangoDB write: data_type={data_type}, step_index={step_index}")
            
            if data_type == "main_graph":
                self.arango_manager.write_timestep_data(step_index, table_type, "main_graph", self)
            elif data_type == "power_plant":
                self.arango_manager.write_timestep_data(step_index, table_type, "power_plant", self)
            elif data_type == "phase_diagram":
                self.arango_manager.write_timestep_data(step_index, table_type, "phase_diagram", self)
            elif data_type == "economic":
                self.arango_manager.write_economic_data(self)
            elif data_type == "physics":
                logging.info(f"Routing to physics data write")
                self.arango_manager.write_physics_data(self)
            else:
                logging.warning(f"Unknown data_type: {data_type}")
                
        except Exception as e:
            logging.error(f"Failed to write to ArangoDB: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")

    def _generate_power_plant_mappings(self):
        """
        Generates dynamic power plant component attribute mappings for the FunctionEvaluator.
        """
        if (hasattr(self.orchestrator, 'unit') and 
            hasattr(self.orchestrator.unit, 'surface') and 
            self.orchestrator.unit.surface and
            type(self.orchestrator.unit.surface).__name__ == 'SurfaceUnitFlexiblePP'):
            
            surface_unit = self.orchestrator.unit.surface
            
            if hasattr(surface_unit, 'specs'):
                specs = surface_unit.specs
                if hasattr(specs, 'new_config'):
                    config = specs.new_config
                elif hasattr(specs, 'org'):
                    config = specs.org
                else:
                    config = None
            else:
                config = None
                
            if config and 'power_plant_graph' in config and 'nodes' in config['power_plant_graph']:
                if not hasattr(self.function_evaluator, 'variable_mapping'):
                    self.function_evaluator.variable_mapping = {}
                if not self.function_evaluator.variable_mapping:
                    self.function_evaluator.variable_mapping = {}
                    
                nodes = config['power_plant_graph']['nodes']
                
                for component_name, component_data in nodes.items():
                    if isinstance(component_data, dict) and 'type' in component_data:
                        if component_name in config:
                            component_config = config[component_name]
                            
                            for attr_name, attr_value in component_config.items():
                                mapping_key = f"{component_name}_{attr_name}"
                                mapping_value = f"self.orchestrator.unit.surface.specs.new_config[\"{component_name}\"][\"{attr_name}\"]"
                                self.function_evaluator.variable_mapping[mapping_key] = mapping_value
                        else:
                            for attr_name, attr_value in component_data.items():
                                if attr_name != 'type':  
                                    mapping_key = f"{component_name}_{attr_name}"
                                    mapping_value = f"self.orchestrator.unit.surface.specs.new_config[\"power_plant_graph\"][\"nodes\"][\"{component_name}\"][\"{attr_name}\"]"
                                    self.function_evaluator.variable_mapping[mapping_key] = mapping_value                

                tespy_output_mappings = {
                    'P': 'self.orchestrator.unit.surface.power_plant.nodes["{component}"].P.val',  # Power
                    'Q': 'self.orchestrator.unit.surface.power_plant.nodes["{component}"].Q.val',  # Heat load
                    'T': 'self.orchestrator.unit.surface.power_plant.nodes["{component}"].T.val',  # Temperature
                    'p': 'self.orchestrator.unit.surface.power_plant.nodes["{component}"].p.val',  # Pressure
                    'h': 'self.orchestrator.unit.surface.power_plant.nodes["{component}"].h.val',  # Enthalpy
                    'm': 'self.orchestrator.unit.surface.power_plant.nodes["{component}"].m.val',  # Mass flow rate
                    'eta': 'self.orchestrator.unit.surface.power_plant.nodes["{component}"].eta.val',  # Efficiency
                }
                
                for component_name, component_data in nodes.items():
                    if isinstance(component_data, dict) and 'type' in component_data:
                        component_type = component_data['type']
                        
                        if component_type in ['Turbine', 'Compressor']:
                            mapping_key = f"{component_name}_P"
                            mapping_value = tespy_output_mappings['P'].format(component=component_name)
                            self.function_evaluator.variable_mapping[mapping_key] = mapping_value
                            
                        elif component_type in ['SimpleHeatExchanger', 'HeatExchanger']:
                            mapping_key = f"{component_name}_Q"
                            mapping_value = tespy_output_mappings['Q'].format(component=component_name)
                            self.function_evaluator.variable_mapping[mapping_key] = mapping_value
                            
                        for output_attr, mapping_template in tespy_output_mappings.items():
                            if output_attr not in ['P', 'Q']:  
                                mapping_key = f"{component_name}_{output_attr}"
                                mapping_value = mapping_template.format(component=component_name)
                                self.function_evaluator.variable_mapping[mapping_key] = mapping_value

    def _process_specs(self, specs) -> dict:
        """
        Extracts and processes phase diagram specifications.

        Args:
            specs (dict): Specifications for the simulation.

        Returns:
            dict: Processed phase diagram specifications.
        """
        return specs['phase_diagram']

    def _init_system(self) -> None:
        """
        Initializes the physical system, including computational nodes and their connections.

        The system handles the techno-physical computations for the simulation.
        """
        self.sys_name = utils.system_name(self.specs)
        if 'bc_iteration' in self.specs.get('schedule', {}):
            self.sys_name = 'external'
        UnitManager = get_system_class(self.sys_name)
        self.orchestrator = UnitManager(self.specs)

    def _init_econ_unit(self) -> None:
        """
        Initializes the economic unit, if applicable.
        """
        self.economic = None
        if 'economic' in self.specs:
            Unit = get_unit_class(type_='economic', unit_name=self.specs['economic']['type'])
            self.economic = Unit(specs=self.specs, nodes=self.orchestrator.graph.nodes)

    def _native_system_iteration(self) -> None:
        """
        Balances the system and advances by one time step using native computations.
        """
        count = 0
        while not self.orchestrator.max_itr_reached(count):
            count += 1
            self.orchestrator.execute()  # Run compute nodes
            if self.orchestrator.balanced():
                logging.debug(f"System balanced after {count} iterations")
                break
            self.orchestrator.update()
        self.orchestrator.update_time_dependent_vars()

    def _external_system_iteration(self, funcs) -> None:
        """
        Balances the system and advances by one time step for external systems.
        """
        self.orchestrator.execute()
        if (self.sys_name == 'external'):
            self.orchestrator.update(funcs, self.economic._results)
        else:
            self.orchestrator.update()
        self.orchestrator.update_time_dependent_vars()
        self.economic.execute(self._results, self.function_evaluator.evaluated_functions, self.dt_list)

    def _save_results(self, current_date: datetime) -> None:
        """
        Saves simulation results for the current time step.

        Args:
            current_date (datetime): The current date in the simulation.
        """
        if (self.orchestrator.unit.surface.__class__.__name__ == 'SurfaceUnitFlexiblePP'):
            utils.parse_results_flexible(
                d=self._results,
                nodes=self.orchestrator.graph.nodes,
                current_date=current_date.strftime(DATETIME_FMT)
            )
        else:
            utils.parse_results(
                d=self._results,
                nodes=self.orchestrator.graph.nodes,
                current_date=current_date.strftime(DATETIME_FMT)
            )

    def _post_processing(self) -> None:
        """
        Handles post-processing tasks, including saving results and generating plots.
        """
        utils.write_results(
            input_file=self._input_file,
            results=(self._results, self.economic.get_results() if self.economic else None)
        )

    def addons_manager(self) -> None:
        """
        Dynamically discovers addons from the addons directory, initializes them,
        and sets up corresponding specifications.
        Combines `self.specs['graph']` and `self.specs['power_plant_graph']` under a new higher-level key
        before passing it to the addon instance.
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        while not current_dir.endswith("TANGO"):
            current_dir = os.path.dirname(current_dir)
        addons_path = os.path.join(current_dir, "src", "tango", "addons")

        self.addons = {}

        for addon_name in os.listdir(addons_path):
            addon_dir = os.path.join(addons_path, addon_name)

            if os.path.isdir(addon_dir) and not addon_name.startswith('__'):
                try:
                    addon_module = importlib.import_module(f"tango.addons.{addon_name}.{addon_name}_interface")
                    addon_specs_class_name = f"{addon_name}Specs"
                    if hasattr(addon_module, addon_specs_class_name):
                        addon_specs_class = getattr(addon_module, addon_specs_class_name)
                    else:
                        addon_specs_class = getattr(
                            importlib.import_module("tango.units.dataclasses"),
                            addon_specs_class_name
                        )

                    addon_specs_dict = self.specs.get('addons', {}).get(addon_name, {})
                    if not addon_specs_dict:
                        logging.warning(f"Addon '{addon_name}' is not set in the input file and will be skipped.")
                        continue

                    addon_specs = addon_specs_class.from_dict(addon_specs_dict)
                    setattr(self, f"{addon_name}_specs", addon_specs)

                    addon_class_name = f"{addon_name}_addon"
                    if hasattr(addon_module, addon_class_name):
                        addon_class = getattr(addon_module, addon_class_name)
                    else:
                        raise AttributeError(f"'{addon_class_name}' not found in module '{addon_module.__name__}'.")

                    merged_graph = {
                        "main_graph": deepcopy(self.specs['graph']),
                        "power_plant_graph": deepcopy(self.specs.get('power_plant_graph', {}))
                    }

                    self.addons[addon_name] = addon_class(merged_graph, self._results)

                    logging.info(f"Addon '{addon_name}' initialized successfully with merged graph.")

                except Exception as e:
                    logging.error(f"Failed to load addon '{addon_name}': {e}")

    def _write_timestep_files(self, step_index: int) -> None:
        """
        Writes all files for a specific timestep atomically.
        Ensures that if main_graph CSV is written, all other related files are also written and closed.
        Also writes data to ArangoDB if enabled.
        
        Args:
            step_index (int): The time step index for file naming.
        """
        write_csv = getattr(self.orchestrator.unit.surface.specs, 'table_to_csv', 'no') == 'yes'
        output_table_enabled = self.orchestrator.unit.surface.specs.output_table == 'yes'
        power_plant_table_enabled = (
            hasattr(self.orchestrator.unit.surface.specs, 'power_plant_table') and
            self.orchestrator.unit.surface.specs.power_plant_table == 'yes' and 
            self.orchestrator.unit.surface.__class__.__name__ == 'SurfaceUnitFlexiblePP'
        )
        
        thermagraph_svg_enabled = False
        if 'ThermaGraph' in self.addons:
            thermagraph_specs = getattr(self, 'ThermaGraph_specs', None)
            if thermagraph_specs and getattr(thermagraph_specs, 'per_timestep', 'no') == 'yes':
                auto_save_svg_val = self.specs.get('addons', {}).get('ThermaGraph', {}).get('auto_save_svg', getattr(thermagraph_specs, 'auto_save_svg', 'yes'))
                thermagraph_svg_enabled = auto_save_svg_val == 'yes'
        
        files_to_write = []
        if output_table_enabled and write_csv:
            files_to_write.append('main_graph_csv')
        if power_plant_table_enabled and write_csv:
            files_to_write.append('power_plant_csv')
        if thermagraph_svg_enabled:
            files_to_write.append('thermagraph_svg')
        
        arango_data_written = False
        
        if output_table_enabled:
            logging.info(f"Writing main graph data to ArangoDB for timestep {step_index}")
            self.write_to_arangodb(step_index, "main_graph", "main_graph")
            arango_data_written = True
            
        if power_plant_table_enabled:
            logging.info(f"Writing power plant data to ArangoDB for timestep {step_index}")
            self.write_to_arangodb(step_index, "power_plant", "power_plant")
            arango_data_written = True
            

        
        if not files_to_write and not arango_data_written:
            logging.debug(f"No files or ArangoDB data to write for timestep {step_index} (table_to_csv={write_csv}, output_table={output_table_enabled}, power_plant_table={power_plant_table_enabled}, thermagraph_svg={thermagraph_svg_enabled})")
            return
            
        try:
            if output_table_enabled and write_csv:
                self.generate_output_table(step_index=step_index, table_type="main_graph", write_csv=True, print_table=False)
            
            if power_plant_table_enabled and write_csv:
                # Write power plant table only to the unique run directory
                self.generate_power_plant_output_table(step_index=step_index, write_csv=True, print_table=False)
            

            
            if thermagraph_svg_enabled:
                thermagraph_specs = getattr(self, 'ThermaGraph_specs')
                thermagraph_specs.states_file = os.path.join(self._run_dir, f"{self._run_id}_thermagraph_states_{step_index}.json")
                thermagraph_specs.connections_file = os.path.join(self._run_dir, f"{self._run_id}_thermagraph_connections_{step_index}.json")
                fluid_name = (
                    self.specs.get('fluid_name') or
                    self.specs.get('props', {}).get('fluid_name') or
                    self.specs.get('common', {}).get('fluid_name') or
                    'CO2'
                )
                thermagraph_specs.fluid_name = fluid_name
                thermagraph_specs.auto_save_svg = 'yes'
                # Use unique SVG filename in run directory
                thermagraph_specs.svg_filename = os.path.join(self._run_dir, f"{self._run_id}_thermagraph_output_{step_index}.svg")
                self.addons['ThermaGraph'].auto_save_svg = thermagraph_specs.auto_save_svg
                self.addons['ThermaGraph'].svg_filename = thermagraph_specs.svg_filename
                self.addons['ThermaGraph'].post_process(thermagraph_specs)
                self.addons['ThermaGraph'].execute(step_index=step_index)
                
                # Write the generated SVG to ArangoDB after it's created
                logging.info(f"Writing phase diagram data to ArangoDB for timestep {step_index}")
                self.write_to_arangodb(step_index, "phase_diagram", "phase_diagram")
                arango_data_written = True
            
            if not self._check_timestep_files_integrity(step_index):
                raise RuntimeError(f"File integrity check failed for timestep {step_index}")
            
            if files_to_write:
                logging.info(f"All files for timestep {step_index} written successfully and verified: {files_to_write}")
            if arango_data_written:
                logging.info(f"ArangoDB data for timestep {step_index} written successfully")
            
        except Exception as e:
            logging.error(f"Error writing files for timestep {step_index}: {e}")
            self._cleanup_timestep_files(step_index, output_table_enabled, power_plant_table_enabled, thermagraph_svg_enabled, write_csv)
            raise
    
    def _verify_timestep_files(self, step_index: int, output_table_enabled: bool, power_plant_table_enabled: bool, 
                              thermagraph_svg_enabled: bool, write_csv: bool) -> None:
        """
        Verifies that all expected files for a timestep exist and are properly closed.
        
        Args:
            step_index (int): The time step index.
            output_table_enabled (bool): Whether main graph output table is enabled.
            power_plant_table_enabled (bool): Whether power plant table is enabled.
            thermagraph_svg_enabled (bool): Whether ThermaGraph SVG generation is enabled.
            write_csv (bool): Whether CSV files should be written.
        """
        expected_files = []
        
        if output_table_enabled and write_csv:
            expected_files.append(os.path.join(self._run_dir, f"{self._run_id}_main_graph_{step_index}.csv"))
        
        if power_plant_table_enabled and write_csv:
            expected_files.append(os.path.join(self._run_dir, f"{self._run_id}_power_plant_{step_index}.csv"))
        
        if thermagraph_svg_enabled:
            expected_files.append(f"thermagraph_output_{step_index}.svg")
        
        missing_files = []
        for filename in expected_files:
            if not os.path.exists(filename):
                missing_files.append(filename)
        
        if missing_files:
            logging.warning(f"Missing files for timestep {step_index}: {missing_files}")
        else:
            logging.debug(f"All expected files for timestep {step_index} are present: {expected_files}")
    
    def _cleanup_timestep_files(self, step_index: int, output_table_enabled: bool, power_plant_table_enabled: bool, 
                               thermagraph_svg_enabled: bool, write_csv: bool) -> None:
        """
        Cleans up any partially written files for a timestep in case of errors.
        
        Args:
            step_index (int): The time step index.
            output_table_enabled (bool): Whether main graph output table is enabled.
            power_plant_table_enabled (bool): Whether power plant table is enabled.
            thermagraph_svg_enabled (bool): Whether ThermaGraph SVG generation is enabled.
            write_csv (bool): Whether CSV files should be written.
        """
        files_to_cleanup = []
        
        if output_table_enabled and write_csv:
            files_to_cleanup.append(os.path.join(self._run_dir, f"{self._run_id}_main_graph_{step_index}.csv"))
        
        if power_plant_table_enabled and write_csv:
            files_to_cleanup.append(os.path.join(self._run_dir, f"{self._run_id}_power_plant_{step_index}.csv"))
        
        if thermagraph_svg_enabled:
            files_to_cleanup.append(f"thermagraph_output_{step_index}.svg")
        
        for filename in files_to_cleanup:
            try:
                if os.path.exists(filename):
                    os.remove(filename)
                    logging.debug(f"Cleaned up file: {filename}")
            except Exception as e:
                logging.error(f"Failed to cleanup file {filename}: {e}")
    
    def _get_expected_files_for_timestep(self, step_index: int) -> list:
        """
        Returns a list of expected files for a given timestep.
        
        Args:
            step_index (int): The time step index.
            
        Returns:
            list: List of expected filenames for this timestep.
        """
        expected_files = []
        write_csv = getattr(self.orchestrator.unit.surface.specs, 'table_to_csv', 'no') == 'yes'
        output_table_enabled = self.orchestrator.unit.surface.specs.output_table == 'yes'
        power_plant_table_enabled = (
            hasattr(self.orchestrator.unit.surface.specs, 'power_plant_table') and
            self.orchestrator.unit.surface.specs.power_plant_table == 'yes' and 
            self.orchestrator.unit.surface.__class__.__name__ == 'SurfaceUnitFlexiblePP'
        )
        
        thermagraph_svg_enabled = False
        if 'ThermaGraph' in self.addons:
            thermagraph_specs = getattr(self, 'ThermaGraph_specs', None)
            if thermagraph_specs and getattr(thermagraph_specs, 'per_timestep', 'no') == 'yes':
                auto_save_svg_val = self.specs.get('addons', {}).get('ThermaGraph', {}).get('auto_save_svg', getattr(thermagraph_specs, 'auto_save_svg', 'yes'))
                thermagraph_svg_enabled = auto_save_svg_val == 'yes'
        
        if output_table_enabled and write_csv:
            expected_files.append(os.path.join(self._run_dir, f"{self._run_id}_main_graph_{step_index}.csv"))
        
        if power_plant_table_enabled and write_csv:
            expected_files.append(os.path.join(self._run_dir, f"{self._run_id}_power_plant_{step_index}.csv"))
        
        if thermagraph_svg_enabled:
            expected_files.append(os.path.join(self._run_dir, f"{self._run_id}_thermagraph_output_{step_index}.svg"))
        
        return expected_files
    
    def _check_timestep_files_integrity(self, step_index: int) -> bool:
        """
        Checks if all expected files for a timestep exist and are properly closed.
        
        Args:
            step_index (int): The time step index.
            
        Returns:
            bool: True if all files exist and are properly closed, False otherwise.
        """
        expected_files = self._get_expected_files_for_timestep(step_index)
        
        if not expected_files:
            logging.debug(f"No files expected for timestep {step_index} - integrity check passed")
            return True  
        
        # Check if main CSV file exists (this should always be written if output_table is enabled)
        write_csv = getattr(self.orchestrator.unit.surface.specs, 'table_to_csv', 'no') == 'yes'
        output_table_enabled = self.orchestrator.unit.surface.specs.output_table == 'yes'
        
        if output_table_enabled and write_csv:
            main_csv_path = os.path.join(self._run_dir, f"{self._run_id}_main_graph_{step_index}.csv")
            main_csv_exists = os.path.exists(main_csv_path)
            if not main_csv_exists:
                logging.warning(f"Main CSV file missing for timestep {step_index}: {main_csv_path}")
                return False
        
        missing_files = []
        for filename in expected_files:
            if not os.path.exists(filename):
                missing_files.append(filename)
            else:
                try:
                    with open(filename, 'r') as f:
                        pass
                except Exception as e:
                    logging.warning(f"File {filename} exists but may not be properly closed: {e}")
                    missing_files.append(filename)
        
        if missing_files:
            logging.warning(f"Missing or improperly closed files for timestep {step_index}: {missing_files}")
            return False
        
        logging.debug(f"All files for timestep {step_index} are present and properly closed: {expected_files}")
        return True
    
    def get_timestep_files_status(self, step_index: int) -> dict:
        """
        Returns the status of all files for a given timestep.
        
        Args:
            step_index (int): The time step index.
            
        Returns:
            dict: Dictionary with file status information.
        """
        expected_files = self._get_expected_files_for_timestep(step_index)
        status = {
            'timestep': step_index,
            'expected_files': expected_files,
            'files_status': {},
            'all_complete': True
        }
        
        for filename in expected_files:
            file_exists = os.path.exists(filename)
            file_closed = False
            
            if file_exists:
                try:
                    with open(filename, 'r') as f:
                        file_closed = True
                except Exception:
                    file_closed = False
            
            status['files_status'][filename] = {
                'exists': file_exists,
                'closed': file_closed,
                'complete': file_exists and file_closed
            }
            
            if not (file_exists and file_closed):
                status['all_complete'] = False
        
        return status
    
    def get_all_timestep_files_status(self) -> dict:
        """
        Returns the status of all files across all timesteps.
        
        Returns:
            dict: Dictionary with overall file status information.
        """
        total_timesteps = len(self.specs["schedule"]['dt_list'])
        overall_status = {
            'total_timesteps': total_timesteps,
            'timesteps_status': {},
            'overall_complete': True,
            'missing_files': [],
            'incomplete_timesteps': []
        }
        
        for step_index in range(total_timesteps):
            timestep_status = self.get_timestep_files_status(step_index)
            overall_status['timesteps_status'][step_index] = timestep_status
            
            if not timestep_status['all_complete']:
                overall_status['overall_complete'] = False
                overall_status['incomplete_timesteps'].append(step_index)
                
                # Collect missing files
                for filename, file_status in timestep_status['files_status'].items():
                    if not file_status['complete']:
                        overall_status['missing_files'].append({
                            'timestep': step_index,
                            'filename': filename,
                            'exists': file_status['exists'],
                            'closed': file_status['closed']
                        })
        
        return overall_status
    
    def wait_for_timestep_files_completion(self, step_index: int, timeout_seconds: int = 30, check_interval: float = 0.1) -> bool:
        """
        Waits for all files for a specific timestep to be written and properly closed.
        
        Args:
            step_index (int): The time step index.
            timeout_seconds (int): Maximum time to wait in seconds.
            check_interval (float): Interval between checks in seconds.
            
        Returns:
            bool: True if all files are complete within timeout, False otherwise.
        """
        import time
        
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            if self._check_timestep_files_integrity(step_index):
                return True
            time.sleep(check_interval)
        
        logging.warning(f"Timeout waiting for timestep {step_index} files to complete")
        return False

    def execute(self) -> None:
        """
        Executes the workflow.

        Steps:
        - Iterates over the time steps specified in the schedule.
        - Balances and advances the system state.
        - Saves results and performs post-processing tasks.
        """
        self._generate_power_plant_mappings()
        
        if 'functions' in self.specs and self.specs['functions']:
            self.function_evaluator.evaluate_functions(self.specs['functions'])
        current_date = self._start_date
        for i in tqdm(range(len(self.specs["schedule"]['dt_list'])), desc="Progress: ", ncols=100, file=sys.stdout):
            self._dt_months = np.round(self.specs['schedule']['dt_list'][i] * YEAR_TO_MONTH)
            if (type(self.orchestrator).__name__ != 'SystemExternal' and
                    self.specs['schedule']['bc_iteration_checkpoint'] == 'production_well_bottom'):
                self._native_system_iteration()
            else:
                self._external_system_iteration(self.function_evaluator.evaluated_functions)

            self._save_results(current_date)
            current_date += relativedelta(months=self._dt_months)
            write_csv = getattr(self.orchestrator.unit.surface.specs, 'table_to_csv', 'no') == 'yes'
            if getattr(self.orchestrator.unit.surface.specs, 'output_table', 'no') == 'yes':
                logging.info(f"[TANGO] Printing main graph table for timestep {i} (write_csv={write_csv})")
                self.generate_output_table(step_index=i, table_type="main_graph", write_csv=write_csv, print_table=True)

            if (getattr(self.orchestrator.unit.surface.specs, 'power_plant_table', 'no') == 'yes' and self.orchestrator.unit.surface.__class__.__name__ == 'SurfaceUnitFlexiblePP'):
                if hasattr(self.orchestrator.unit.surface, 'power_plant') and hasattr(self.orchestrator.unit.surface.power_plant, 'generate_output_table'):
                    logging.info(f"[TANGO] Printing power plant table for timestep {i} (write_csv={write_csv})")
                    self.generate_power_plant_output_table(step_index=i, write_csv=write_csv, print_table=True)

            self._write_timestep_files(i)

        if 'functions' in self.specs and self.specs['functions']:
            self.function_evaluator.evaluate_functions(self.specs['functions'])

        if (self.orchestrator.unit.injection_well.__class__.__name__ == 'WellUnitMOOSE'):
            self.dt_list = self.orchestrator.unit.injection_well.MOOSE_dt_list

        if self.economic:
            self.economic.execute(self._results, self.function_evaluator.evaluated_functions, self.dt_list)
            self.write_to_arangodb(0, "economic", "economic")
        
        self.write_to_arangodb(0, "physics", "physics")

        for addon_name, addon_instance in self.addons.items():
            addon_specs = getattr(self, f"{addon_name}_specs")

            if addon_specs.active.lower() == "yes":
                logging.info(f"Running post_process for addon: {addon_name}")
                addon_instance.post_process(addon_specs)

            if addon_specs.execute.lower() == "yes":
                logging.info(f"Running execute for addon: {addon_name}")
                addon_instance.execute()
        
        if 'batch_runner' in self.specs:
            self.process_batch_runner_outputs()
        else:
            self._post_processing()

        if hasattr(self, 'arango_manager') and self.arango_manager:
            status = self.arango_manager.check_status()
            summary = self.arango_manager.get_data_summary()
            logging.info(f"ArangoDB Final Status: {summary}")
            print(f"\n[ARANGODB] {summary}")
            
            if hasattr(self, '_current_simulation_id') and self._current_simulation_id:
                print(f"[ARANGODB] Simulation {self._current_simulation_id} completed successfully")

        if 'district_heating' in self.specs and self.specs.get('district_heating', {}).get('run_district_heating_simulator', '').lower() == 'yes':
            self.orchestrator.hotmapsdispatch_runner(self.economic._results, self._results, self.economic.specs.dt_list)

    def generate_output_table(self, step_index: int = -1, table_type: str = "main_graph", write_csv: bool = False, print_table: bool = True):
        """
        Generates and prints a table showing system information:
        Units, Ports, Pressure, Temperature, Enthalpy, and Mass Rate.
        Also writes the table data to a CSV file for each time step if write_csv is True.
        
        Args:
            step_index (int, optional): The time step index for CSV file naming.
            table_type (str, optional): Either "main_graph" or "power_plant" for file naming.
            write_csv (bool, optional): Whether to write the table to a CSV file.
            print_table (bool, optional): Whether to print the table to the console.
        """
        from tabulate import tabulate
        from termcolor import colored
        from itertools import cycle
        import csv

        graph_nodes = self.orchestrator.graph._node
        graph_edges = self.orchestrator.graph.edges

        table_data = []
        headers = ["Unit", "Port", "Pressure (MPa)", "Temperature (°C)", "Enthalpy (Kj/kg)", "Mass Rate (kg/s)"]

        for edge in graph_edges:
            source, target = edge
            source_unit = graph_nodes[source]['unit']
            target_unit = graph_nodes[target]['unit']

            try:
                outlet_fluid = getattr(source_unit, 'outlet_fluid', None)
                mass_rate = getattr(source_unit, 'mass_rate', 'N/A')
                if outlet_fluid:
                    outlet_P = getattr(outlet_fluid, 'P', 'N/A')
                    outlet_T = getattr(outlet_fluid, 'T', 'N/A')
                    outlet_H = getattr(outlet_fluid, 'H', 'N/A')
                    outlet_P = outlet_P / 1000000.0 if isinstance(outlet_P, (int, float)) else outlet_P
                    outlet_T = outlet_T - 273.15 if isinstance(outlet_T, (int, float)) else outlet_T
                    outlet_H = outlet_H / 1000.0 if isinstance(outlet_H, (int, float)) else outlet_H
                    table_data.append([source, "Outlet", outlet_P, outlet_T, outlet_H, mass_rate])
            except AttributeError:
                table_data.append([source, "Outlet", "Error", "Error", "Error", "N/A"])

            try:
                inlet_fluid = getattr(target_unit, 'inlet_fluid', None)
                mass_rate = getattr(target_unit, 'mass_rate', 'N/A')
                if inlet_fluid:
                    inlet_P = getattr(inlet_fluid, 'P', 'N/A')
                    inlet_T = getattr(inlet_fluid, 'T', 'N/A')
                    inlet_H = getattr(inlet_fluid, 'H', 'N/A')
                    inlet_P = inlet_P / 1000000.0 if isinstance(inlet_P, (int, float)) else inlet_P
                    inlet_T = inlet_T - 273.15 if isinstance(inlet_T, (int, float)) else inlet_T
                    inlet_H = inlet_H / 1000.0 if isinstance(inlet_H, (int, float)) else inlet_H
                    table_data.append([target, "Inlet", inlet_P, inlet_T, inlet_H, mass_rate])
            except AttributeError:
                table_data.append([target, "Inlet", "Error", "Error", "Error", "N/A"])

        if table_data:
            last_row = table_data.pop()
            table_data.insert(0, last_row)

        # Write to CSV file if requested
        if write_csv and step_index >= 0:
            csv_filename = os.path.join(self._run_dir, f"{self._run_id}_{table_type}_{step_index}.csv")
            try:
                with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(headers)
                    writer.writerows(table_data)
                print(f"Output table written to: {csv_filename}")
            except Exception as e:
                print(f"Error writing CSV file: {e}")

        if print_table:
            available_colors = ["cyan", "green", "yellow", "red", "blue", "magenta", "white"]
            unit_names = list({node for node in self.orchestrator.graph._node})
            color_map = {unit: color for unit, color in zip(unit_names, cycle(available_colors))}

            colored_table_data = []
            for row in table_data:
                unit_color = color_map.get(row[0], "white")
                colored_row = [colored(str(cell), unit_color, attrs=["bold"]) for cell in row]
                colored_table_data.append(colored_row)

            top_border = "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+"
            print(top_border)
            print(tabulate(colored_table_data, headers=headers, tablefmt="fancy_grid", colalign=("center", "center", "center", "center", "center", "center")).replace("─", " "))
            print(top_border)

    def generate_power_plant_output_table(self, step_index: int = -1, write_csv: bool = False, print_table: bool = True):
        """
        Generates and prints a power plant table showing system information.
        Also writes the table data to a CSV file for each time step if write_csv is True.
        
        Args:
            step_index (int, optional): The time step index for CSV file naming.
            write_csv (bool, optional): Whether to write the table to a CSV file.
            print_table (bool, optional): Whether to print the table to the console.
        """
        if not (hasattr(self.orchestrator.unit.surface, 'power_plant') and 
                hasattr(self.orchestrator.unit.surface.power_plant, 'generate_output_table')):
            return
            
        import csv
        from tabulate import tabulate
        from termcolor import colored
        from itertools import cycle
        
        graph_nodes = self.orchestrator.unit.surface.power_plant.nodes
        graph_edges = [(conn.source.label, conn.target.label) for conn in self.orchestrator.unit.surface.power_plant.connections]
        table_data = []
        headers = ["Unit", "Port", "Pressure (MPa)", "Temperature (°C)", "Enthalpy (kJ/kg)", "Mass Rate (kg/s)", "Vapor Mass Fraction"]
        processed_ports = set()
        
        for edge in graph_edges:
            source, target = edge
            source_unit = graph_nodes[source]
            target_unit = graph_nodes[target]
            
            for idx, outlet in enumerate(getattr(source_unit, 'outl', [])):
                port_key = (source, f"Outlet-{idx + 1}")
                if port_key not in processed_ports:
                    processed_ports.add(port_key)
                    x_attr = getattr(outlet, 'x', None)
                    x_val = x_attr.val if x_attr is not None and hasattr(x_attr, 'val') else 'N/A'
                    table_data.append([
                        source,
                        f"Outlet-{idx + 1}",
                        outlet.p.val / 10,
                        outlet.T.val,
                        outlet.h.val,
                        outlet.m.val,
                        x_val
                    ])
            
            for idx, inlet in enumerate(getattr(target_unit, 'inl', [])):
                port_key = (target, f"Inlet-{idx + 1}")
                if port_key not in processed_ports:
                    processed_ports.add(port_key)
                    x_attr = getattr(inlet, 'x', None)
                    x_val = x_attr.val if x_attr is not None and hasattr(x_attr, 'val') else 'N/A'
                    table_data.append([
                        target,
                        f"Inlet-{idx + 1}",
                        inlet.p.val / 10,
                        inlet.T.val,
                        inlet.h.val,
                        inlet.m.val,
                        x_val
                    ])
        
        # Rearrange table for better presentation
        if table_data:
            last_row = table_data.pop()
            table_data.insert(0, last_row)
        
        # Write to CSV file if requested
        if write_csv and step_index >= 0:
            csv_filename = os.path.join(self._run_dir, f"{self._run_id}_power_plant_{step_index}.csv")
            try:
                with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(headers)
                    writer.writerows(table_data)
                print(f"Output table written to: {csv_filename}")
            except Exception as e:
                print(f"Error writing CSV file: {e}")
        
        if print_table:
            available_colors = ["cyan", "green", "yellow", "red", "blue", "magenta", "white"]
            unit_names = list({row[0] for row in table_data})
            color_map = {unit: color for unit, color in zip(unit_names, cycle(available_colors))}
            
            colored_table_data = []
            for row in table_data:
                unit_color = color_map.get(row[0], "white")
                colored_row = [colored(str(cell), unit_color, attrs=["bold"]) for cell in row]
                colored_table_data.append(colored_row)
            
            top_border = "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+"
            print(top_border)
            print(tabulate(colored_table_data, headers=headers, tablefmt="fancy_grid", colalign=("center", "center", "center", "center", "center", "center", "center")).replace("─", " "))
            print(top_border)

    def process_batch_runner_outputs(self):
        """
        Processes batch runner outputs and writes results to a CSV file.
        Input parameters are written in the first columns, followed by output parameters.
        For simulation results with time series data, creates separate columns for each timestep.
        """
        if 'batch_runner' not in self.specs:
            return
            
        batch_config = self.specs['batch_runner']
        outputs_list = batch_config.get('outputs_list', [])
        inputs_list = batch_config.get('inputs_list', [])
        time_steps = batch_config.get('time_steps', [])
        output_file_name = batch_config.get('output_file_name', 'batch_runner_output.csv')
        
        economic_outputs = ['LCOE', 'CAPEX_well', 'CAPEX_surface_pipe', 'CAPEX_power_plant', 
                           'CAPEX_permitting', 'CAPEX_exploration', 'CAPEX_wells', 'CAPEX_total']
        
        input_values = {}
        for input_param in inputs_list:
            if '.' in input_param:
                param_parts = input_param.split('.')
                current_dict = self.specs
                
                try:
                    for part in param_parts:
                        if isinstance(current_dict, dict) and part in current_dict:
                            current_dict = current_dict[part]
                        else:
                            print(f"  Warning: Could not access {input_param} - {part} not found")
                            input_values[input_param] = None
                            break
                    else:
                        input_values[input_param] = current_dict
                except Exception as e:
                    print(f"  Error accessing {input_param}: {e}")
                    input_values[input_param] = None
            else:
                if input_param in self.specs:
                    input_values[input_param] = self.specs[input_param]
                else:
                    print(f"  Warning: {input_param} not found in specs")
                    input_values[input_param] = None
        
        output_values = {}
        for output_component in outputs_list:
            if output_component in economic_outputs:
                if hasattr(self, 'economic') and self.economic and hasattr(self.economic, '_results'):
                    if output_component in self.economic._results:
                        output_values[output_component] = self.economic._results[output_component]
                    else:
                        output_values[output_component] = None
                else:
                    print(f"  Warning: Economic results not available")
                    output_values[output_component] = None
            else:
                if output_component in self._results:
                    values = self._results[output_component]
                    for time_step in time_steps:
                        try:
                            ts_idx = int(time_step)
                        except (TypeError, ValueError):
                            output_values[f"{output_component}_{time_step}"] = None
                            continue
                        idx = ts_idx - 1 if ts_idx > 0 else ts_idx
                        if -len(values) <= idx < len(values):
                            output_values[f"{output_component}_{time_step}"] = values[idx]
                        else:
                            output_values[f"{output_component}_{time_step}"] = None
                else:
                    print(f"  Warning: {output_component} not found in simulation results")
                    for time_step in time_steps:
                        output_values[f"{output_component}_{time_step}"] = None
        
        self.write_batch_runner_csv(output_file_name, input_values, output_values)
        
        print(f"\nBatch runner results written to: {output_file_name}")

    def write_batch_runner_csv(self, output_file_name, input_values, output_values):
        """
        Writes batch runner results to a CSV file.
        
        Args:
            output_file_name (str): Name of the output CSV file
            input_values (dict): Dictionary of input parameter names and values
            output_values (dict): Dictionary of output parameter names and values
        """
        import csv
        import os
        
        headers = list(input_values.keys()) + list(output_values.keys())
        data = list(input_values.values()) + list(output_values.values())
        
        file_exists = os.path.exists(output_file_name)
        
        try:
            with open(output_file_name, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                if not file_exists:
                    writer.writerow(headers)
                
                writer.writerow(data)
                
            if not file_exists:
                print(f"Successfully created CSV file: {output_file_name}")
            else:
                print(f"Successfully appended to CSV file: {output_file_name}")
            
        except Exception as e:
            print(f"Error writing CSV file {output_file_name}: {e}")

    def process_batch_runner_inputs(self, inputs_list):
        """
        Processes batch runner inputs by accessing nested parameters in self.specs.
        Supports both simple parameters and nested parameters using dot notation.
        
        Args:
            inputs_list (list): List of input parameter names (can include dot notation for nested access)
        """
        for input_param in inputs_list:
            print(f"\nProcessing input: {input_param}")
            
            if '.' in input_param:
                param_parts = input_param.split('.')
                current_dict = self.specs
                
                try:
                    for part in param_parts:
                        if isinstance(current_dict, dict) and part in current_dict:
                            current_dict = current_dict[part]
                        else:
                            print(f"  Warning: Could not access {input_param} - {part} not found")
                            break
                    else:
                        print(f"  Input value for {input_param}: {current_dict}")
                        continue
                except Exception as e:
                    print(f"  Error accessing {input_param}: {e}")
                    continue
            else:
                if input_param in self.specs:
                    print(f"  Input value for {input_param}: {self.specs[input_param]}")
                else:
                    print(f"  Warning: {input_param} not found in specs")
