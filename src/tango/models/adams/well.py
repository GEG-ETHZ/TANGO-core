from tango.models.base import *
from tango.core import FluidState
from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION
from dataclasses import dataclass
import numpy as np


@dataclass
class WellSpecsAdams(CommonSpecs):
    """The well specs based on Adams et al. (2015)."""
    vertical_deviation: float = 0.0    # the vertical deviation angle defined in degrees
    diameter: float = 0.14    # the well diameter (m)
    epsilon: float = 0.01    # roughness of the well (m)
    num_cells: int = 100    # number of cells that is used for discretization
    gravity_scale_factor: float = 1.0    # the scale factor used for changing the direction of gravity
    well_length: float = None


class WellStateAdams(WellState):
    """The well state model"""
    def __init__(self) -> None:
        WellState.__init__(self)


class WellModelAdams(WellModel):
    """The well model based on Adams et al. (2015)."""
    def __init__(self, specs: dict, state: WellState) -> None:
        self.specs = WellSpecsAdams(**specs)
        self.state = state

        num_cells = self.specs.num_cells
        self.m_dot = self.specs.mass_flow_rate
        self.g = GRAVITY_ACCELERATION
        self.cross_section_area = 0.25 * np.pi * self.specs.diameter**2

        self.set_farfield_temperature()
        self.set_gravity_multiplier(self.specs.gravity_scale_factor)
        self.set_well_length()

        # discretization related parameters
        self.dL = self.well_length/num_cells
        self.dz = self.specs.reservoir_depth/num_cells
        self.t_d = 0.0  # initialize the non-dimensional time

        # See Carslaw and Jaeger (1959) for the scaling of time.
        self.t_scaling_factor = 4.0 * self.specs.rock_k \
                                / (self.specs.rock_density*self.specs.rock_cp*self.specs.diameter**2)

        self.P = np.zeros(num_cells)  # pressure (Pa)
        self.h = np.zeros(num_cells)  # specific enthalpy (J/kg)
        self.rho = np.zeros(num_cells)  # fluid density (kg/m3)
        self.mu = np.zeros(num_cells)  # fluid dynamic viscosity (Pa s)
        self.T_f = np.zeros(num_cells)  # fluid temperature (K)
        self.u = np.zeros(num_cells)  # flow velocity (m/s)

    def set_well_length(self):
        if self.specs.well_length is None:
            vertical_deviation_rad = np.deg2rad(self.specs.vertical_deviation)
            self.well_length = self.specs.reservoir_depth / np.cos(vertical_deviation_rad)
        else:
            self.well_length = self.specs.well_length

    def set_farfield_temperature(self):
        self.zspace = np.linspace(0.0, self.specs.reservoir_depth, self.specs.num_cells+1)
        self.zspace = (self.zspace[1:] + self.zspace[:-1]) * 0.5  # depth at cell centers

        dTdz = self.specs.thermal_gradient
        T0 = self.specs.surface_temperature
        self.T_r = T0 + self.zspace * dTdz  # rock temperature (K)

    def set_inlet_state(self, state) -> None:
        self.state.inlet_fluid = state.outlet_fluid
        self.state.outlet_fluid = FluidState.copy(self.state.inlet_fluid)

        self.fluid_state_tmp = self.state.outlet_fluid
        self.fluid_state_init = self.state.inlet_fluid

        self.f_dir = 1.0  # flow direction

    def set_outlet_state(self, state) -> None:
        self.state.outlet_fluid = state.inlet_fluid
        self.state.inlet_fluid = FluidState.copy(self.state.outlet_fluid)

        self.fluid_state_tmp = self.state.inlet_fluid
        self.fluid_state_init = self.state.outlet_fluid

        self.f_dir = -1.0 # flow direction

    def set_gravity_multiplier(self, g_mult):
        self.g_mult = g_mult
        self.g = self.g_mult*self.g

    def initialize_state(self) -> None:
        self.P[0] = self.fluid_state_init.P
        self.h[0] = self.fluid_state_init.H
        self.rho[0] = self.fluid_state_init.rho
        self.mu[0] = self.fluid_state_init.mu
        self.T_f[0] = self.fluid_state_init.T
        self.u[0] = self.m_dot / self.cross_section_area / self.rho[0]

    def update(self) -> None:
        self.initialize_state()
        self.t_d += self.t_scaling_factor * self.specs.dt * YEAR_TO_SECOND

        for i in range(1, self.specs.num_cells):
            ff = self.friction_factor(self.rho[i-1], self.mu[i-1], self.u[i-1])
            self.P[i] = self.P[i-1] - self.rho[i-1]*self.g*self.dz \
                        - self.f_dir*self.delta_P_loss(ff, self.rho[i-1], self.u[i-1])
            self.h[i] = self.h[i-1] - self.g*self.dz \
                        - self.Q_loss(self.T_f[i-1] - self.T_r[i-1]) / self.m_dot

            self.fluid_state_tmp.updateHP(self.h[i], self.P[i])

            self.rho[i] = self.fluid_state_tmp.rho
            self.mu[i] = self.fluid_state_tmp.mu
            self.T_f[i] = self.fluid_state_tmp.T
            self.u[i] = self.m_dot / self.cross_section_area / self.rho[i]

    def Q_loss(self, delta_T):
        """Returns the heat loss introduced Zhang et al., 2011 (10.1016/j.geothermics.2011.08.003).

        Args:
            delta_T (float): temperature differences between the farfield and fluid (K)

        Returns:
            float: the heat loss
        """
        t_d = self.t_d
        if t_d <= 2.8:
            beta = (np.pi*t_d)**-0.5 + 0.5 - 0.25*(t_d/np.pi)**0.5 + 0.125*t_d
        else:
            beta = 2.0/(np.log(4.0*t_d) - 1.16) - 1.16/(np.log(4.0*t_d) - 1.16)**2

        return 2.0 * self.dL * np.pi * self.specs.rock_k * beta * delta_T

    def delta_P_loss(self, friction_factor: float, rho: float, u: float) -> float:
        """Returns the pressure loss calculated using the Darcy--Weisbach equation.

        Args:
            friction_factor (float): the friction factor (-)
            rho (float): the fluid density (kg/m3)
            u (float): the flow velocity (m/s)

        Returns:
            float: the pressure loss (Pa)
        """
        return 0.5*friction_factor*self.dL*rho*u**2 / self.specs.diameter

    def friction_factor(self, rho, mu, u) -> float:
        """Returns the friction factor calculated using the Haaland equation (1983).

        Args:
            rho (float): the fluid density (kg/m3)
            mu (float): the dynamic viscosity (Pa s)
            u (float): the flow velocity (m/s)

        Returns:
            float: the friction factor (-)
        """
        Re = rho*u*self.specs.diameter / mu  # Reynolds number
        r = self.specs.epsilon / self.specs.diameter  # relative roughness

        return (-1.8*np.log10((r/3.7)**1.11 + 6.9/Re))**-2.0

    def execute(self) -> None:
        self.update()
