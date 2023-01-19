from tango.core import FluidState
from tango.models.base import *
from dataclasses import dataclass

@dataclass
class ModelSpecs:
    """Where specifications for a geothermal power generation cost simulation are provided."""
    def __init__(self, specs):
        self.fluid = specs['fluid_specs']

class ModelState:
    """Where computed state for a geothermal power generation cost simulation are stored."""

    def __init__(self, specs: ModelSpecs):
        self.specs = specs
        self.fluid_init_method = 'with' + self.specs.fluid['method']
        
        self.fluid: FluidState = getattr(FluidState, self.fluid_init_method)(**specs.fluid)
        self.injection_well: WellState
        self.production_well: WellState
        self.powerplant: PowerPlantState
        self.economics: EconomicsState

    def update_fluid_state_PT(self):
        self.fluid.updatePT(self.fluid.P, self.fluid.T)

    def add_reservoir_state(self, state: ReservoirState):
        self.reservoir: ReservoirState = state(self.specs.reservoir, self)

    def add_state(self, name: str, state):
        specs = getattr(self.specs, name)
        setattr(self, name, state(specs, self))


class Model:
    """Used to execute a geothermal power generation cost simulation."""

    def __init__(self, specs: ModelSpecs):
        self.specs = specs
        self.state = ModelState(self.specs)

    def add_well_model(self, model: WellModel):
        self.well_model = model(self.specs)

    def add_reservoir_model(self, model: ReservoirModel):
        self.reservoir_model = model(self.specs.reservoir)

    def add_model(self, name: str, model):
        specs = getattr(self.specs, name)
        state = getattr(self.state, name)
        setattr(self, name, model(specs, state))

    def execute(self) -> ModelState:
        state = ModelState(self.specs)
        self.injection_well_model.execute(state)
        self.reservoir_model.execute(state)
        self.production_well_model.execute(state)
        self.powerplant_model.execute(state)
        self.economics_model.execute(state)
        return state
