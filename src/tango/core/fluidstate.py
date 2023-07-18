import CoolProp
# from src.tango.core.constants import *


class FluidState:
    """Used to describe the thermophysical properties of a fluid."""


    def __init__(self, state: CoolProp.AbstractState):
        """Construct a FluidState object for a fluid.

        This constructor should not be used directly. Use instead the following
        static methods to create a FluidState object:

            - FluidState.withPT
            - FluidState.withPH
            - FluidState.withPQ
            - FluidState.withTQ
            - FluidState.withPS
        """
        self.cstate: CoolProp.AbstractState = state


    @staticmethod
    def copy(state):
        """Create a copy of a FluidState object

        Args:
            state (FluidState)

        Returns:
            FluidState
        """
        state_copy = CoolProp.AbstractState('HEOS', state.fluidname)
        state_copy.update(CoolProp.PT_INPUTS, state.P, state.T)
        return FluidState(state_copy)


    @staticmethod
    def withPT(fluidname: str, P: float, T: float):
        """Create a FluidState object with given pressure and temperature.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            P (float): The fluid pressure (in Pa)
            T (float): The fluid temperature (in K)
        """

        state = CoolProp.AbstractState('HEOS', fluidname)
        state.update(CoolProp.PT_INPUTS, P, T)
        return FluidState(state)


    @staticmethod
    def withHP(fluidname: str, H: float, P: float):
        """Create a FluidState object with given pressure and specific enthalpy.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            P (float): The fluid pressure (in Pa)
            H (float): The fluid specific enthalpy (in J/kg)
        """
        state = CoolProp.AbstractState('HEOS', fluidname)
        state.update(CoolProp.HmassP_INPUTS, H, P)
        return FluidState(state)


    @staticmethod
    def withPS(fluidname: str, P: float, S: float):
        """Create a FluidState object with given pressure and specific entropy.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            P (float): The fluid pressure (in Pa)
            S (float): The fluid specific entropy (in J/(kg*K))
        """
        state = CoolProp.AbstractState('HEOS', fluidname)
        state.update(CoolProp.PSmass_INPUTS, P, S)
        return FluidState(state)


    @staticmethod
    def withPQ(fluidname: str, P: float, Q: float):
        """Create a FluidState object with given pressure and Q state.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            P (float): The fluid pressure (in Pa)
            Q (float): The fluid Q value, where Q = 0 is saturated liquid and Q = 1 is saturated vapor
        """
        state = CoolProp.AbstractState('HEOS', fluidname)
        state.update(CoolProp.PQ_INPUTS, P, Q)
        return FluidState(state)


    @staticmethod
    def withQT(fluidname: str, Q: float, T: float):
        """Create a FluidState object with given temperature and Q state.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2)
            T (float): The fluid temperature (in K)
            Q (float): The molar Q value, where Q = 0 is saturated liquid and Q = 1 is saturated vapor
        """
        state = CoolProp.AbstractState('HEOS', fluidname)
        state.update(CoolProp.QT_INPUTS, Q, T)
        return FluidState(state)


    def updatePT(self, P: float, T: float):
        """Update the fluid state with given new pressure and temperature.

        Args:
            P (float): The fluid pressure (in Pa)
            T (float): The fluid temperature (in K)
        """
        self.cstate.update(CoolProp.PT_INPUTS, P, T)


    def updateHP(self, H: float, P: float):
        """Update the fluid state with given new pressure and specific enthalpy.

        Args:
            P (float): The fluid pressure (in Pa)
            H (float): The fluid specific enthalpy (in J/kg)
        """
        self.cstate.update(CoolProp.HmassP_INPUTS, H, P)

    def updatePS(self, P: float, S: float):
        """Update the fluid state with given new pressure and specific entropy.

        Args:
            P (float): The fluid pressure (in Pa)
            S (float): The fluid specific entropy (in J/(kg*K))
        """
        self.cstate.update(CoolProp.PSmass_INPUTS, P, S)

    def updatePQ(self, P: float, Q: float):
        self.cstate.update(CoolProp.PQ_INPUTS, P, Q)

    def updateQT(self, Q: float, T: float):
        self.cstate.update(CoolProp.QT_INPUTS, Q, T)

    @property
    def fluidname(self):
        return self.cstate.name()


    @property
    def P(self):
        """The fluid pressure (in Pa)."""
        return self.cstate.p()


    @property
    def T(self):
        """The fluid temperature (in K)."""
        return self.cstate.T()


    @property
    def H(self):
        """The fluid specific enthalpy (in J/kg)."""
        return self.cstate.hmass()


    @property
    def S(self):
        """The fluid specific entropy (in J/(kg*K))."""
        return self.cstate.smass()


    @property
    def Q(self):
        """The fluid Q quality value (dimensionless)."""
        return self.cstate.Q()


    @property
    def rho(self):
        """The fluid density (in kg/m3)."""
        return self.cstate.rhomass()


    @property
    def cp(self):
        """The fluid specific heat capacity at constant pressure (in J/(kg*K))."""
        return self.cstate.cpmass()


    @property
    def mu(self):
        """The fluid viscosity (in Pa*s)."""
        return self.cstate.viscosity()


    @property
    def Tcrit(self):
        """The fluid critical temperature (in K)"""
        return CoolProp.CoolProp.PropsSI('TCRIT', "", 0, "", 0, self.cstate.name())


    @property
    def Pcrit(self):
        """The fluid critical pressure (in Pa)"""
        return CoolProp.CoolProp.PropsSI('PCRIT', "", 0, "", 0, self.cstate.name())


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
        self.updateHP(self.P, H)
