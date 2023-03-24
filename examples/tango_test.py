from tango.model import ModelState, Model
from tango.models.adams import *
from tango.core.yaml_loader import load_from_yaml

specs = load_from_yaml('adamsmodel.yml')

state = ModelState(specs)
state.add_state('power_plant', PowerPlantStateAdams)
state.add_state('reservoir', ReservoirStateAdams)
state.add_state('production_well', WellStateAdams)
state.add_state('injection_well', WellStateAdams)

model = Model(state, specs)
model.add_model('reservoir', ReservoirModelAdams)
model.add_model('production_well', WellModelAdams)
model.add_model('power_plant', PowerPlantModelAdams)
model.add_model('injection_well', WellModelAdams)

model.injection_well.set_outlet_state(state.reservoir)
model.production_well.set_inlet_state(state.reservoir)
model.power_plant.set_inlet_state(state.production_well)


for i in range(5):
    model.execute()
    print(state.power_plant.w_turbine*1e-6)