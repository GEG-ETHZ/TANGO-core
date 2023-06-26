from tango.model import ModelState, Model
from tango.models.adams import *

class CGSModelStateAdams(ModelState):
    """The state of the conventional geothermal system based on Adams model."""
    def __init__(self):
        self.injection_well = WellStateAdams()
        self.reservoir = ReservoirStateAdams()
        self.production_well = WellStateAdams()
        self.surface = SurfaceStateAdams()
        self.economic = EconomicStateAdams()


class CGSModelAdams(Model):
    """The model of the conventional geothermal system based on Adams model."""
    def __init__(self, specs: dict): # add physics-based models
        super().__init__(specs)
        self.add_model('reservoir', ReservoirModelAdams)
        self.add_model('production_well', WellModelAdams)
        self.add_model('surface', SurfaceModelAdams)
        self.add_model('injection_well', WellModelAdams)

    def initialize(self, state: CGSModelStateAdams):
        self.reservoir.init_state(state.reservoir)
        self.surface.init_state(state.surface)

        getattr(self, 'injection_well').set_outlet_state(state.injection_well, state.reservoir)
        getattr(self, 'production_well').set_inlet_state(state.production_well, state.reservoir)
        getattr(self, 'surface').set_inlet_state(state.surface, state.production_well)
        # getattr(self, 'production_well').set_outlet_state(state.power_plant)

        self.economic = EconomicModelAdams(specs = self.specs['common'] | self.specs['economic'],
                                           model_dict=self.model_dict)
        self.economic.set_inlet_state(state.surface)

    def execute(self, state: CGSModelStateAdams): #-> ModelResult:
        return super().execute(state)
        # return result object


class AGSModelAdams:
    pass