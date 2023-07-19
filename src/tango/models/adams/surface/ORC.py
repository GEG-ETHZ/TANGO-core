from tango.core.config import *
from tango.core import FluidState
from tango.models.adams.surface.base import *
from dataclasses import dataclass

import logging
import numpy as np


@dataclass
class SurfaceSpecsAdamsORC(SurfaceSpecsAdams):
    initial_outlet_pressure: float = 1.2e6  # Initial guess of outlet (injector wellhead) pressure (Pa) for ORC
    initial_outlet_temperature: float = 333.15  # Initial guess of outlet (injector wellhead) temperature (K) for ORC
    refrigerant: str = 'R245fa'


class SurfaceStateAdamsORC(SurfaceState):
    def __init__(self):
        SurfaceState.__init__(self)
        self.inlet_fluid: FluidState
        self.outlet_fluid: FluidState
        self.dP_pump: float = 0.
        self.dP_pipes: float = 0.
        self.outlet_temperature_tmp: float = 0.
        self.w_net: float = 0.

        
class SurfaceModelAdamsORC(SurfaceModelAdams):

    """The power plant model based on Adams et al. (2015)."""
    def __init__(self, specs: dict):
        SurfaceModelAdams.__init__(self)
        self.specs = SurfaceSpecsAdamsORC(**specs)
        self.fluid_name = self.specs.fluid_name
        self.refrigerant_name = self.specs.refrigerant
        self.cross_sectional_area = 0.25 * np.pi * self.specs.pipe_diameter ** 2
        self.set_mdot()
        self.set_max_boiling_temperature()


    def set_max_boiling_temperature(self) -> float:
        """
            get max boiling temperature that will be used as a constraint for the organic fluid at the temperature
            with max saturated vapor entropy
        """
        P_crit = FluidState.withPT(self.refrigerant_name,
                                  P=self.specs.initial_outlet_pressure,
                                  T=self.specs.initial_outlet_temperature).Pcrit # P, T are arbitrary
        P_min = FluidState.withQT(self.refrigerant_name, Q=1.0, T=273.15).P # assume min pressure is condensing at 0 deg.C
        P_arr = np.linspace(P_min, P_crit, 1000)
        S_arr = np.zeros(len(P_arr))
        for i, P in enumerate(P_arr):
            S_arr[i] = FluidState.withPQ(self.refrigerant_name, P=P, Q=1.0).S
        S_max = np.max(S_arr)
        P_max = P_arr[np.argmax(S_arr)]
        self.max_boiling_temperature = FluidState.withPS(self.refrigerant_name, P=P_max, S=S_max).T


    def init_state(self, state) -> None:
        """
        ORC system:
            production_well - xxxx - injection_well
        """
        state.outlet_fluid = FluidState.withPT(self.fluid_name,
                                               P=self.specs.initial_outlet_pressure,
                                               T=self.specs.initial_outlet_temperature)
        state.outlet_temperature_tmp = state.outlet_fluid.T


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


    def get_friction_factor(self, rho: float, mu: float, u: float) -> float:
        d = self.specs.pipe_diameter
        epsilon = self.specs.epsilon
        Re = rho * u * d / mu  # Reynolds number
        r = epsilon / d
        return (-1.8*np.log10((r/3.7)**1.11 + 6.9/Re))**-2.0


    def get_pipe_pressure_drop(self, rho: float, u: float, ff: float) -> float:
        d = self.specs.pipe_diameter
        L = self.specs.well_spacing
        return 0.5 * ff * L * rho * u ** 2 / d

    def upadte_state_pipe(self, state) -> None:
        """update state at surface pile (pressure drop between producer wellhead and surface plant inlet)"""

        rho = state.inlet_fluid.rho
        mu = state.inlet_fluid.mu
        u = self.m_dot / self.cross_sectional_area / rho

        ff = self.get_friction_factor(rho, mu, u)
        state.dP_pipe = self.get_pipe_pressure_drop(rho, u, ff)

        state.inlet_fluid.updatePT(P=state.inlet_fluid.P - state.dP_pipe, T=state.inlet_fluid.T)


    def update(self, state) -> None:

        self.upadte_state_pipe(state)

        pass


    def overwrite_outlet_state(self, state, P, T) -> None:
        state.outlet_fluid.updatePT(P, T)
