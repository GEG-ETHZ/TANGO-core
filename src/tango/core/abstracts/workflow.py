from abc import ABC


class Workflow(ABC):

    system, economic_model = 2*[None]
    def __init__(self, specs: dict):
        self.specs = specs


    def _init_system(self) -> None:
        """
            initialize physical system - a collection of compute nodes (models) and their connections
            system takes care of 'techno (physics)' part of TANGO computations
        """
        raise NotImplementedError("Implement '_init_system' method in child Worflow class.")


    def _init_econ_model(self) -> None:
        raise NotImplementedError("Implement '_init_econ_model' method in child Worflow class.")


    def execute(self) -> None:
        raise NotImplementedError("Implement 'execute' method in child Worflow class.")

