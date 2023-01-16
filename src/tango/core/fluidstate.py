from CoolProp import CoolProp

from tango.core.constants import *


class FluidState:
    """Used to describe the thermophysical properties of a fluid."""


    def __init__(self, state: CoolProp.State):
        """Construct a FluidState object for a fluid.

        This constructor should not be used directly. Use instead the following
        static methods to create a FluidState object:

            - FluidState.withPT
            - FluidState.withPH
            - FluidState.withPQ
            - FluidState.withTQ
            - FluidState.withPS
        """
        self.cstate: CoolProp.State = state


    @staticmethod
    def withPT(fluidname: str, P: float, T: float, **_):
        """Create a FluidState object with given pressure and temperature.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            P (float): The fluid pressure (in Pa)
            T (float): The fluid temperature (in K)
        """
        return FluidState(CoolProp.State(fluidname, dict(P = P*PA_TO_KPA, T = T)))


    @staticmethod
    def withPH(fluidname: str, P: float, H: float):
        """Create a FluidState object with given pressure and specific enthalpy.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            P (float): The fluid pressure (in Pa)
            H (float): The fluid specific enthalpy (in J/kg)
        """
        return FluidState(CoolProp.State(fluidname, dict(P = P*PA_TO_KPA, H = H*J_TO_KJ)))


    @staticmethod
    def withPS(fluidname: str, P: float, S: float):
        """Create a FluidState object with given pressure and specific entropy.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            P (float): The fluid pressure (in Pa)
            S (float): The fluid specific entropy (in J/(kg*K))
        """
        return FluidState(CoolProp.State(fluidname, dict(P = P*PA_TO_KPA, S = S*J_TO_KJ)))


    @staticmethod
    def withPQ(fluidname: str, P: float, Q: float):
        """Create a FluidState object with given pressure and Q state.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            P (float): The fluid pressure (in Pa)
            Q (float): The fluid Q value, where Q = 0 is saturated liquid and Q = 1 is saturated vapor
        """
        PkPa = P * 0.001  # from Pa to kPa
        return FluidState(CoolProp.State(fluidname, dict(P = PkPa, Q = Q)))


    @staticmethod
    def withTQ(fluidname: str, T: float, Q: float):
        """Create a FluidState object with given temperature and Q state.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            T (float): The fluid temperature (in K)
            Q (float): The fluid Q value, where Q = 0 is saturated liquid and Q = 1 is saturated vapor
        """
        return FluidState(CoolProp.State(fluidname, dict(T = T, Q = Q)))


    def updatePT(self, P: float, T: float):
        """Update the fluid state with given new pressure and temperature.

        Args:
            P (float): The fluid pressure (in Pa)
            T (float): The fluid temperature (in K)
        """
        self.cstate.update(dict(T = T, P = P*PA_TO_KPA))


    def updatePH(self, P: float, H: float):
        """Update the fluid state with given new pressure and specific enthalpy.

        Args:
            P (float): The fluid pressure (in Pa)
            H (float): The fluid specific enthalpy (in J/kg)
        """
        self.cstate.update(dict(P = P*PA_TO_KPA, H = H*J_TO_KJ))


    @property
    def fluidname(self):
        return self.cstate.Fluid


    @property
    def P(self):
        """The fluid pressure (in Pa)."""
        return self.cstate.p * KPA_TO_PA


    @property
    def T(self):
        """The fluid temperature (in K)."""
        return self.cstate.T


    @property
    def H(self):
        """The fluid specific enthalpy (in J/kg)."""
        return self.cstate.h * KJ_TO_J


    @property
    def S(self):
        """The fluid specific entropy (in J/(kg*K))."""
        return self.cstate.s * KJ_TO_J


    @property
    def Q(self):
        """The fluid Q quality value (dimensionless)."""
        return self.cstate.Q


    @property
    def rho(self):
        """The fluid density (in kg/m3)."""
        return self.cstate.rho


    @property
    def cp(self):
        """The fluid specific heat capacity at constant pressure (in J/(kg*K))."""
        return self.cstate.cp * KJ_TO_J


    @property
    def mu(self):
        """The fluid viscosity (in Pa*s)."""
        return self.cstate.visc


    @property
    def Tcrit(self):
        """The fluid critical temperature (in K)"""
        return CoolProp.PropsSI('TCRIT', "", 0, "", 0, self.cstate.Fluid)


    @property
    def Pcrit(self):
        """The fluid critical pressure (in Pa)"""
        return CoolProp.PropsSI('PCRIT', "", 0, "", 0, self.cstate.Fluid)


    @T.setter
    def T(self, T: float):
        """Update the state of the fluid with a new temperature while keeping same pressure.

        Args:
            T (float): The new temperature of the fluid (in K)
        """
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
