from tango.models.base import *
from tango.core.config import *
from tango.core import FluidState


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


    def set_constants(self) -> None:
        if self.specs.cooling_mode == 'WET':
            self.coeffs_cooling = [1.2, 0., -3.79e-3, 1.95e-2]
            self.coeffs_condensing = [1.65, -6.24e-6, -5.03e-3, 0.]
        elif self.specs.cooling_mode == 'DRY':
            self.coeffs_cooling = [7.65e-1, 0., 0., 1.28e-1]
            self.coeffs_condensing = [0.619, 0., 0., 0.]
        else:
            raise ValueError(f"surface_cooling_tower_mode: {self.specs.cooling_mode} is not supported")


    def BAC_regression_model(self, coeffs: list) -> float:
        """
        Baltimore Aircoil Specific (BAC) regression model for cooling and condensing costs
        """
        a, b, c, d = coeffs
        T_ambient = self.specs.surface_temperature
        dT_approach = self.specs.approach_temperature
        dT_range = self.condensation_temperature_range
        return a / dT_approach + b * T_ambient + c * T_ambient / dT_approach + d / (dT_approach+dT_range)


    def get_parasitic_power_fraction_cooling(self):
        return self.BAC_regression_model(coeffs=self.coeffs_cooling)


    def get_parasitic_power_fraction_condensing(self):
        return self.BAC_regression_model(coeffs=self.coeffs_condensing)


    def execute(self, state) -> None:
        self.update(state)
