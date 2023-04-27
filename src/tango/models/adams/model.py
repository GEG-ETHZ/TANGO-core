from tango.model import ModelState, Model
from tango.models.adams import *

class CGSModelStateAdams(ModelState):
    """The state of the conventional geothermal system based on Adams model."""
    def __init__(self):
        self.injection_well = WellStateAdams()
        self.reservoir = ReservoirStateAdams()
        self.production_well = WellStateAdams()
        self.power_plant = PowerPlantStateAdams()


class CGSModelAdams(Model):
    """The model of the conventional geothermal system based on Adams model."""
    def __init__(self, state: ModelState, specs: dict):
        super().__init__(state, specs)
        self.add_model('reservoir', ReservoirModelAdams)
        self.add_model('production_well', WellModelAdams)
        self.add_model('power_plant', PowerPlantModelAdams)
        self.add_model('injection_well', WellModelAdams)

        getattr(self, 'injection_well').set_outlet_state(state.reservoir)
        getattr(self, 'production_well').set_inlet_state(state.reservoir)
        getattr(self, 'power_plant').set_inlet_state(state.production_well)

    def execute(self) -> ModelState:
        return super().execute()


class AGSModelAdams:
    pass