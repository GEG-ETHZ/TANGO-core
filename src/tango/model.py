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
        setattr(self, name, state)


class Model:
    """Used to execute a geothermal power generation cost simulation."""

    def __init__(self, state: ModelState, specs: dict):
        self.specs = specs
        self.state = state

    def add_model(self, name: str, model):
        state = getattr(self.state, name)
        specs = self.specs['common'] | self.specs[name]
        setattr(self, name, model(specs, state))

    def execute(self) -> ModelState:
        state = ModelState(self.specs)
        self.injection_well_model.execute(state)
        self.reservoir_model.execute(state)
        self.production_well_model.execute(state)
        self.powerplant_model.execute(state)
        self.economics_model.execute(state)
        return state
