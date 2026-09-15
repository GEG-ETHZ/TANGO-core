"""FluidState — thin CoolProp wrapper for tango_next.

Mirrors the minimal surface of ``src/tango/core/fluidstate.py`` (a CoolProp
``AbstractState`` wrapper) needed so far: PT/HP/PS construction, in-place
update, and the property accessors used by the discretized wellbore models
and isentropic-efficiency pump/compressor calcs. Extend as additional
components need more CoolProp input pairs (PQ, QT, ...).

Every CoolProp failure is wrapped as ``CoolPropError`` (see ``core/errors.py``)
so callers can identify a property-lookup failure without parsing traceback
strings or catching CoolProp's own exception type directly.
"""

from __future__ import annotations

import CoolProp

from tango_next.core.errors import CoolPropError


class FluidState:
    """Wraps a CoolProp ``AbstractState`` (BICUBIC-tabulated HEOS backend) for one fluid."""

    def __init__(self, fluid_name: str) -> None:
        """Construct an uninitialized state for ``fluid_name``; call an update_*/with_* method next."""
        self.fluid_name = fluid_name
        self._state = CoolProp.AbstractState("BICUBIC&HEOS", fluid_name)

    @staticmethod
    def with_PT(fluid_name: str, P: float, T: float) -> FluidState:
        """Construct a FluidState from pressure (Pa) and temperature (K)."""
        fs = FluidState(fluid_name)
        fs.update_PT(P, T)
        return fs

    @staticmethod
    def with_HP(fluid_name: str, H: float, P: float) -> FluidState:
        """Construct a FluidState from specific enthalpy (J/kg) and pressure (Pa)."""
        fs = FluidState(fluid_name)
        fs.update_HP(H, P)
        return fs

    @staticmethod
    def with_PS(fluid_name: str, P: float, S: float) -> FluidState:
        """Construct a FluidState from pressure (Pa) and specific entropy (J/(kg·K)).

        Used for isentropic-efficiency pump/compressor models: the isentropic
        outlet state at a target pressure, given the inlet state's entropy.
        """
        fs = FluidState(fluid_name)
        fs.update_PS(P, S)
        return fs

    @staticmethod
    def copy(other: FluidState) -> FluidState:
        """Construct a new FluidState with the same fluid and (P, T) as ``other``."""
        return FluidState.with_PT(other.fluid_name, other.P, other.T)

    def update_PT(self, P: float, T: float) -> None:
        """Update this state in place from pressure (Pa) and temperature (K)."""
        try:
            self._state.update(CoolProp.PT_INPUTS, P, T)
        except ValueError as exc:
            raise CoolPropError(
                f"updatePT(P={P:.6g} Pa, T={T:.6g} K) failed for {self.fluid_name}: {exc}",
            ) from exc

    def update_HP(self, H: float, P: float) -> None:
        """Update this state in place from specific enthalpy (J/kg) and pressure (Pa)."""
        try:
            self._state.update(CoolProp.HmassP_INPUTS, H, P)
        except ValueError as exc:
            raise CoolPropError(
                f"updateHP(H={H:.6g} J/kg, P={P:.6g} Pa) failed for {self.fluid_name}: {exc}",
            ) from exc

    def update_PS(self, P: float, S: float) -> None:
        """Update this state in place from pressure (Pa) and specific entropy (J/(kg·K))."""
        try:
            self._state.update(CoolProp.PSmass_INPUTS, P, S)
        except ValueError as exc:
            raise CoolPropError(
                f"updatePS(P={P:.6g} Pa, S={S:.6g} J/(kg*K)) failed for {self.fluid_name}: {exc}",
            ) from exc

    @property
    def P(self) -> float:
        """Pressure (Pa)."""
        return self._state.p()

    @property
    def T(self) -> float:
        """Temperature (K)."""
        return self._state.T()

    @property
    def H(self) -> float:
        """Specific enthalpy (J/kg)."""
        return self._state.hmass()

    @property
    def S(self) -> float:
        """Specific entropy (J/(kg·K))."""
        return self._state.smass()

    @property
    def rho(self) -> float:
        """Density (kg/m³)."""
        return self._state.rhomass()

    @property
    def mu(self) -> float:
        """Dynamic viscosity (Pa·s)."""
        return self._state.viscosity()

    @property
    def cp(self) -> float:
        """Isobaric specific heat capacity (J/(kg·K))."""
        return self._state.cpmass()
