from tango.model import ModelState, Model
from tango.models.adams import *
from tango.core import FluidState

from yaml import load
from yaml.loader import SafeLoader

def load_from_yaml(filename: str):
    with open(filename) as f:
        specs = load(f, Loader=SafeLoader)

    return specs

specs = load_from_yaml('closed_loop.yml')

state = ModelState(specs)
state.add_state('injection_well', WellStateAdams)
state.add_state('horizontal_well', WellStateAdams)
state.add_state('production_well', WellStateAdams)
state.add_state('boundary', WellStateAdams)
state.boundary.outlet_fluid = FluidState.withPT(specs['common']['fluid_name'], 3.5e6, 273.15+40)

model = Model(state, specs)
model.add_model('injection_well', WellModelAdams)
model.add_model('horizontal_well', HorizontalWellModelAdams)
model.add_model('production_well', WellModelAdams)
model.injection_well.set_inlet_state(state.boundary)
model.horizontal_well.set_inlet_state(state.injection_well)
model.production_well.set_inlet_state(state.horizontal_well)

print(model.horizontal_well.T_r[-1] - 273.15)

for i in range(10):
    model.injection_well.execute()
    model.horizontal_well.execute()
    model.production_well.execute()

    print(state.horizontal_well.inlet_fluid.T - 273.15, state.horizontal_well.outlet_fluid.T - 273.15)
