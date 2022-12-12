from tango.model import Model
from tango.models.adams import *

model = Model(ReservoirSpecsAdams)
model.add_reservoir_model(ReservoirStateAdams, ReservoirModelAdams)
print(model.reservoir_state.reservoir_temperature)