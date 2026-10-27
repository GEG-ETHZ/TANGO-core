"""FluidState — thin CoolProp wrapper for tango.

A thin wrapper around CoolProp's ``AbstractState``, covering PT/HP/PS
construction, in-place update, and the property accessors used by the
discretized wellbore models and isentropic-efficiency pump/compressor
calcs. Extend as additional components need more CoolProp input pairs
(PQ, QT, ...).

Every CoolProp failure is wrapped as ``CoolPropError`` (see ``core/errors.py``)
so callers can identify a property-lookup failure without parsing traceback
strings or catching CoolProp's own exception type directly.
"""

from __future__ import annotations

import enum

import CoolProp

from tango.core.errors import CoolPropError


class CoolPropBackend(enum.StrEnum):
    """Selects which CoolProp equation-of-state backend tango uses for fluid property lookups.

    **YAML field:** ``common.coolprop_backend`` (defaults to ``HEOS`` if
    omitted — see ``BICUBIC_HEOS``'s docstring for why the faster tabular
    backend is not the default).
    """

    BICUBIC_HEOS = "BICUBIC&HEOS"
    """BICUBIC-tabulated HEOS: interpolates properties from a table instead of
    solving the equation of state, roughly halving CoolProp call time versus
    raw HEOS, with ~3e-5 relative error away from phase boundaries. Not the
    default because its (P, T) lookups are unreliable near phase boundaries,
    and TESPy trusts them without checking:

    - Near the critical point the table cells are coarse (CoolProp's docs
      cite ~14 K cell width for CO2): a fixed 315 K CO2 target solved to
      ~305.3 K at a nearby operating point.
    - Just below saturation, a (P, T) flash can return an enthalpy on the
      wrong side of the saturation curve. For R245fa 1 K below saturation it
      returns 343.7 kJ/kg at 0.14 MPa and 257.5 kJ/kg at 0.145 MPa against
      the exact 229.6 and 230.8 kJ/kg, so a ``subcooling_K`` condenser outlet
      comes out as a two-phase mixture and its pump compresses wet vapor,
      while the TESPy solve still reports convergence. Errors depend on where
      the pressure falls in the table, so a pressure that works says nothing
      about its neighbors.

    Use only for a system known to stay well away from phase boundaries,
    after checking its results against ``HEOS``."""

    HEOS = "HEOS"
    """Raw (non-tabulated) HEOS — solves the actual equation of state
    directly, no interpolation-table error, at roughly 1.4-2.2x the runtime
    of ``BICUBIC_HEOS`` for the templates. Default."""


COOLPROP_BACKEND = CoolPropBackend.HEOS
"""Default CoolProp backend for ``common.coolprop_backend`` (see
``core/specs.py``'s ``Common`` model) when a YAML config doesn't set it
explicitly. Anywhere else a fluid backend needs naming explicitly (e.g.
TESPy's ``Connection.set_attr(fluid=...)`` in ``components/surface/graph.py``)
should read it from ``common.coolprop_backend``, not this constant directly,
so a config's override is actually honored."""


class FluidState:
    """Wraps a CoolProp ``AbstractState`` for one fluid, at a configurable backend."""

    def __init__(self, fluid_name: str, backend: str = COOLPROP_BACKEND) -> None:
        """Construct an uninitialized state for ``fluid_name``; call an update_*/with_* method next."""
        self.fluid_name = fluid_name
        self.backend = backend
        try:
            self._state = CoolProp.AbstractState(backend, fluid_name)
        except ValueError as exc:
            raise CoolPropError("""Fluid state instantiation error""") from exc

    @staticmethod
    def with_PT(fluid_name: str, P: float, T: float, backend: str = COOLPROP_BACKEND) -> FluidState:
        """Construct a FluidState from pressure (Pa) and temperature (K)."""
        fs = FluidState(fluid_name, backend)
        fs.update_PT(P, T)
        return fs

    @staticmethod
    def with_HP(fluid_name: str, H: float, P: float, backend: str = COOLPROP_BACKEND) -> FluidState:
        """Construct a FluidState from specific enthalpy (J/kg) and pressure (Pa)."""
        fs = FluidState(fluid_name, backend)
        fs.update_HP(H, P)
        return fs

    @staticmethod
    def with_PS(fluid_name: str, P: float, S: float, backend: str = COOLPROP_BACKEND) -> FluidState:
        """Construct a FluidState from pressure (Pa) and specific entropy (J/(kg·K)).

        Used for isentropic-efficiency pump/compressor models: the isentropic
        outlet state at a target pressure, given the inlet state's entropy.
        """
        fs = FluidState(fluid_name, backend)
        fs.update_PS(P, S)
        return fs

    @staticmethod
    def with_PQ(fluid_name: str, P: float, Q: float, backend: str = COOLPROP_BACKEND) -> FluidState:
        """Construct a saturated FluidState from pressure (Pa) and vapor mass fraction ``Q`` (0 = liquid, 1 = vapor)."""
        fs = FluidState(fluid_name, backend)
        fs.update_PQ(P, Q)
        return fs

    @staticmethod
    def copy(other: FluidState) -> FluidState:
        """Construct a new FluidState with the same fluid, backend, and (P, T) as ``other``."""
        return FluidState.with_PT(other.fluid_name, other.P, other.T, other.backend)

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

    def update_PQ(self, P: float, Q: float) -> None:
        """Update this state in place to saturation at pressure (Pa), with vapor mass fraction ``Q``."""
        try:
            self._state.update(CoolProp.PQ_INPUTS, P, Q)
        except ValueError as exc:
            raise CoolPropError(
                f"updatePQ(P={P:.6g} Pa, Q={Q:.6g}) failed for {self.fluid_name}: {exc}",
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

    @property
    def T_critical(self) -> float:
        """Critical temperature (K) of the fluid."""
        return self._state.T_critical()

    def saturation_pressure(self, T: float) -> float:
        """Saturation (bubble-point) pressure (Pa) at temperature ``T``, below the critical temperature."""
        sat = CoolProp.AbstractState(self.backend, self.fluid_name)
        try:
            sat.update(CoolProp.QT_INPUTS, 0.0, T)
        except ValueError as exc:
            raise CoolPropError(
                f"saturation pressure lookup failed for {self.fluid_name} at T={T} K",
            ) from exc
        return sat.p()

    @property
    def is_two_phase(self) -> bool:
        """Whether the state lies inside the vapor-liquid dome (0 < quality < 1)."""
        return self._state.phase() == CoolProp.iphase_twophase
