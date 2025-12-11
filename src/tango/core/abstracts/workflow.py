from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tango.units.registry import UNIT_OPTIONS


@dataclass
class Workflow(ABC):
    r"""Abstract Base Workflow Class for process orchestration.

    Represents a high-level workflow that manages the execution of physical systems
    and their associated economic computations..

    Attributes:
        specs (dict): Specifications for the workflow, including configurations for system and economic
        units.
        input_file (str): Path to the input file.
        user_id (str, optional): User ID for database operations.
        run_id (str, optional): Unique run ID for file naming.
        run_dir (str, optional): Directory for run-specific output files.
        unit_options (dict, optional): Dictionary of unit options.

    """

    # user inputs
    specs: dict
    input_file: str | None = None
    user_id: str | None = None
    run_id: str = "default"
    run_dir: Path | str = field(default_factory=lambda: Path().cwd())
    unit_options: dict = field(default_factory=lambda: UNIT_OPTIONS.copy())

    # attributes that get generated automatically
    results: dict = field(init=False, default_factory=dict)
    orchestrator: Any = field(init=False, default=None)
    economic_unit: Any = field(init=False, default=None)

    def __post_init__(self):
        """Complete initialization of Workflow"""
        self.init_system()
        self.init_econ_unit()

    @abstractmethod
    def init_system(self) -> None:
        r"""Abstract method to initialize the physical system.

        The physical system consists of a collection of computational nodes (units)
        and their connections. This method handles the "techno (physics)" part
        of the computations.

        Raises:
            NotImplementedError: Must be implemented in derived classes.

        """
        raise NotImplementedError("Implement '_init_system' method in child Workflow class.")

    @abstractmethod
    def init_econ_unit(self) -> None:
        r"""Abstract method to initialize the economic unit.

        The economic unit handles financial computations and analyses.

        Raises:
            NotImplementedError: Must be implemented in derived classes.

        """
        raise NotImplementedError("Implement '_init_econ_unit' method in child Workflow class.")

    @abstractmethod
    def execute(self) -> None:
        r"""Abstract method to execute the workflow.

        The workflow encompasses the system computations and economic analyses.

        Raises:
            NotImplementedError: Must be implemented in derived classes.

        """
        raise NotImplementedError("Implement 'execute' method in child Workflow class.")
