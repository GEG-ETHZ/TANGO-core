from datetime import datetime
from dateutil.relativedelta import relativedelta
from tqdm import tqdm
import numpy as np
import sys
import logging

from tango.core.abstracts.workflow import *
from tango.core.constants import *
from tango.core.config import *
from tango import utils
from tango.orchestrators.native import *
from tango.orchestrators.external import *
from tango.diagram_plotter import FluidDiagramPlotter
from tango.units.dataclasses import DiagramSpecs

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

    Methods:
        execute():
            Executes the workflow, including physics and economic computations.
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
        self._fluid_states = {}
        self.diagram_specs = DiagramSpecs.from_dict(self._process_specs(specs))

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
        self._fluid_states = utils.states_dict_generator(
            self.diagram_specs.include_Power_plant,
            self.orchestrator.graph.nodes,
            self.orchestrator.unit.surface.__class__.__name__,
            self._fluid_states
        )

    def _post_processing(self) -> None:
        """
        Handles post-processing tasks, including saving results and generating plots.
        """
        utils.write_results(
            input_file=self._input_file,
            results=(self._results, self.economic.get_results() if self.economic else None)
        )
        plotter1 = FluidDiagramPlotter(
            fluid_states=self._fluid_states,
            fluid=self.diagram_specs.fluid,
            unit_system=self.diagram_specs.unit_system,
            diagram_type=self.diagram_specs.diagram_type,
            x_min=self.diagram_specs.x_min,
            x_max=self.diagram_specs.x_max,
            y_min=self.diagram_specs.y_min,
            y_max=self.diagram_specs.y_max,
            isoline_config=self.diagram_specs.isoline_config
        )
        connections = utils.create_connections(
            self.diagram_specs.include_Power_plant,
            self.specs['graph']['edges'],
            self.orchestrator.unit.surface
        )
        plotter1.create_plot(connections)

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

        self._post_processing()


