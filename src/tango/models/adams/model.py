from tango.models.base import *
from tango.models.adams import *
from tango.models.adams.surface import *
from tango.core.config import *

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
    def __init__(self, specs: dict):
        super().__init__(specs)
        self.add_model('injection_well', WellModelAdams)
        self.add_model('reservoir', ReservoirModelAdams)
        self.add_model('production_well', WellModelAdams)
        self.add_model('surface', self.get_surface_model())


    def get_surface_model(self) -> object:
        return eval(f"SurfaceModelAdams{MAP_FLUIDNAME_TO_SURFACE_PLANT_DESIGN[self.reservoir.fluid_name]}")


    def initialize(self, state: CGSModelStateAdams):

        self.reservoir.set_boundaries(getattr(self, 'injection_well').specs,
                                      getattr(self, 'production_well').specs) # set inlet and outlet specs

        self.surface.init_state(state.surface)
        self.reservoir.init_state(state.reservoir)

        getattr(self, 'injection_well').set_inlet_state(state.injection_well, state.surface, well_type='injector')
        getattr(self, 'reservoir').set_inlet_state(state.reservoir, state.injection_well)
        getattr(self, 'production_well').set_inlet_state(state.production_well, state.reservoir, well_type='producer')
        getattr(self, 'surface').set_inlet_state(state.surface, state.production_well)

        self.economic = EconomicModelAdams(specs = self.specs['common'] | self.specs['economic'],
                                           model_dict=self.model_dict)
        self.economic.set_inlet_state(state.surface)

    def execute(self, state: CGSModelStateAdams): #-> ModelResult:
        return super().execute(state)
        # return result object


class AGSModelAdams:
    pass