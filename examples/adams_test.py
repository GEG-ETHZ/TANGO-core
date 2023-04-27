from tango.models.adams import CGSModelAdams, CGSModelStateAdams
from tango.core.yaml_loader import load_from_yaml

specs = load_from_yaml('adamsmodel.yml')

state = CGSModelStateAdams()
model = CGSModelAdams(state, specs)

model.execute()

print(state.reservoir.outlet_fluid.T)