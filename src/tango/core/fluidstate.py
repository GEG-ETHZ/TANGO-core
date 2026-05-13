import CoolProp

from tango.core.errors import (
    CoolPropError,
    InvalidEnthalpyError,
    InvalidEntropyError,
    InvalidPandHError,
    InvalidPandSError,
    SubzeroPandTError,
    SubzeroPressureError,
    SubzeroStateVarError,
    SubzeroTempError,
    check_feas_enthalpy,
    check_feas_entropy,
    check_feas_press,
    check_feas_temp,
)


class FluidState:
    """Represents the thermodynamic state of a fluid.

    This class provides various methods to create and manipulate fluid states using
    pressure, temperature, enthalpy, entropy, and quality (Q) values. The underlying
    calculations are handled by the CoolProp library.

    Attributes:
        cstate (CoolProp.AbstractState): The internal state object used for property calculations.

    """

    def __init__(self, state: CoolProp.AbstractState):
        """Initialize a new instance of the FluidState class with a given state.

        This constructor should not be used directly. Instead, use the following
        static methods to create a FluidState object:

            - FluidState.withPT
            - FluidState.withHP
            - FluidState.withPS
            - FluidState.withPQ
            - FluidState.withQT

        Args:
            state (CoolProp.AbstractState): The CoolProp state object representing the fluid.

        """
        self.cstate: CoolProp.AbstractState = state

    @staticmethod
    def copy(state):
        """Create a copy of a FluidState object.

        Args:
            state (FluidState): The FluidState object to be copied.

        Returns:
            FluidState: A new FluidState object with the same properties.

        """
        state_copy = CoolProp.AbstractState("HEOS", state.fluidname)
        try:
            state_copy.update(CoolProp.PT_INPUTS, state.P, state.T)
        except ValueError as cp_err:
            tango_errs: list[str] = []  # type: ignore[annotation-unchecked]
            p_err = False
            t_err = False
            if (tango_err := check_feas_press(state.P)) is not None:
                tango_errs.append(tango_err)
                p_err = True
            if (tango_err := check_feas_temp(state.T)) is not None:
                tango_errs.append(tango_err)
                t_err = True
            if len(tango_errs) != 0:
                msg = "\n".join(tango_errs)
                if p_err and t_err:
                    raise SubzeroPandTError(msg) from cp_err
                if p_err:
                    raise SubzeroPressureError(msg) from cp_err
                if t_err:
                    raise SubzeroTempError(msg) from cp_err
            else:
                raise CoolPropError(str(cp_err))

        return FluidState(state_copy)

    @staticmethod
    def withPT(fluidname: str, P: float, T: float):
        """Creates a FluidState object with a given pressure and temperature.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2).
            P (float): The fluid pressure (in Pa).
            T (float): The fluid temperature (in K).

        Returns:
            FluidState: A new FluidState object.

        """
        try:
            state = CoolProp.AbstractState("HEOS", fluidname)
            state.update(CoolProp.PT_INPUTS, P, T)
        except ValueError as cp_err:
            tango_errs: list[str] = []  # type: ignore[annotation-unchecked]
            p_err = False
            t_err = False
            if (tango_err := check_feas_press(P)) is not None:
                tango_errs.append(tango_err)
                p_err = True
            if (tango_err := check_feas_temp(T)) is not None:
                tango_errs.append(tango_err)
                t_err = True
            if len(tango_errs) != 0:
                msg = "\n".join(tango_errs)
                if p_err and t_err:
                    raise SubzeroPandTError(msg) from cp_err
                if p_err:
                    raise SubzeroPressureError(msg) from cp_err
                if t_err:
                    raise SubzeroTempError(msg) from cp_err
            else:
                raise CoolPropError(str(cp_err))

        return FluidState(state)

    @staticmethod
    def withHP(fluidname: str, H: float, P: float):
        """Creates a FluidState object with a given pressure and specific enthalpy.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2).
            H (float): The fluid specific enthalpy (in J/kg).
            P (float): The fluid pressure (in Pa).

        Returns:
            FluidState: A new FluidState object.

        """
        try:
            state = CoolProp.AbstractState("HEOS", fluidname)
            state.update(CoolProp.HmassP_INPUTS, H, P)
        except ValueError as cp_err:
            tango_errs: list[str] = []  # type: ignore[annotation-unchecked]

            p_err = False
            h_err = False
            if (tango_err := check_feas_press(P)) is not None:
                tango_errs.append(tango_err)
                p_err = True
            if (tango_err := check_feas_enthalpy(H)) is not None:
                tango_errs.append(tango_err)
                h_err = True
            if len(tango_errs) != 0:
                msg = "\n".join(tango_errs)
                if p_err and h_err:
                    raise InvalidPandHError(msg) from cp_err
                if p_err:
                    raise SubzeroPressureError(msg) from cp_err
                if h_err:
                    raise InvalidEnthalpyError(msg) from cp_err
            else:
                raise CoolPropError(str(cp_err))

        return FluidState(state)

    @staticmethod
    def withPS(fluidname: str, P: float, S: float):
        """Creates a FluidState object with a given pressure and specific entropy.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2).
            P (float): The fluid pressure (in Pa).
            S (float): The fluid specific entropy (in J/(kg*K)).

        Returns:
            FluidState: A new FluidState object.

        """
        try:
            state = CoolProp.AbstractState("HEOS", fluidname)
            state.update(CoolProp.PSmass_INPUTS, P, S)
        except ValueError as cp_err:
            tango_errs: list[str] = []  # type: ignore[annotation-unchecked]
            p_err = False
            s_err = False
            if (tango_err := check_feas_press(P)) is not None:
                tango_errs.append(tango_err)
                p_err = True
            if (tango_err := check_feas_entropy(S)) is not None:
                tango_errs.append(tango_err)
                s_err = True
            if len(tango_errs) != 0:
                msg = "\n".join(tango_errs)
                if p_err and s_err:
                    raise InvalidPandSError(msg) from cp_err
                if p_err:
                    raise SubzeroPressureError(msg) from cp_err
                if s_err:
                    raise InvalidEntropyError(msg) from cp_err
            else:
                raise CoolPropError(str(cp_err))

        return FluidState(state)

    @staticmethod
    def withPQ(fluidname: str, P: float, Q: float):
        """Creates a FluidState object with a given pressure and Q (quality) value.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2).
            P (float): The fluid pressure (in Pa).
            Q (float): The fluid quality value, where Q = 0 is saturated liquid and Q = 1 is saturated vapor.

        Returns:
            FluidState: A new FluidState object.

        """
        try:
            state = CoolProp.AbstractState("HEOS", fluidname)
            state.update(CoolProp.PQ_INPUTS, P, Q)
        except ValueError as cp_err:
            tango_errs: list[str] = []  # type: ignore[annotation-unchecked]
            p_err = False
            if (tango_err := check_feas_press(P)) is not None:
                tango_errs.append(tango_err)
            if len(tango_errs) != 0:
                msg = "\n".join(tango_errs)
                if p_err:
                    raise SubzeroPressureError(msg) from cp_err
                else:
                    raise SubzeroStateVarError(msg) from cp_err
            else:
                raise CoolPropError(str(cp_err))

        return FluidState(state)

    @staticmethod
    def withQT(fluidname: str, Q: float, T: float):
        """Creates a FluidState object with a given temperature and Q (quality) value.

        Args:
            fluidname (str): The name of the fluid (e.g., Water, CO2).
            T (float): The fluid temperature (in K).
            Q (float): The fluid quality value, where Q = 0 is saturated liquid and Q = 1 is saturated vapor.

        Returns:
            FluidState: A new FluidState object.

        """
        try:
            state = CoolProp.AbstractState("HEOS", fluidname)
            state.update(CoolProp.QT_INPUTS, Q, T)
        except ValueError as cp_err:
            tango_errs: list[str] = []  # type: ignore[annotation-unchecked]
            t_err = False
            if (tango_err := check_feas_temp(T)) is not None:
                tango_errs.append(tango_err)
            if len(tango_errs) != 0:
                msg = "\n".join(tango_errs)
                if t_err:
                    raise SubzeroTempError(msg) from cp_err
                else:
                    raise SubzeroStateVarError(msg) from cp_err
            else:
                raise CoolPropError(str(cp_err))

        return FluidState(state)

    def updatePT(self, P: float, T: float):
        """Update the fluid state with a new pressure and temperature.

        Args:
            P (float): The fluid pressure (in Pa).
            T (float): The fluid temperature (in K).

        """
        try:
            self.cstate.update(CoolProp.PT_INPUTS, P, T)
        except ValueError as cp_err:
            tango_errs: list[str] = []
            p_err = False
            t_err = False
            if (tango_err := check_feas_press(P)) is not None:
                tango_errs.append(tango_err)
                p_err = True
            if (tango_err := check_feas_temp(T)) is not None:
                tango_errs.append(tango_err)
                t_err = True
            if len(tango_errs) != 0:
                msg = "\n".join(tango_errs)
                if t_err and p_err:
                    raise SubzeroPandTError(msg) from cp_err
                elif p_err:
                    raise SubzeroPressureError(msg) from cp_err
                elif t_err:
                    raise SubzeroTempError(msg) from cp_err

            else:
                raise CoolPropError(str(cp_err))

    def updateHP(self, H: float, P: float):
        """Update the fluid state with a new specific enthalpy and pressure.

        Args:
            H (float): The fluid specific enthalpy (in J/kg).
            P (float): The fluid pressure (in Pa).

        """
        try:
            self.cstate.update(CoolProp.HmassP_INPUTS, H, P)
        except ValueError as cp_err:
            tango_errs: list[str] = []
            p_err = False
            h_err = False
            if (tango_err := check_feas_press(P)) is not None:
                tango_errs.append(tango_err)
                p_err = True
            if (tango_err := check_feas_enthalpy(H)) is not None:
                tango_errs.append(tango_err)
                h_err = True
            if len(tango_errs) != 0:
                msg = "\n".join(tango_errs)
                if p_err and h_err:
                    raise InvalidPandHError(msg) from cp_err
                elif p_err:
                    raise SubzeroPressureError(msg) from cp_err
                elif h_err:
                    raise InvalidEnthalpyError(msg) from cp_err
            else:
                raise CoolPropError(str(cp_err))

    def updatePS(self, P: float, S: float):
        """Update the fluid state with a new pressure and specific entropy.

        Args:
            P (float): The fluid pressure (in Pa).
            S (float): The fluid specific entropy (in J/(kg*K)).

        """
        try:
            self.cstate.update(CoolProp.PSmass_INPUTS, P, S)
        except ValueError as cp_err:
            tango_errs: list[str] = []
            p_err = False
            s_err = False
            if (tango_err := check_feas_press(P)) is not None:
                tango_errs.append(tango_err)
                p_err = True
            if (tango_err := check_feas_entropy(S)) is not None:
                tango_errs.append(tango_err)
                s_err = True
            if len(tango_errs) != 0:
                msg = "\n".join(tango_errs)
                if p_err and s_err:
                    raise InvalidPandSError(msg) from cp_err
                if p_err:
                    raise SubzeroPressureError(msg) from cp_err
                if s_err:
                    raise InvalidEntropyError(msg) from cp_err
            else:
                raise CoolPropError(str(cp_err))

    def updatePQ(self, P: float, Q: float):
        """Update the fluid state with a new pressure and Q (quality) value.

        Args:
            P (float): The fluid pressure (in Pa).
            Q (float): The fluid quality value.

        """
        try:
            self.cstate.update(CoolProp.PQ_INPUTS, P, Q)
        except ValueError as cp_err:
            if P < 0.0:
                raise SubzeroPressureError(
                    "Absolute pressure must be greater than or equal to 0.0 Pa",
                ) from cp_err

    def updateQT(self, Q: float, T: float):
        """Update the fluid state with a new temperature and Q (quality) value.

        Args:
            Q (float): The fluid quality value.
            T (float): The fluid temperature (in K).

        """
        try:
            self.cstate.update(CoolProp.QT_INPUTS, Q, T)
        except ValueError as cp_err:
            tango_errs: list[str] = []  # type: ignore[annotation-unchecked]
            t_err = False
            if (tango_err := check_feas_temp(T)) is not None:
                tango_errs.append(tango_err)
                t_err = True
            if len(tango_errs) != 0:
                msg = "\n".join(tango_errs)
                if t_err:
                    raise SubzeroTempError(msg) from cp_err
                else:
                    # unreachable
                    pass
            else:
                raise CoolPropError(str(cp_err))

        except ValueError as cp_err:
            if T < 0.0:
                raise CoolPropError(
                    "Temperature must be greater than or equal to 0.0 K",
                ) from cp_err

    # Properties
    @property
    def fluidname(self) -> str:
        """Returns the name of the fluid."""
        return self.cstate.name()

    @property
    def P(self) -> float:
        """The fluid pressure (in Pa)."""
        return self.cstate.p()

    @property
    def T(self) -> float:
        """The fluid temperature (in K)."""
        return self.cstate.T()

    @property
    def H(self) -> float:
        """The fluid specific enthalpy (in J/kg)."""
        return self.cstate.hmass()

    @property
    def S(self) -> float:
        """The fluid specific entropy (in J/(kg*K))."""
        return self.cstate.smass()

    @property
    def Q(self) -> float:
        """The fluid Q quality value (dimensionless)."""
        return self.cstate.Q()

    @property
    def rho(self) -> float:
        """The fluid density (in kg/m³)."""
        return self.cstate.rhomass()

    @property
    def cp(self) -> float:
        """The fluid specific heat capacity at constant pressure (in J/(kg*K))."""
        return self.cstate.cpmass()

    @property
    def mu(self) -> float:
        """The fluid viscosity (in Pa*s)."""
        return self.cstate.viscosity()

    @property
    def Tcrit(self) -> float:
        """The fluid critical temperature (in K)."""
        return CoolProp.CoolProp.PropsSI("TCRIT", "", 0, "", 0, self.cstate.name())

    @property
    def Pcrit(self) -> float:
        """The fluid critical pressure (in Pa)."""
        return CoolProp.CoolProp.PropsSI("PCRIT", "", 0, "", 0, self.cstate.name())

    # Setters
    @T.setter
    def T(self, T: float):
        """Updates the state of the fluid with a new temperature while maintaining the same pressure."""
        self.updatePT(self.P, T)

    @P.setter
    def P(self, P: float):
        """Updates the state of the fluid with a new pressure while maintaining the same temperature."""
        self.updatePT(P, self.T)
