from tango.runners.base import *

class RunnerAdamsCPG(Runner):

    def __init__(self,
                 specs: dict,
                 input_file: str):
        super().__init__(specs, input_file)
        self.x_lst, self.y_lst = [], []


    def converged(self) -> bool:

        dP_reservoir = self.state.reservoir.pressure_old - self.state.reservoir.outlet_fluid.P

        if np.abs(dP_reservoir) < self.runspec.dP_reservoir_threshold:
            return True

        self.x_lst.append(copy.deepcopy(self.state.surface.dP_pump))
        self.y_lst.append(dP_reservoir)
        if len(self.x_lst) == 1: # first call
            self.state.surface.dP_pump = 0.5 * dP_reservoir
        else:
            self.state.surface.dP_pump = utils.newton(self.x_lst, self.y_lst)
            self.x_lst.pop(0)
            self.y_lst.pop(0)

        self.workflow.surface.overwrite_pump_state(state=self.state.surface)

        return False


    def update_primary_variables(self) -> None:
        self.x_lst.clear()
        self.y_lst.clear()
        self.state.reservoir.pressure_old = copy.deepcopy(self.state.reservoir.outlet_fluid.P)
        self.state.reservoir.energy_extracted_old = copy.deepcopy(self.state.reservoir.energy_extracted)
