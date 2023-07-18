from tango.models.base import *
from tango.models.adams import *
from tango.models.adams.surface import *
from tango.core.config import *

class CGSModelStateAdamsCPG(ModelState):
    """The state of the conventional geothermal system based on Adams model."""
    def __init__(self):
        self.injection_well = WellStateAdams()
        self.reservoir = ReservoirStateAdams()
        self.production_well = WellStateAdams()
        self.surface = SurfaceStateAdamsCPG()


class CGSModelAdamsCPG(Model):
    """The model of the conventional geothermal system based on Adams model."""
    def __init__(self, specs: dict):
        super().__init__(specs)
        self.add_model('injection_well', WellModelAdams)
        self.add_model('reservoir', ReservoirModelAdams)
        self.add_model('production_well', WellModelAdams)
        self.add_model('surface', SurfaceModelAdamsCPG)


    def initialize(self, state: CGSModelStateAdamsCPG):

        self.reservoir.set_boundaries(getattr(self, 'injection_well').specs,
                                      getattr(self, 'production_well').specs) # set inlet and outlet specs

        self.surface.init_state(state.surface)
        self.reservoir.init_state(state.reservoir)

        getattr(self, 'injection_well').set_inlet_state(state.injection_well, state.surface)
        getattr(self, 'reservoir').set_inlet_state(state.reservoir, state.injection_well)
        getattr(self, 'production_well').set_inlet_state(state.production_well, state.reservoir, isProducer=True)
        getattr(self, 'surface').set_inlet_state(state.surface, state.production_well)

        self.economic = EconomicModelAdams(specs = self.specs['common'] | self.specs['economic'],
                                           model_dict=self.model_dict)
        self.economic.set_inlet_state(state.surface)

    def execute(self, state: CGSModelStateAdamsCPG): #-> ModelResult:
        return super().execute(state)


class CGSModelStateAdamsORC(ModelState):
    """The state of the conventional geothermal system based on Adams model."""
    def __init__(self):
        self.injection_well = WellStateAdams()
        self.reservoir = ReservoirStateAdams()
        self.production_well = WellStateAdams()
        self.production_well_pump = WellStateAdams()
        self.surface = SurfaceStateAdamsORC()


class CGSModelAdamsORC(Model):
    """The model of the conventional geothermal system based on Adams model."""
    def __init__(self, specs: dict):
        super().__init__(specs)
        self.add_model('injection_well', WellModelAdams)
        self.add_model('reservoir', ReservoirModelAdams)
        self.add_model('production_well', WellModelAdams)
        self.add_model('production_well_pump', WellModelAdams)
        self.add_model('surface', SurfaceModelAdamsORC)


    def initialize(self, state: CGSModelStateAdamsORC):

        self.reservoir.set_boundaries(getattr(self, 'injection_well').specs,
                                      getattr(self, 'production_well').specs) # set inlet and outlet specs

        self.surface.init_state(state.surface)
        self.reservoir.init_state(state.reservoir)

        getattr(self, 'injection_well').set_inlet_state(state.injection_well, state.surface)
        getattr(self, 'reservoir').set_inlet_state(state.reservoir, state.injection_well)
        getattr(self, 'production_well').set_inlet_state(state.production_well, state.reservoir,
                                                         isProducer=True,
                                                         wellhead_depth=getattr(self, 'production_well_pump').specs.well_length)
        getattr(self, 'production_well_pump').set_inlet_state(state.production_well_pump, state.production_well,
                                                              isProducer=True)
        getattr(self, 'surface').set_inlet_state(state.surface, state.production_well_pump)

        self.economic = EconomicModelAdams(specs = self.specs['common'] | self.specs['economic'],
                                           model_dict=self.model_dict)
        self.economic.set_inlet_state(state.surface) # TODO: check cost for prd pump

    def execute(self, state: CGSModelStateAdamsORC): #-> ModelResult:
        return super().execute(state)


class AGSModelAdams:
    pass