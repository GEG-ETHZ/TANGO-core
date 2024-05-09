from abc import ABC


class UnitSpecs(ABC):
    pass


class UnitState(ABC):

    def __init__(self):
        pass

    def update(self) -> None:
        pass


class Unit(ABC):

    def __init__(self, id, specs) -> None:
        self.id = id
        self.specs = specs


    def init_state(self) -> None:
        raise NotImplementedError("Implement 'init_state' method in your derived Unit class.")


    def execute(self) -> None:
        raise NotImplementedError("Implement 'execute' method in your derived Unit class.")
