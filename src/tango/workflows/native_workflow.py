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

def get_system_class(type_: str) -> object:
    try:
        return eval(SYSTEM_OPTIONS[type_.lower()])
    except:
        raise ValueError(f"System type: {type_} is not supported.")


class NativeWorkflow(Workflow):
    """TANGO native workflow based on genGEO"""

    def __init__(self, specs: dict, input_file: str):
        super().__init__(specs)
        self._input_file = input_file
        self._dt_months = np.round(self.specs['schedule']['dt'] * YEAR_TO_MONTH)
        self._num_time_steps = self.specs['schedule']['num_tsteps']
        self._start_date = datetime.strptime(self.specs['schedule']['start_date'], DATETIME_FMT)
        self._init_system()
        self._init_econ_unit()
        self._results = dict()


    def _init_system(self) -> None:
        """
            initialize physical system - a collection of compte nodes (units) and their connections
            system takes care of 'techno (physics)' part of TANGO computations
        """
        UnitManager = get_system_class(utils.system_name(self.specs))
        self.orchestrator = UnitManager(self.specs)


    def _init_econ_unit(self) -> None:
        """initialize econ unit, if applicable"""
        self.economic = None
        if 'economic' in self.specs:
            Unit = get_unit_class(type_='economic', unit_name=self.specs['economic']['type'])
            self.economic = Unit(specs=self.specs, nodes=self.orchestrator.graph.nodes)


    def _native_system_iteration(self) -> None:
        """update some unknown variables to balance the system. Then advance one time step"""
        count = 0
        while True:
            if self.orchestrator.max_itr_reached(count):
                break
            count += 1
            self.orchestrator.execute() # run compute nodes defined within the graph
            if self.orchestrator.balanced():
                logging.debug(f"System balanced after {count} iterations")
                break
            self.orchestrator.update()
        self.orchestrator.update_time_dependent_vars()


    def _save_results(self, current_date: datetime) -> None:
        """update self.results"""
        utils.parse_results(d=self._results,
                            nodes=self.orchestrator.graph.nodes,
                            current_date=current_date.strftime(DATETIME_FMT))


    def _post_processing(self) -> None:

        utils.write_inputs(input_file=self._input_file,
                           units=self.orchestrator.unit)

        utils.write_results(input_file=self._input_file,
                            results=(self._results,self.economic.get_results() if self.economic != None else None))


    def execute(self) -> None:
        current_date = self._start_date
        # print(type(self.orchestrator).__name__ )
        for i in tqdm(range(self._num_time_steps), desc="Progress: ", ncols = 100, file=sys.stdout):
            if (type(self.orchestrator).__name__ != 'SystemExternal'):
                self._native_system_iteration()
            else:
                self.orchestrator.execute()
            self._save_results(current_date)
            current_date = current_date + relativedelta(months=self._dt_months)

        if self.economic != None:
            self.economic.execute(self._results)

        self._post_processing()

