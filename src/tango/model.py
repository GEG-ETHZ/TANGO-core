from tango.models.base import *

class ModelState:
    """Where computed state for a geothermal power generation cost simulation are stored."""

    def __init__(self, specs: dict):
        self.specs = specs
        self.injection_well: WellState
        self.production_well: WellState
        self.reservoir: ReservoirState
        self.surface: SurfaceState
        self.results = {'time': [], 'q_condenser': [], 'q_cooler': [], 'w_pump': [], 'w_turbine': []} #TODO: check if list is ok (should it be scaler?)


    def add_state(self, name: str, state):
        setattr(self, name, state())


class Model:
    """Used to execute a geothermal power generation cost simulation."""

    def __init__(self, state: ModelState, specs: dict):
        self.specs = specs
        self.state = state
        self.model_list = []


    def add_model(self, name: str, model):
        state = getattr(self.state, name)
        specs = self.specs['common'] | self.specs[name]
        model = model(specs, state)
        self.model_list.append(model)
        setattr(self, name, model)


    def execute(self) -> ModelState:
        for model in self.model_list:
            print(f"Running model: {str(model.__class__)}")
            model.execute()
            # model.save_results()

        return self.state
