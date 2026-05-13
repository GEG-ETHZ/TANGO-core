from tango.core.abstracts.workflow import Workflow
from tango.orchestrators.cmg import *


class CMGWorkflow(Workflow):
    """A workflow class for TANGO using CMG (Computer Modelling Group) integration.

    This workflow manages the initialization, execution, and results handling
    for simulations that use CMG-based physical systems.

    Attributes:
        input_file (str): Path to the input file for the workflow.
        results (dict): Stores results from the workflow execution.
        system (SystemCMG): The CMG-based physical system.
        economic (object): The economic analysis unit (not yet implemented).

    """

    def init_system(self) -> None:
        """Initializes the physical system as a collection of computational nodes (units)
        and their connections. This system handles the techno-physical computations.

        Uses `SystemCMG` for CMG-based integration.
        """
        self.system = SystemCMG(self.specs, unit_options=self.unit_options)

    def init_econ_unit(self) -> None:
        """Initializes the economic unit for the workflow, if applicable.

        Note:
        - This method is currently a placeholder and requires implementation.

        """
        self.economic = None
        raise NotADirectoryError()

    def stream_interface(self) -> None:
        """Executes the physical system and integrates it with the economic unit.

        Steps:
        - Runs the physical system's computations via the `execute` method.
        - If an economic unit is present, integrates its functionality.

        Note:
        - Economic unit integration is currently a placeholder.

        """
        self.system.execute()

        if self.economic is not None:
            pass  # Placeholder for economic unit integration.

    def execute(self):
        """Not implemented yet"""
        raise NotImplementedError()
