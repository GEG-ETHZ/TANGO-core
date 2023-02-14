from tango.core import FluidState
from tango.models.base import *

class ModelState:
    """Where computed state for a geothermal power generation cost simulation are stored."""

    def __init__(self, specs: dict):
        self.specs = specs
        self.set_fluid_specs(specs)

        self.injection_well: WellState
        self.production_well: WellState
        self.powerplant: PowerPlantState
        self.economics: EconomicsState

    def set_fluid_specs(self, specs: dict):
        self.fluid_init_method = 'with' + specs['fluid']['method']
        self.fluidname = specs['fluid']['fluidname']

    def add_state(self, name: str, state):
        setattr(self, name, state())


class Model:
    """Used to execute a geothermal power generation cost simulation."""

    def __init__(self, specs: dict):
        self.specs = specs
        self.state = ModelState(self.specs)

    def add_well_model(self, model: WellModel):
        self.well_model = model(self.specs)

    def add_reservoir_model(self, model: ReservoirModel):
        self.reservoir_model = model(self.specs.reservoir)

    def add_model(self, name: str, model):
        setattr(self, name, model(self.specs[name], self.state))

    def execute(self) -> ModelState:
        state = ModelState(self.specs)
        self.injection_well_model.execute(state)
        self.reservoir_model.execute(state)
        self.production_well_model.execute(state)
        self.powerplant_model.execute(state)
        self.economics_model.execute(state)
        return state
