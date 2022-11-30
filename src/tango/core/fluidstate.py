
import math
from dataclasses import dataclass
from typing import Optional
from CoolProp import CoolProp

@dataclass
class FluidState:
    """Used to describe the composition and thermophysical properties of a fluid."""

    def __init__(self, fluidname: str, T: float = 298.15, P: float = 1.0e5, state: Optional[CoolProp.State] = None):
        """Construct a FluidState object for a fluid.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            T (float, optional): The fluid temperature (in K). Defaults to 298.15.
            P (float, optional): The fluid pressure (in Pa). Defaults to 1.0e5.
            state (Optional[CoolProp.State], optional): The full state of the fluid already computed. Defaults to None.
        """
        if state == None:
            self._TK = T
            self._PkPa = P * 0.001
            self._state = CoolProp.State(fluidname, dict(T = self._TK, P = self._PkPa))  # Warning: P in kPa when using CoolProp.State!
        else:
            self._TK = state.T
            self._PkPa = state.p * 1000.0  # from kPa to Pa
            self._state = state


    @staticmethod
    def withPT(fluidname: str, P: float, T: float):
        """Create a FluidState object with given pressure and temperature.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            P (float): The fluid pressure (in Pa)
            T (float): The fluid temperature (in K)
        """
        PkPa = P * 0.001  # from Pa to kPa
        state = CoolProp.State(fluidname, dict(P = PkPa, T = T))
        return FluidState(fluidname, state = state)


    @staticmethod
    def withPH(fluidname: str, P: float, H: float):
        """Create a FluidState object with given pressure and specific enthalpy.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            P (float): The fluid pressure (in Pa)
            H (float): The fluid specific enthalpy (in J/kg)
        """
        PkPa = P * 0.001
        HkJ = H * 0.001  # from J/kg to kJ/kg
        state = CoolProp.State(fluidname, dict(P = PkPa, H = HkJ))
        return FluidState(fluidname, state = state)


    @staticmethod
    def withPQ(fluidname: str, P: float, Q: float):
        """Create a FluidState object with given pressure and Q state.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            P (float): The fluid pressure (in Pa)
            Q (float): The fluid Q value, where Q = 0 is saturated liquid and Q = 1 is saturated vapor
        """
        PkPa = P * 0.001  # from Pa to kPa
        state = CoolProp.State(fluidname, dict(P = PkPa, Q = Q))
        return FluidState(fluidname, state = state)


    @staticmethod
    def withTQ(fluidname: str, T_C: float, Q: float):
        """Create a FluidState object with given temperature and Q state.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            T_C (float): The fluid temperature (in °C)
            Q (float): The fluid Q value, where Q = 0 is saturated liquid and Q = 1 is saturated vapor
        """
        TK = T_C + 273.15
        state = CoolProp.State(fluidname, dict(T = TK, Q = Q))
        return FluidState(fluidname, state = state)


    @staticmethod
    def withPS(fluidname: str, P: float, S: float):
        """Create a FluidState object with given pressure and specific entropy.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            P (float): The fluid pressure (in Pa)
            S (float): The fluid specific entropy (in J/(kg*K))
        """
        PkPa = P * 0.001  # from Pa to kPa
        S_kJK = S * 0.001  # from J/(kg*K) to kJ/(kg*K)
        state = CoolProp.State(fluidname, dict(P = PkPa, S = S_kJK))
        return FluidState(fluidname, state = state)


    def updatePT(self, P: float, T: float):
        """Update the fluid state with given new pressure and temperature.

        Args:
            P (float): The fluid pressure (in Pa)
            T (float): The fluid temperature (in K)
        """
        self._TK = T
        self._PkPa = P * 0.001  # from Pa to kPa
        self._state.update(dict(T = T, P = self._PkPa))


    def updatePH(self, P: float, H: float):
        """Update the fluid state with given new pressure and specific enthalpy.

        Args:
            P (float): The fluid pressure (in Pa)
            H (float): The fluid specific enthalpy (in J/kg)
        """
        self._PkPa = P * 0.001  # from Pa to kPa
        HkJ = H * 0.001  # from J/kg to kJ/kg
        self._state.update(dict(P = self._PkPa, H = HkJ))
        self._TK = self._state.T


    @property
    def P(self):
        """The fluid pressure (in Pa)."""
        return self._state.p * 1000.0  # from kPa to Pa


    @property
    def T(self):
        """The fluid temperature (in K)."""
        return self._state.T


    @property
    def H(self):
        """The fluid specific enthalpy (in J/kg)."""
        return self._state.h * 1000.0  # from kJ/kg to J/kg


    @property
    def S(self):
        """The fluid specific entropy (in J/(kg*K))."""
        return self._state.s * 1000.0  # from kJ/(kg*K) to J/(kg*K)


    @property
    def rho(self):
        """The fluid density (in kg/m3)."""
        return self._state.rho


    @property
    def cp(self):
        """The fluid specific heat capacity at constant pressure (in J/(kg*K))."""
        return self._state.cp * 1000.0  # from kJ/(kg*K) to J/(kg*K)


    @property
    def mu(self):
        """The fluid viscosity (in Pa*s)."""
        return self._state.visc


    @property
    def Tcrit(self):
        """The fluid critical temperature (in K)"""
        return CoolProp.PropsSI('TCRIT', "", 0, "", 0, self._state.Fluid)


    @property
    def Pcrit(self):
        """The fluid critical pressure (in Pa)"""
        return CoolProp.PropsSI('PCRIT', "", 0, "", 0, self._state.Fluid)


    @staticmethod
    def Tcrit(fluidname: str):
        """Return the critical temperature of a fluid with given name (in K)"""
        return CoolProp.PropsSI('TCRIT', "", 0, "", 0, fluidname)

    @staticmethod
    def Pcrit(fluidname: str):
        """Return the critical pressure of a fluid with given name (in Pa)"""
        return CoolProp.PropsSI('PCRIT', "", 0, "", 0, fluidname)


    @T.setter
    def T(self, T: float):
        """Update the state of the fluid with a new temperature while keeping same pressure.

        Args:
            T (float): The new temperature of the fluid (in K)
        """
        if not math.close(T, self.T):
            self.updatePT(self.P, T)


    @P.setter
    def P(self, P: float):
        """Update the state of the fluid with a new pressure while keeping same temperature.

        Args:
            P (float): The new pressure of the fluid (in Pa)
        """
        self.updatePT(P, self.T)


    @H.setter
    def H(self, H: float):
        """Update the state of the fluid with a new specific enthalpy while keeping same pressure.

        Args:
            H (float): The new specific enthalpy of the fluid (in J/kg)
        """
        self.updatePH(self.P, H)
