from tango.model import ModelState, Model
from tango.models.adams import *

class CGSModelStateAdams(ModelState):
    """The state of the conventional geothermal system based on Adams model."""
    def __init__(self):
        self.injection_well = WellStateAdams()
        self.reservoir = ReservoirStateAdams()
        self.production_well = WellStateAdams()
        self.surface = SurfaceStateAdams()


class CGSModelAdams(Model):
    """The model of the conventional geothermal system based on Adams model."""
    def __init__(self, specs: dict):
        super().__init__(specs)
        self.add_model('reservoir', ReservoirModelAdams)
        self.add_model('production_well', WellModelAdams)
        self.add_model('surface', SurfaceModelAdams)
        self.add_model('injection_well', WellModelAdams)

    def init_state(self, state: CGSModelStateAdams):
        self.reservoir.init_state(state.reservoir)
        self.surface.init_state(state.surface)
        # for model in self.model_dict.values():
        #     model.init_state()

        getattr(self, 'injection_well').set_outlet_state(state.injection_well, state.reservoir)
        getattr(self, 'production_well').set_inlet_state(state.production_well, state.reservoir)
        getattr(self, 'surface').set_inlet_state(state.surface, state.production_well)
        # getattr(self, 'production_well').set_outlet_state(state.power_plant)

    def execute(self, state: CGSModelStateAdams): #-> ModelResult:
        return super().execute(state)
        # return result object


class AGSModelAdams:
    pass