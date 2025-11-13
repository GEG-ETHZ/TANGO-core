from abc import ABC, abstractmethod

class Workflow(ABC):
    r"""
    Abstract Base Workflow Class for process orchestration.

    Represents a high-level workflow that manages the execution of physical systems
    and their associated economic computations..

    Attributes:
        specs (dict): Specifications for the workflow, including configurations for system and economic units. ..
    """

    # TODO: figure out what this line was intended to do 
    orchestrator, economic_unit = 2 * [None]

    @abstractmethod
    def __init__(self, specs: dict):
        """
        Initializes a new instance of the Workflow class.

        Args:
            specs (dict): Specifications for the workflow.
        """
        self.specs = specs

    def _init_system(self) -> None:
        r"""
        Abstract method to initialize the physical system.

        The physical system consists of a collection of computational nodes (units)
        and their connections. This method handles the "techno (physics)" part
        of the computations.

        Raises:
            NotImplementedError: Must be implemented in derived classes.
        """
        raise NotImplementedError("Implement '_init_system' method in child Workflow class.")

    def _init_econ_unit(self) -> None:
        r"""
        Abstract method to initialize the economic unit.

        The economic unit handles financial computations and analyses.

        Raises:
            NotImplementedError: Must be implemented in derived classes.
        """
        raise NotImplementedError("Implement '_init_econ_unit' method in child Workflow class.")

    @abstractmethod
    def execute(self) -> None:
        r"""
        Abstract method to execute the workflow.

        The workflow encompasses the system computations and economic analyses.

        Raises:
            NotImplementedError: Must be implemented in derived classes.
        """
        raise NotImplementedError("Implement 'execute' method in child Workflow class.")
