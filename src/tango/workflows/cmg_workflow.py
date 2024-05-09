from tango.core.abstracts.workflow import Workflow
from tango.systems.cmg import *

class CMGWorkflow(Workflow): #TODO: Implement

    def __init__(self, specs: dict, input_file: str):
        super().__init__(specs)
        self._input_file = input_file
        self._init_system()
        self._init_econ_unit()
        self._results = dict()


    def _init_system(self) -> None:
        """
            initialize physical system - a collection of compte nodes (units) and their connections
            system takes care of 'techno (physics)' part of TANGO computations
        """
        self.system = SystemCMG(self.specs)


    def _init_econ_unit(self) -> None:
        """initialize econ unit, if applicable"""
        self.economic = None
        #TODO: Implement


    def execute(self) -> None:

        self.system.execute()

        if self.economic != None:
            pass

        # self._post_processing()