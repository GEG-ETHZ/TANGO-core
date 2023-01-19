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
        self.fluid: FluidState = getattr(FluidState, specs.fluid['method'])(**specs.fluid)
        self.reservoir: ReservoirState
        self.injection_well: WellState
        self.production_well: WellState
        self.powerplant: PowerPlantState
        self.economics: EconomicsState


class Model:
    """Used to execute a geothermal power generation cost simulation."""

    def __init__(self, specs: ModelSpecs):
        self.specs = specs
        self.state = ModelState(self.specs)

    def add_well_model(self, state: WellState, model: WellModel):
        self.well_state = state(self.specs)
        self.well_model = model(self.specs)

    def add_reservoir_model(self, state: ReservoirState, model: ReservoirModel):
        self.state.reservoir = state(self.specs.reservoir)
        self.reservoir_model = model(self.specs.reservoir)

    def execute(self) -> ModelState:
        state = ModelState(self.specs)
        self.injection_well_model.execute(state)
        self.reservoir_model.execute(state)
        self.production_well_model.execute(state)
        self.powerplant_model.execute(state)
        self.economics_model.execute(state)
        return state
