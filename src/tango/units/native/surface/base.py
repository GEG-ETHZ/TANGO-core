from tango.core.config import *
from tango.core import FluidState
from tango.core.abstracts.unit import *

class SurfaceState():

    def __init__(self) -> None:
        pass


class SurfaceUnitNative(Unit):
    """The power plant unit based on Adams et al. (2015)."""
    def __init__(self, id, specs):
        super().__init__(id, specs)
        self.mass_rate: float = 0.0
        self.inlet_fluid: FluidState
        self.outlet_fluid: FluidState


    def _set_mult(self) -> None:
        """
            - m_dot_mult is to convert m_dot (well-pair level mass flow rate) at a producer
              to a pattern level mass flow rate (=injection mass flow rate)
        """
        self._m_dot_mult = 4.0 if self.specs.well_pattern in ['5SPOT', 'INVERTED_5SPOT'] else 1.0


    def _set_constants(self) -> None:
        if self.specs.cooling_mode == 'WET':
            self._coeffs_cooling = [1.2, 0., -3.79e-3, 1.95e-2]
            self._coeffs_condensing = [1.65, -6.24e-6, -5.03e-3, 0.]
        elif self.specs.cooling_mode == 'DRY':
            self._coeffs_cooling = [7.65e-1, 0., 0., 1.28e-1]
            self._coeffs_condensing = [0.619, 0., 0., 0.]
        else:
            raise ValueError(f"surface_cooling_tower_mode: {self.specs.cooling_mode} is not supported")


    def _BAC_regression_model(self, coeffs: list) -> float:
        """
        Baltimore Aircoil Specific (BAC) regression unit for cooling and condensing costs
        """
        a, b, c, d = coeffs
        T_ambient = self.specs.surface_temperature
        dT_approach = self.specs.approach_temperature
        dT_range = self._condensation_temperature_range
        return a / dT_approach + b * T_ambient + c * T_ambient / dT_approach + d / (dT_approach+dT_range)


    def _get_parasitic_power_fraction_cooling(self):
        return self._BAC_regression_model(coeffs=self._coeffs_cooling)


    def _get_parasitic_power_fraction_condensing(self):
        return self._BAC_regression_model(coeffs=self._coeffs_condensing)


    def init_inlet_state(self, inlet_state) -> None:
        self.inlet_fluid = FluidState.copy(inlet_state.outlet_fluid)


    def update_inlet_state(self) -> None:
        """
         updated inlet state based on inlet streams
                 (mass flow rate weighted average)
        """
        total_mass_rate = 0.
        for sl in self.inlet_streams:
            total_mass_rate += sl.mass_rate
        T_ave, P_ave, H_ave = 0., 0., 0.
        for sl in self.inlet_streams:
            wt = sl.mass_rate / total_mass_rate
            T_ave += wt * sl.fluid_state.T
            P_ave += wt * sl.fluid_state.P
            H_ave += wt * sl.fluid_state.H
        self.mass_rate = self._m_dot_mult * total_mass_rate
        try:
            self.inlet_fluid.updateHP(H=H_ave, P=P_ave)
        except:
            self.inlet_fluid.updatePT(P=P_ave, T=T_ave)


    def execute(self) -> None:
        self.update_inlet_state()
        self.update()
        # print("surface_in ", self.inlet_fluid.P, self.inlet_fluid.T)
        # print("surface_out ", self.outlet_fluid.P, self.outlet_fluid.T)
