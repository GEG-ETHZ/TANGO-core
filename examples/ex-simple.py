from tango import *

# specs = ModelSpecs()
# specs.reservoir = ReservoirSpecsAdams()
# specs.reservoir.permeability = 1e-14
# specs.reservoir.depth = 300.0

# specs.injection_well = WellSpecsAdams()
# specs.injection_well



# model = Model(specs)



model = Model()
model.reservoir = ReservoirModelAdams()
model.injection_well = WellModelAdams(radius=0.3, length=1)

state = model.execute()

print(state)
