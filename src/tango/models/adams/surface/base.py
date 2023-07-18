from tango.models.base import *
from tango.core.config import *
from tango.core import FluidState


class SurfaceSpecsAdams(CommonSpecs):
    pipe_diameter: float = 0.41 # (m)
    pipe_length_per_well_pair: float = 750 # (m)


class SurfaceModelAdams(SurfaceModel):
    """The power plant model based on Adams et al. (2015)."""
    def __init__(self):
        pass


    def set_mdot(self) -> None:
        """
            - mass_flow_rate = flow rate at an injector (Kg/s)
            - m_dot = flow rate at each well pair (Kg/s)
        """
        if self.specs.well_pattern not in WELL_PATTERN_OPTIONS:
            raise RuntimeError(f"well_pattern: {self.well_pattern} is not supported")
        self.m_dot = self.specs.mass_flow_rate
        if self.specs.well_pattern == 'INVERTED_5SPOT':
            self.m_dot = self.specs.mass_flow_rate / 4.0


    def set_inlet_state(self, state, state_from) -> None:
        state.inlet_fluid = state_from.outlet_fluid # inlet_fluid at production_well


    def execute(self, state) -> None:
        self.update(state)
