from tango.model import Model
from tango.models.adams import *

from yaml import load
from yaml.loader import SafeLoader

def load_from_yaml(filename: str):
    with open(filename) as f:
        specs = load(f, Loader=SafeLoader)

    return specs

specs = load_from_yaml('adamsmodel.yml')
model = Model(specs)

model.state.add_state('reservoir', ReservoirStateAdams)
model.add_model('reservoir', ReservoirModelAdams)

for i in range(10):
    model.reservoir.execute()
    print(model.state.reservoir.outlet_temperature)
