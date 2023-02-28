from tango.models.base import *
from tango.models.adams import WellModelAdams
import numpy as np

class HorizontalWellModelAdams(WellModelAdams):
    """The well model based on Adams et al. (2015)."""

    def __init__(self, specs: WellSpecs, state: WellState) -> None:
        WellModelAdams.__init__(self, specs, state)

    def set_farfield_temperature(self):
        dTdz = self.specs.thermal_gradient
        T0 = self.specs.surface_temperature
        depth = self.specs.reservoir_depth
        self.T_r = np.full(self.specs.num_cells, T0 + depth * dTdz)  # rock temperature (K)
