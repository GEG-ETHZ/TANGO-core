from tango.models.base import *

class ModelState:
    """Where computed state for a geothermal power generation cost simulation are stored."""

    def __init__(self, specs: dict):
        self.specs = specs

        self.injection_well: WellState
        self.production_well: WellState
        self.reservoir: ReservoirState
        self.powerplant: PowerPlantState
        self.economics: EconomicsState

    def add_state(self, name: str, state):
        setattr(self, name, state())


class Model:
    """Used to execute a geothermal power generation cost simulation."""

    def __init__(self, state: ModelState, specs: dict):
        self.specs = specs
        self.state = state
        self.model_list = []

    def add_model(self, name: str, model):
        state = getattr(self.state, name)
        specs = self.specs['common'] | self.specs[name]
        model = model(specs, state)
        self.model_list.append(model)
        setattr(self, name, model)

    def execute(self) -> ModelState:
        for model in self.model_list:
            model.execute()

        return self.state
