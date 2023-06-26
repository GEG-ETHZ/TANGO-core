from tango.models.adams import CGSModelAdams, CGSModelStateAdams
from tango.core.yaml_loader import load_from_yaml

# specs = load_from_yaml('adamsmodel.yml')
specs = load_from_yaml('adamsmodel_genGEO_example.yml')

state = CGSModelStateAdams()
model = CGSModelAdams(specs)
model.init_state(state)

model.execute(state)

print(state.reservoir.outlet_fluid.T)