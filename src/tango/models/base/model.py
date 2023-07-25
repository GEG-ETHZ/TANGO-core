from tango.models.base import *
from abc import ABC


class ModelSpecs(ABC):
    pass


class ModelState:
    """Where computed state for a geothermal power generation cost simulation are stored."""

    def __init__(self, specs: dict):
        self.specs = specs

    def add_state(self, name: str, state):
        setattr(self, name, state())


class Model:
    """Used to execute a geothermal power generation cost simulation."""

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
