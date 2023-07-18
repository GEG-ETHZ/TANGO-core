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
        self.temperature_old: float = 333.15 # K temperature at previous time step
        self.w_net: float = 0.

        
class SurfaceModelAdamsORC(SurfaceModelAdams):

    """The power plant model based on Adams et al. (2015)."""
    def __init__(self, specs: dict):
        SurfaceModelAdams.__init__(self)
        self.specs = SurfaceSpecsAdamsORC(**specs)
        self.refrigerant_name = self.specs.refrigerant
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


    def pipe(self):
        """update state due to pressure drop between producer wellhead and surface plant inlet"""
        # get friction factor

        pass



    def update(self, state) -> None:

        self.pipe(state)

        pass
