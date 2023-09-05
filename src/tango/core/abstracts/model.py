from abc import ABC


class ModelSpecs(ABC):
    pass


class ModelState(ABC):

    def __init__(self):
        pass

    def update(self) -> None:
        pass


class Model(ABC):

    def __init__(self, specs) -> None:
        self.specs = specs


    def init_state(self) -> None:
        raise NotImplementedError("Implement 'init_state' method in your derived Model class.")


    def execute(self) -> None:
        raise NotImplementedError("Implement 'execute' method in your derived Model class.")
