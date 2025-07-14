from datetime import datetime
from dateutil.relativedelta import relativedelta
from tqdm import tqdm
import numpy as np
import sys
import logging
import importlib
import os
from copy import deepcopy

from tango.core.abstracts.workflow import *
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

    def __init__(self, specs: dict, input_file: str):
        """
        Initializes the NativeWorkflow object.

        Args:
            specs (dict): Specifications for the simulation.
            input_file (str): Path to the input file.

        Steps:
        - Initializes the physical and economic systems.
        - Sets up diagram specifications for plotting results.
        """
        super().__init__(specs)
        self._input_file = input_file
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
        while True:
            if self.orchestrator.max_itr_reached(count):
                break
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



    def execute(self) -> None:
        """
        Executes the workflow.

        Steps:
        - Iterates over the time steps specified in the schedule.
        - Balances and advances the system state.
        - Saves results and performs post-processing tasks.
        """
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
            if (self.orchestrator.unit.surface.specs.output_table == 'yes'):
                self.generate_output_table()

            if (self.orchestrator.unit.surface.specs.power_plant_table == 'yes' and self.orchestrator.unit.surface.__class__.__name__ == 'SurfaceUnitFlexiblePP'):
                self.orchestrator.unit.surface.power_plant.generate_output_table()

        if 'functions' in self.specs and self.specs['functions']:
            self.function_evaluator.evaluate_functions(self.specs['functions'])

        if (self.orchestrator.unit.injection_well.__class__.__name__ == 'WellUnitMOOSE'):
            self.dt_list = self.orchestrator.unit.injection_well.MOOSE_dt_list

        if self.economic:
            self.economic.execute(self._results, self.function_evaluator.evaluated_functions, self.dt_list)

        for addon_name, addon_instance in self.addons.items():
            addon_specs = getattr(self, f"{addon_name}_specs")

            if addon_specs.active.lower() == "yes":
                logging.info(f"Running post_process for addon: {addon_name}")
                addon_instance.post_process(addon_specs)

            if addon_specs.execute.lower() == "yes":
                logging.info(f"Running execute for addon: {addon_name}")
                addon_instance.execute()

        self._post_processing()
        if 'district_heating' in self.specs:
            self.orchestrator.hotmapsdispatch_runner(self.economic._results, self._results, self.economic.specs.dt_list)

    def generate_output_table(self):
        """
        Generates and prints a table showing system information:
        Units, Ports, Pressure, Temperature, Enthalpy, and Mass Rate.
        """
        from tabulate import tabulate
        from termcolor import colored
        from itertools import cycle

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
                    outlet_P = getattr(outlet_fluid, 'P', 'N/A') / 1000000.0
                    outlet_T = getattr(outlet_fluid, 'T', 'N/A') - 273.15
                    outlet_H = getattr(outlet_fluid, 'H', 'N/A') / 1000.0
                    table_data.append([source, "Outlet", outlet_P, outlet_T, outlet_H, mass_rate])
            except AttributeError:
                table_data.append([source, "Outlet", "Error", "Error", "Error", "N/A"])

            try:
                inlet_fluid = getattr(target_unit, 'inlet_fluid', None)
                mass_rate = getattr(target_unit, 'mass_rate', 'N/A')
                if inlet_fluid:
                    inlet_P = getattr(inlet_fluid, 'P', 'N/A') / 1000000.0
                    inlet_T = getattr(inlet_fluid, 'T', 'N/A') - 273.15
                    inlet_H = getattr(inlet_fluid, 'H', 'N/A') / 1000.0
                    table_data.append([target, "Inlet", inlet_P, inlet_T, inlet_H, mass_rate])
            except AttributeError:
                table_data.append([target, "Inlet", "Error", "Error", "Error", "N/A"])

        if table_data:
            last_row = table_data.pop()
            table_data.insert(0, last_row)

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
