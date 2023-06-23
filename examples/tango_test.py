from tango.model import ModelState, Model
from tango.models.adams import *
from tango.core.yaml_loader import load_from_yaml

#TODO: add main under src, set PYTHONPATH
#      reservoir+well ---> subsurface
#      no time step in genGEO?

#TODO: add logging

# specs = load_from_yaml('adamsmodel.yml')
specs = load_from_yaml('adamsmodel_genGEO_example.yml')

#TODO: add sanity check of input (add config.py)

state = ModelState(specs)
state.add_state('surface', SurfaceStateAdams)
state.add_state('reservoir', ReservoirStateAdams)
state.add_state('production_well', WellStateAdams)
state.add_state('injection_well', WellStateAdams)

model = Model(state, specs)
model.add_model('reservoir', ReservoirModelAdams)
model.add_model('production_well', WellModelAdams)
model.add_model('surface', SurfaceModelAdams)
model.add_model('injection_well', WellModelAdams)

model.injection_well.set_outlet_state(state.reservoir)
model.production_well.set_inlet_state(state.reservoir)
model.surface.set_inlet_state(state.production_well)

# TODO: not sure the way genGEO is handling time stepping makes sense
for i in range(5):
    model.execute() #TODO: add save results
    print(state.surface.w_turbine*1e-6)

if 'economic' in specs:
    econ = EconomicModelAdams(model, specs['common'] | specs['economic'])
    econ.init_state(state.surface)
    econ.execute()

print(econ.results)
