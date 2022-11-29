from tango.models.base import *
from tango.serialization import *


class ModelSpecs:
    """Where specifications for a geothermal power generation cost simulation are provided."""
    pass


class ModelState:
    reservoir: ReservoirState
    """Where computed state for a geothermal power generation cost simulation are stored."""
    def __init__(self, specs: ModelSpecs):
        self.reservoir_model: ReservoirState
        self.injection_well_model: WellState
        self.production_well_model: WellState
        self.powerplant_model: PowerPlantState
        self.economics_model: EconomicsState


class Model:

    def __init__(self, specs: ModelSpecs):
        self.reservoir_model: ReservoirModel   = createReservoirModel(specs)
        self.injection_well_model: WellModel   = createWellModel(specs)
        self.production_well_model: WellModel  = createWellModel(specs)
        self.powerplant_model: PowerPlantModel = createPowerPlantModel(specs)
        self.economics_model: EconomicsModel   = createEconomicsModel(specs)


    def execute(self) -> ModelState:
        state = ModelState(self.specs)
        self.reservoir_model.execute(state)
        self.injection_well_model.execute(state)
        self.production_well_model.execute(state)
        self.powerplant_model.execute(state)
        self.economics_model.execute(state)
        return state
