from tango.model import ModelState, Model
from tango.models.adams import *

from yaml import load
from yaml.loader import SafeLoader

def load_from_yaml(filename: str):
    with open(filename) as f:
        specs = load(f, Loader=SafeLoader)

    return specs

specs = load_from_yaml('adamsmodel.yml')

state = ModelState(specs)
state.add_state('reservoir', ReservoirStateAdams)
state.add_state('production_well', WellStateAdams)

model = Model(state, specs)
model.add_model('reservoir', ReservoirModelAdams)
model.add_model('production_well', WellModelAdams)
model.production_well.set_inlet_state(state.reservoir)

for i in range(10):
    model.reservoir.execute()
    model.production_well.execute()
    print(state.production_well.inlet_fluid.T)