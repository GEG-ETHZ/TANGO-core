from tango.model import ModelState, Model
from tango.models.adams import *
from tango.core.yaml_loader import load_from_yaml

#TODO: add main under src, set PYTHONPATH
#      reservoir+well ---> subsurface
#      no time step in genGEO?

#TODO: add logging

specs = load_from_yaml('adamsmodel.yml')

#TODO: add sanity check of input

state = ModelState(specs)
state.add_state('surface', SurfaceStateAdams)
state.add_state('reservoir', ReservoirStateAdams)
state.add_state('production_well', WellStateAdams)
state.add_state('injection_well', WellStateAdams)
state.add_state('economic', EconomicStateAdams)

model = Model(state, specs)
model.add_model('reservoir', ReservoirModelAdams)
model.add_model('production_well', WellModelAdams)
model.add_model('surface', SurfaceModelAdams)
model.add_model('injection_well', WellModelAdams)
model.add_model('economic', EconomicModelAdams)


model.injection_well.set_outlet_state(state.reservoir)
model.production_well.set_inlet_state(state.reservoir)
model.surface.set_inlet_state(state.production_well)
model.economic.set_inlet_state(state.surface)
model.economic.set_models(model.model_list)

model.execute()
print(state.surface.w_turbine*1e-6)

#TODO add economic

# for i in range(5):
#     model.execute()
#     print(state.surface.w_turbine*1e-6)