from tango.models.base import *
from abc import ABC


class ModelSpecs(ABC):
    pass


class ModelState:
    """Model states for each compute node"""

    def __init__(self, specs: dict):
        self.specs = specs

    def add_state(self, name: str, state):
        setattr(self, name, state())


class Model:
    """Compute model for each compute node and their execution"""

    def __init__(self, specs: dict):
        self.specs = specs
        self.model_dict = {}

    def add_model(self, name: str, model):
        specs = self.specs['common'] | self.specs[name]
        model = model(specs)
        self.model_dict[name] = model
        setattr(self, name, model)

    def execute(self, state):
        for name, model in self.model_dict.items():
            model.execute(getattr(state, name))

class System:
    """High level class that oversees model states and compute models"""
    def __init__(self, state, models):
        self.state = state
        self.models = models

    def max_itr_reached(self, count) -> bool:
        return False

    def balanced(self) -> bool:
        return True

    def update_time_dependent_vars(self) -> None:
        pass

    def update(self) -> None:
        pass

