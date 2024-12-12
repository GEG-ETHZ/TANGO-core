from tango.core.abstracts.workflow import Workflow
from tango.orchestrators.cmg import *

class CMGWorkflow(Workflow):
    """
    A workflow class for TANGO using CMG (Computer Modelling Group) integration.

    This workflow manages the initialization, execution, and results handling
    for simulations that use CMG-based physical systems.

    Attributes:
        _input_file (str): Path to the input file for the workflow.
        _results (dict): Stores results from the workflow execution.
        system (SystemCMG): The CMG-based physical system.
        economic (object): The economic analysis unit (not yet implemented).

    Methods:
        stream_interface():
            Executes the physical system and integrates with the economic unit if available.
    """

    def __init__(self, specs: dict, input_file: str):
        """
        Initializes the CMGWorkflow object.

        Args:
            specs (dict): Specifications for the simulation.
            input_file (str): Path to the input file.

        Steps:
        - Initializes the physical system.
        - Prepares the economic unit (placeholder implementation).
        - Initializes the results dictionary.
        """
        super().__init__(specs)
        self._input_file = input_file
        self._init_system()
        self._init_econ_unit()
        self._results = dict()

    def _init_system(self) -> None:
        """
        Initializes the physical system as a collection of computational nodes (units)
        and their connections. This system handles the techno-physical computations.

        Uses `SystemCMG` for CMG-based integration.
        """
        self.system = SystemCMG(self.specs)

    def _init_econ_unit(self) -> None:
        """
        Initializes the economic unit for the workflow, if applicable.

        Note:
        - This method is currently a placeholder and requires implementation.
        """
        self.economic = None
        # TODO: Implement

    def stream_interface(self) -> None:
        """
        Executes the physical system and integrates it with the economic unit.

        Steps:
        - Runs the physical system's computations via the `execute` method.
        - If an economic unit is present, integrates its functionality.

        Note:
        - Economic unit integration is currently a placeholder.
        """
        self.system.execute()

        if self.economic is not None:
            pass  # Placeholder for economic unit integration.

