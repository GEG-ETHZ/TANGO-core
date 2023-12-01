import copy
import logging
from dataclasses import dataclass
import numpy as np

from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION
from tango.core.abstracts.unit import *
from tango.units.native.common import WellSpecsNative


class WellUnitNative(Unit):
    """The well unit based on Adams et al. (2015)."""
    def __init__(self, id: str, specs: dict):
        super().__init__(id, specs)
        self._specs = WellSpecsNative.from_dict(specs)

        # geometric parameters
        self._diameter = self._specs.diameter
        self._relative_roughness = self._specs.epsilon / self._diameter
        self._cross_sectional_area = 0.25 * np.pi * self._diameter ** 2
        self._well_length = self._set_well_length()

        # other parameters
        self._initialize_discretized_vars()
        self._initialize_farfield_temperature()
        self._set_gravity_multiplier()
        self._t_scaling_factor = self._compute_time_scaling_factor()

        self._t_d: float = 0. # dimensionless time at current time step
        self._t_d_old: float = 0. # dimensionless time at previos time step
        self.mass_rate: float = 0.0
        self.inlet_fluid: FluidState
        self.outlet_fluid: FluidState


    def _set_well_length(self) -> float:
        if self._specs.well_length is None:
            raise RuntimeError(f"Required parameter 'well_length' is not found in specs.")
        else:
            return self._specs.well_length


    def _initialize_farfield_temperature(self) -> None:
        if self._specs.vertical_deviation != None:
            raise ValueError(f"'vertical_deviation' is not supported in vertical well classes. Please use horizontal well.")
        zspace = np.linspace(self._specs.wellhead_depth, self._well_length, self._num_cells+1)
        zspace = (zspace[1:] + zspace[:-1]) * 0.5  # depth at cell centers
        dTdz = self._specs.thermal_gradient
        T0 = self._specs.surface_temperature
        self._T_r = T0 + zspace * dTdz  # rock temperature (K)


    def _initialize_discretized_vars(self) -> None:
        num_cells = self._specs.num_cells
        self._num_cells = num_cells
        self._dL = self._well_length/num_cells
        self._dz = self._well_length/num_cells
        self._P = np.zeros(num_cells)  # pressure (Pa)
        self._h = np.zeros(num_cells)  # specific enthalpy (J/kg)
        self._rho = np.zeros(num_cells)  # fluid density (kg/m3)
        self._mu = np.zeros(num_cells)  # fluid dynamic viscosity (Pa s)
        self._T_f = np.zeros(num_cells)  # fluid temperature (K)
        self._T_r = np.zeros(num_cells)  # far field temperature (K)
        self._u = np.zeros(num_cells)  # flow velocity (m/s)


    def _set_gravity_multiplier(self) -> None:
        self._g = GRAVITY_ACCELERATION * self._specs.gravity_scale_factor


    def _compute_time_scaling_factor(self) -> float:
        """Carslaw and Jaeger (1959) for the scaling of time."""
        return 4.0 * self._specs.rock_k / (self._specs.rock_density * self._specs.rock_cp * self._diameter ** 2)


    def _initialize_state(self) -> None:
        self.update_dimensionless_time(del_t=self._t_scaling_factor * self._specs.dt * YEAR_TO_SECOND)
        self.fluid_state_init = self.inlet_fluid
        self._P[0] = self.fluid_state_init.P
        self._h[0] = self.fluid_state_init.H
        self._rho[0] = self.fluid_state_init.rho
        self._mu[0] = self.fluid_state_init.mu
        self._T_f[0] = self.fluid_state_init.T
        self._u[0] = self.mass_rate / self._cross_sectional_area / self._rho[0]
        self.fluid_state_tmp = FluidState.copy(self.inlet_fluid)


    def _compute_Q_loss(self, delta_T: float, t_d: float) -> float:
        """Returns the heat loss introduced Zhang et al., 2011 (10.1016/j.geothermics.2011.08.003).

        Args:
            delta_T (float): temperature differences between the farfield and fluid (K)
            t_d (float): dimensionless time (-)

        Returns:
            float: the heat loss
        """
        if t_d <= 2.8:
            beta = (np.pi*t_d)**-0.5 + 0.5 - 0.25*(t_d/np.pi)**0.5 + 0.125*t_d
        else:
            beta = 2.0/(np.log(4.0*t_d) - 1.16) - 1.16/(np.log(4.0*t_d) - 1.16)**2

        return 2.0 * self._dL * np.pi * self._specs.rock_k * beta * delta_T


    def _compute_delta_P_loss(self, ff: float, rho: float, u: float) -> float:
        """Returns the pressure loss calculated using the Darcy--Weisbach equation.

        Args:
            ff (float): the friction factor (-)
            rho (float): the fluid density (kg/m3)
            u (float): the flow velocity (m/s)

        Returns:
            float: the pressure loss (Pa)
        """
        return 0.5 * ff * self._dL * rho * u ** 2 / self._diameter


    def _compute_friction_factor(self, rho, mu, u) -> float:
        """Returns the friction factor calculated using the Haaland equation (1983).

        Args:
            rho (float): the fluid density (kg/m3)
            mu (float): the dynamic viscosity (Pa s)
            u (float): the flow velocity (m/s)

        Returns:
            float: the friction factor (-)
        """
        Re = rho * u * self._diameter / mu  # Reynolds number
        r = self._relative_roughness  # relative roughness
        return (-1.8 * np.log10((r / 3.7) ** 1.11 + 6.9 / Re)) ** -2.0


    def get_well_length(self) -> float:
        return self._well_length


    def get_diameter(self) -> float:
        return self._diameter


    def get_probability_of_success(self) -> float:
        return self._specs.probability_of_success


    def update(self) -> None:
        """update dynamic variables along wellbore"""
        self._initialize_state()
        t_d = self.get_dimensionless_time()
        g, dz, f_dir = self._g, self._dz, self._f_dir
        mdot, A = self.mass_rate, self._cross_sectional_area
        for i in range(1, self._num_cells):
            ff = self._compute_friction_factor(self._rho[i-1], self._mu[i-1], self._u[i-1])
            dP_loss = self._compute_delta_P_loss(ff, self._rho[i-1], self._u[i-1])
            Q_loss = self._compute_Q_loss(delta_T=self._T_f[i-1] - self._T_r[i-1], t_d=t_d)
            self._P[i] = self._P[i - 1] - f_dir * self._rho[i - 1] * g * dz - dP_loss
            self._h[i] = self._h[i - 1] - f_dir * g * dz - Q_loss / mdot
            try:
                self.fluid_state_tmp.updateHP(self._h[i], self._P[i])
            except:
                logging.warning(f"Failed to update fluid state with HP. Updating with PT instead.")
                self.fluid_state_tmp.updatePT(self._P[i], self._T_f[i])
            self._rho[i] = self.fluid_state_tmp.rho
            self._mu[i] = self.fluid_state_tmp.mu
            self._T_f[i] = self.fluid_state_tmp.T
            self._u[i] = mdot / A / self._rho[i]

        self.ppp = self._P[i]
        self.hhh = self._h[i]
        self.ttt = self._T_f[i]
        # self.outlet_fluid.updateHP(self._h[i], self._P[i])

        # self.update_outlet_streams()


    def stream_interface(self) -> None:
        # self.update_inlet_state()
        self.update()
        self.outlet_fluid.updateHP(self.hhh, self.ppp)
        print("production_in ", self.inlet_fluid.P, self.inlet_fluid.T)
        print("production_out ", self.outlet_fluid.P, self.outlet_fluid.T)


    def update_dimensionless_time_old(self) -> None:
        self._t_d_old = self._t_d


    def init_inlet_state(self, inlet_state) -> None:
        self.inlet_fluid = FluidState.copy(inlet_state.outlet_fluid)


    # def update_inlet_state(self) -> None:
    #     """ update inlet state based on inlet streams (mass flow rate weighted average) """
    #     total_mass_rate = 0.
    #     for sl in self.inlet_streams:
    #         total_mass_rate += sl.mass_rate
    #     T_ave, P_ave, H_ave = 0., 0., 0.
    #     for sl in self.inlet_streams:
    #         wt = sl.mass_rate / total_mass_rate
    #         T_ave += wt * sl.fluid_state.T
    #         P_ave += wt * sl.fluid_state.P
    #         H_ave += wt * sl.fluid_state.H
    #     self.mass_rate = total_mass_rate
    #     try:
    #         self.inlet_fluid.updateHP(H=H_ave, P=P_ave)
    #     except:
    #         self.inlet_fluid.updatePT(P=P_ave, T=T_ave)


    def get_dimensionless_time(self) -> float:
        return self._t_d


    def get_dimensionless_time_old(self) -> float:
        return self._t_d_old


    def update_dimensionless_time(self, del_t) -> None:
        self._t_d = self._t_d_old + del_t
