from tango.models.base import *

class ModelSpecs:
    """Where specifications for a geothermal power generation cost simulation are provided."""
    pass


class ModelState:
    """Where computed state for a geothermal power generation cost simulation are stored."""

    def __init__(self, specs: ModelSpecs):
        self.reservoir: ReservoirState
        self.injection_well: WellState
        self.production_well: WellState
        self.powerplant: PowerPlantState
        self.economics: EconomicsState


class Model:
    """Used to execute a geothermal power generation cost simulation."""

    def __init__(self, specs: ModelSpecs):
        self.specs = specs

    def add_reservoir_model(self, state: ReservoirState, model: ReservoirModel):
        self.reservoir_state = state(self.specs)
        self.reservoir_model = model(self.specs)

    def execute(self) -> ModelState:
        state = ModelState(self.specs)
        self.injection_well_model.execute(state)
        self.reservoir_model.execute(state)
        self.production_well_model.execute(state)
        self.powerplant_model.execute(state)
        self.economics_model.execute(state)
        return state
