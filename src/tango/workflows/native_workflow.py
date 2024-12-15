from datetime import datetime
from dateutil.relativedelta import relativedelta
from tqdm import tqdm
import numpy as np
import sys
import logging
import importlib
import os

from tango.core.abstracts.workflow import *
from tango.core.constants import *
from tango.core.config import *
from tango import utils
from tango.orchestrators.native import *
from tango.orchestrators.external import *

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
        self._init_system()
        self._init_econ_unit()
        self._results = dict()
        # self.ThermaGraph_specs = ThermaGraphSpecs.from_dict(specs['addons']['ThermaGraph'])
        self.addons_manager()


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
        UnitManager = get_system_class(utils.system_name(self.specs))
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

    def _external_system_iteration(self) -> None:
        """
        Balances the system and advances by one time step for external systems.
        """
        self.orchestrator.execute()
        self.orchestrator.update()
        self.orchestrator.execute()
        self.orchestrator.update_time_dependent_vars()

    def _save_results(self, current_date: datetime) -> None:
        """
        Saves simulation results for the current time step.

        Args:
            current_date (datetime): The current date in the simulation.
        """
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
        """
        addons_path = "/Users/morteza/Documents/projects/TANGO/src/tango/addons"
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
                        raise KeyError(f"Specifications for addon '{addon_name}' not found in input specs.")

                    addon_specs = addon_specs_class.from_dict(addon_specs_dict)
                    setattr(self, f"{addon_name}_specs", addon_specs)

                    addon_class_name = f"{addon_name}_addon"
                    if hasattr(addon_module, addon_class_name):
                        addon_class = getattr(addon_module, addon_class_name)
                    else:
                        raise AttributeError(f"'{addon_class_name}' not found in module '{addon_module.__name__}'.")

                    self.addons[addon_name] = addon_class(self.specs['graph'], self._results)

                    logging.info(f"Addon '{addon_name}' initialized successfully.")

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
        current_date = self._start_date
        for i in tqdm(range(len(self.specs["schedule"]['dt_list'])), desc="Progress: ", ncols=100, file=sys.stdout):
            self._dt_months = np.round(self.specs['schedule']['dt_list'][i] * YEAR_TO_MONTH)
            if (type(self.orchestrator).__name__ != 'SystemExternal' and
                    self.specs['schedule']['bc_iteration_checkpoint'] == 'production_well_bottom'):
                self._native_system_iteration()
            else:
                self._external_system_iteration()

            self._save_results(current_date)
            current_date += relativedelta(months=self._dt_months)
            print('tqdm', i, self._dt_months, current_date)

        if self.economic:
            self.economic.execute(self._results)

        # self.phase_diagram = ThermaGraph_addon(self.specs['graph'], self._results)
        # self.phase_diagram.post_process(self.ThermaGraph_specs)
        # self.phase_diagram.execute()
        for addon_name, addon_instance in self.addons.items():
            addon_specs = getattr(self, f"{addon_name}_specs")

            if addon_specs.active.lower() == "yes":
                logging.info(f"Running post_process for addon: {addon_name}")
                addon_instance.post_process(addon_specs)

            if addon_specs.execute.lower() == "yes":
                logging.info(f"Running execute for addon: {addon_name}")
                addon_instance.execute()

        self._post_processing()


