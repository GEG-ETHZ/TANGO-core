import copy

from tango.runners.base import *

class RunnerStandaloneORC(Runner):

    def __init__(self,
                 specs: dict,
                 input_file: str):
        super().__init__(specs, input_file)
        self.x1_lst, self.y1_lst = [], []
        self.x2_lst, self.y2_lst = [], []
        self.x3_lst, self.y3_lst = [], []


    def set_STANDALONE_CGS(self) -> None:
        self.state = CGSModelStateAdamsORC()
        self.model = CGSModelAdamsORC(self.specs)
        self.model.initialize(self.state)


    def set_STANDALONE_AGS(self) -> None:
        raise NotImplementedError(f"workflow: 'STANDALONE_AGS' is not supported.")


    def set_CMG(self) -> None:
        raise NotImplementedError(f"workflow: 'CMG' is not supported.")


    def converged(self) -> bool:

        dP_reservoir = self.state.reservoir.pressure_old - self.state.reservoir.outlet_fluid.P
        dT_surface = self.state.surface.temperature_old - self.state.surface.outlet_fluid.T
        dP_surface = self.state.surface.inlet_fluid.P - self.state.surface.outlet_fluid.P - self.state.surface.dP_pipes

        if np.abs(dP_reservoir) < self.runspec.dP_reservoir_threshold and \
           np.abs(dT_surface) < self.runspec.dT_surface_threshold and \
           np.abs(dP_surface) < self.runspec.dP_surface_threshold:
            return True

        self.x1_lst.append(copy.deepcopy(self.state.surface.outlet_fluid.P))
        self.x2_lst.append(copy.deepcopy(self.state.surface.outlet_fluid.T))
        self.x3_lst.append(copy.deepcopy(self.state.production_well.dP_pump))
        self.y1_lst.append(dP_reservoir)
        self.y2_lst.append(dT_surface)
        self.y3_lst.append(dP_surface)
        if len(self.x1_lst) == 1: # first call
            root1 = self.state.surface.outlet_fluid.P + dP_reservoir
            # self.state.surface.outlet_fluid.T = self.state.surface.outlet_fluid.T # implicitly updated
            root3 = -1.0 * dP_surface
        else:
            root1 = utils.newton(self.x1_lst, self.y1_lst) #TODO: try solving all together
            root2 = utils.newton(self.x2_lst, self.y2_lst)
            root3 = utils.newton(self.x3_lst, self.y3_lst)
            self.x1_lst.pop(0), self.x2_lst.pop(0), self.x3_lst.pop(0)
            self.y1_lst.pop(0), self.y2_lst.pop(0), self.y3_lst.pop(0)

        self.model.surface.overwrite_outlet_state(state=self.state.surface) #TODO: update this

        return False


    def update_primary_variables(self) -> None:
        self.x1_lst.clear(), self.x2_lst.clear(), self.x3_lst.clear()
        self.y1_lst.clear(), self.y2_lst.clear(), self.y3_lst.clear()
        self.state.reservoir.pressure_old = copy.deepcopy(self.state.reservoir.outlet_fluid.P)
        self.state.reservoir.energy_extracted_old = copy.deepcopy(self.state.reservoir.energy_extracted)
        self.state.surface.temperature_old = copy.deepcopy(self.state.surface.outlet_fluid.T) #TODO: check

