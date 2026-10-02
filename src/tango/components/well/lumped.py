"""Lumped-parameter wellbore components for tango.

LumpedInjectionWell and LumpedProductionWell model a single-segment wellbore
as a 1-D pipe with:
  - Darcy–Weisbach frictional pressure drop
  - Hydrostatic pressure change (positive going down, negative going up)
  - Linear geothermal temperature profile (no wellbore heat-transfer model)

LumpedProductionWellWithPump adds a pump pressure boost at the wellhead.

**Design intent**: The ``Lumped*`` prefix marks 0-D / lumped-parameter models.
These are permanent optional variants to be kept alongside higher-fidelity
numerical-integration models once those are implemented.  Do NOT deprecate or
remove them when adding e.g. ``NumericalInjectionWell``.

Simplified-physics TODOs are marked throughout; upgrade path for each is noted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import Field

from tango.components.well.base import WellComponent
from tango.core.errors import InvalidPowerStateError
from tango.core.fluid_state import FluidState
from tango.core.fluid_utils import (
    fluid_density,
    fluid_viscosity,
    friction_factor_darcy,
    hydrostatic_pressure,
    mean_velocity,
    pressure_drop_friction,
    reynolds_number,
)
from tango.core.locked_state import LockedState
from tango.core.numerics import PUMP_BOOST_MAX_ITER, PUMP_BOOST_TOL_PA, secant_solve
from tango.core.specs import Common
from tango.core.state_methods import StateMethods
from tango.core.stream import Stream

# ---------------------------------------------------------------------------
# State dataclasses
# ---------------------------------------------------------------------------


def _ls(v: float = float("nan")) -> LockedState[float]:
    """Convenience: LockedState[float] starting stale with value ``v``."""
    ls: LockedState[float] = LockedState(v)
    ls.mark_stale()
    return ls


@dataclass(frozen=True)
class WellboreState(StateMethods):
    """Full simulation state for one wellbore solve step.

    All fields are ``LockedState[float]`` so that each is writable exactly once
    per timestep.  The dataclass is ``frozen=True`` to prevent replacing the
    wrapper objects themselves (the LockedState invariant is enforced on the
    value inside).  ``mark_all_stale()`` (inherited from ``StateMethods``) is
    called by the orchestrator (via ``Component.mark_all_stale()``)
    immediately before each ``solve()`` to open the write slot for the new
    timestep.
    """

    h_inlet: LockedState[float] = field(default_factory=_ls)
    T_inlet: LockedState[float] = field(default_factory=_ls)
    """Derived from (``h_inlet``, ``P_inlet``); this model's own physics works in temperature."""
    P_inlet: LockedState[float] = field(default_factory=_ls)
    mass_rate: LockedState[float] = field(default_factory=_ls)
    rho: LockedState[float] = field(default_factory=_ls)
    mu: LockedState[float] = field(default_factory=_ls)
    velocity: LockedState[float] = field(default_factory=_ls)
    Re: LockedState[float] = field(default_factory=_ls)
    friction_factor: LockedState[float] = field(default_factory=_ls)
    delta_p_friction: LockedState[float] = field(default_factory=_ls)
    delta_p_hydrostatic: LockedState[float] = field(default_factory=_ls)
    h_outlet: LockedState[float] = field(default_factory=_ls)
    """Derived from (``T_outlet``, ``P_outlet``) -- what ``outlet`` carries."""
    T_outlet: LockedState[float] = field(default_factory=_ls)
    P_outlet: LockedState[float] = field(default_factory=_ls)


@dataclass(frozen=True)
class ProductionWellWithPumpState(WellboreState):
    """Wellbore state extended with pump data for LumpedProductionWellWithPump."""

    pump_delta_p: LockedState[float] = field(default_factory=_ls)
    pump_power_watts: LockedState[float] = field(default_factory=_ls)


# ---------------------------------------------------------------------------
# History dataclasses
# ---------------------------------------------------------------------------


@dataclass
class WellboreHistory:
    """Per-timestep history of scalar wellbore state (inlet → outlet).

    One list field per ``WellboreState`` attribute (TANGO Commandment: every
    ``*State`` attribute must have an analog in its ``*History`` class) —
    see ``record()``.
    """

    h_inlet: list[float] = field(default_factory=list)
    h_outlet: list[float] = field(default_factory=list)
    T_inlet: list[float] = field(default_factory=list)
    T_outlet: list[float] = field(default_factory=list)
    P_inlet: list[float] = field(default_factory=list)
    P_outlet: list[float] = field(default_factory=list)
    mass_rate: list[float] = field(default_factory=list)
    rho: list[float] = field(default_factory=list)
    mu: list[float] = field(default_factory=list)
    velocity: list[float] = field(default_factory=list)
    Re: list[float] = field(default_factory=list)  # noqa: N815
    friction_factor: list[float] = field(default_factory=list)
    delta_p_friction: list[float] = field(default_factory=list)
    delta_p_hydrostatic: list[float] = field(default_factory=list)

    def record(self, state: WellboreState) -> None:
        """Append one timestep snapshot."""
        self.h_inlet.append(state.h_inlet.get_fresh())
        self.h_outlet.append(state.h_outlet.get_fresh())
        self.T_inlet.append(state.T_inlet.get_fresh())
        self.T_outlet.append(state.T_outlet.get_fresh())
        self.P_inlet.append(state.P_inlet.get_fresh())
        self.P_outlet.append(state.P_outlet.get_fresh())
        self.mass_rate.append(state.mass_rate.get_fresh())
        self.rho.append(state.rho.get_fresh())
        self.mu.append(state.mu.get_fresh())
        self.velocity.append(state.velocity.get_fresh())
        self.Re.append(state.Re.get_fresh())
        self.friction_factor.append(state.friction_factor.get_fresh())
        self.delta_p_friction.append(state.delta_p_friction.get_fresh())
        self.delta_p_hydrostatic.append(state.delta_p_hydrostatic.get_fresh())


@dataclass
class ProductionWellWithPumpHistory(WellboreHistory):
    """Extends WellboreHistory with pump data for LumpedProductionWellWithPump."""

    pump_delta_p: list[float] = field(default_factory=list)
    pump_power_watts: list[float] = field(default_factory=list)

    def record(self, state: WellboreState) -> None:
        """Append one timestep snapshot, including pump data."""
        super().record(state)
        pump_state = state if isinstance(state, ProductionWellWithPumpState) else None
        self.pump_delta_p.append(pump_state.pump_delta_p.get_fresh() if pump_state else 0.0)
        self.pump_power_watts.append(pump_state.pump_power_watts.get_fresh() if pump_state else 0.0)


def _temperature(common: Common, h: float, P: float) -> float:
    """Temperature (K) at (h [J/kg], P [Pa]) -- these lumped models work in temperature internally."""
    return FluidState.with_HP(common.fluid_name, h, P, common.coolprop_backend).T


def _enthalpy(common: Common, P: float, T: float) -> float:
    """Specific enthalpy (J/kg) at (P [Pa], T [K]), for the ``outlet`` stream."""
    return FluidState.with_PT(common.fluid_name, P, T, common.coolprop_backend).H


# ---------------------------------------------------------------------------
# LumpedInjectionWell
# ---------------------------------------------------------------------------


class LumpedInjectionWell(WellComponent):
    """Single-segment injection wellbore: surface → reservoir bottom.

    Simplified physics:
    - P_bottom = P_top + ρ·g·depth − ΔP_friction      (down → +hydrostatic)
    - T_bottom = T_top  + thermal_gradient · depth     (linear geotherm)

    TODO: replace linear T profile with transient conductive model.
    TODO: replace constant ρ, μ with CoolProp lookups.
    """

    common: Common = Field(frozen=True)
    """Shared fluid/rock parameters — a reference to the SAME Common
    instance every other component in the Workflow holds, not an
    independent copy. See core/specs.py."""

    state: WellboreState = Field(default_factory=WellboreState)
    history: WellboreHistory = Field(default_factory=WellboreHistory)

    def solve(self, inlet: Stream) -> None:
        """Compute bottom-hole T and P from surface injection conditions."""
        s = self.state

        s.h_inlet.update(inlet.h.get_fresh())
        s.P_inlet.update(inlet.P.get_fresh())
        s.T_inlet.update(_temperature(self.common, s.h_inlet.get_fresh(), s.P_inlet.get_fresh()))
        s.mass_rate.update(inlet.mass_rate.get_fresh())

        rho = fluid_density(
            self.common.fluid_name,
            s.T_inlet.get_fresh(),
            s.P_inlet.get_fresh(),
            self.common.coolprop_backend,
        )
        mu = fluid_viscosity(
            self.common.fluid_name,
            s.T_inlet.get_fresh(),
            s.P_inlet.get_fresh(),
            self.common.coolprop_backend,
        )
        s.rho.update(rho)
        s.mu.update(mu)

        vel = mean_velocity(s.mass_rate.get_fresh(), rho, self.diameter)
        re = reynolds_number(s.mass_rate.get_fresh(), self.diameter, mu)
        ff = friction_factor_darcy(re, self.diameter, self.pipe_roughness)
        dp_f = pressure_drop_friction(ff, self.well_length, self.diameter, rho, vel)
        dp_h = hydrostatic_pressure(rho, self.well_length, self.gravity)
        s.velocity.update(vel)
        s.Re.update(re)
        s.friction_factor.update(ff)
        s.delta_p_friction.update(dp_f)
        s.delta_p_hydrostatic.update(dp_h)

        s.P_outlet.update(s.P_inlet.get_fresh() + dp_h - dp_f)
        s.T_outlet.update(s.T_inlet.get_fresh() + self.common.thermal_gradient * self.well_length)

        s.h_outlet.update(_enthalpy(self.common, s.P_outlet.get_fresh(), s.T_outlet.get_fresh()))
        self.outlet.h.update(s.h_outlet.get_fresh())
        self.outlet.P.update(s.P_outlet.get_fresh())
        self.outlet.mass_rate.update(s.mass_rate.get_fresh())


# ---------------------------------------------------------------------------
# LumpedProductionWell
# ---------------------------------------------------------------------------


class LumpedProductionWell(WellComponent):
    """Single-segment production wellbore: reservoir bottom → surface.

    Simplified physics:
    - P_top = P_bottom − ρ·g·depth − ΔP_friction   (up → −hydrostatic)
    - T_top = T_inlet   (perfectly insulated — a more detailed thermal model is future work)

    TODO: implement Zhang et al. (2011) transient conduction model.
    TODO: replace constant ρ, μ with CoolProp lookups.
    """

    common: Common = Field(frozen=True)
    """Shared fluid/rock parameters — a reference to the SAME Common
    instance every other component in the Workflow holds, not an
    independent copy. See core/specs.py."""

    state: WellboreState = Field(default_factory=WellboreState)
    history: WellboreHistory = Field(default_factory=WellboreHistory)

    def solve(self, inlet: Stream) -> None:
        """Compute wellhead T and P from reservoir outlet conditions."""
        s = self.state

        s.h_inlet.update(inlet.h.get_fresh())
        s.P_inlet.update(inlet.P.get_fresh())
        s.T_inlet.update(_temperature(self.common, s.h_inlet.get_fresh(), s.P_inlet.get_fresh()))
        s.mass_rate.update(inlet.mass_rate.get_fresh())

        rho = fluid_density(
            self.common.fluid_name,
            s.T_inlet.get_fresh(),
            s.P_inlet.get_fresh(),
            self.common.coolprop_backend,
        )
        mu = fluid_viscosity(
            self.common.fluid_name,
            s.T_inlet.get_fresh(),
            s.P_inlet.get_fresh(),
            self.common.coolprop_backend,
        )
        s.rho.update(rho)
        s.mu.update(mu)

        vel = mean_velocity(s.mass_rate.get_fresh(), rho, self.diameter)
        re = reynolds_number(s.mass_rate.get_fresh(), self.diameter, mu)
        ff = friction_factor_darcy(re, self.diameter, self.pipe_roughness)
        dp_f = pressure_drop_friction(ff, self.well_length, self.diameter, rho, vel)
        dp_h = hydrostatic_pressure(rho, self.well_length, self.gravity)
        s.velocity.update(vel)
        s.Re.update(re)
        s.friction_factor.update(ff)
        s.delta_p_friction.update(dp_f)
        s.delta_p_hydrostatic.update(dp_h)

        s.P_outlet.update(s.P_inlet.get_fresh() - dp_h - dp_f)
        s.T_outlet.update(
            s.T_inlet.get_fresh(),
        )  # perfectly insulated; TODO: transient wellbore heat-loss model (candidate: Zhang 2011)

        s.h_outlet.update(_enthalpy(self.common, s.P_outlet.get_fresh(), s.T_outlet.get_fresh()))
        self.outlet.h.update(s.h_outlet.get_fresh())
        self.outlet.P.update(s.P_outlet.get_fresh())
        self.outlet.mass_rate.update(s.mass_rate.get_fresh())


# ---------------------------------------------------------------------------
# LumpedProductionWellWithPump
# ---------------------------------------------------------------------------


class LumpedProductionWellWithPump(WellComponent):
    """Upper production wellbore segment with an optional pump.

    TODO: replace with TESPy Compressor or explicit pump curve.
    TODO: track pump electricity consumption in EconomicComponent.
    Assumptions:
        - All of the pump's losses heat the produced fluid. The actual
          enthalpy rise is the isentropic rise divided by
          ``pump_efficiency``, and the pump's electricity draw is
          ``mass_rate`` times that same rise. This is right for losses in
          the pump and its fluid-cooled downhole motor. It is not quite right
          when ``pump_efficiency`` is an overall pump-string figure that also
          covers surface equipment (cable, transformer, frequency
          converter), whose losses heat the surroundings rather than the
          fluid: the electricity draw is still correct, but the discharge
          enthalpy is slightly overstated (about 1 kJ/kg for a 50 bar boost
          of hot brine at an overall efficiency of 0.55).
    """

    common: Common = Field(frozen=True)
    """Shared fluid/rock parameters — a reference to the SAME Common
    instance every other component in the Workflow holds, not an
    independent copy. See core/specs.py."""
    pump_efficiency: float = Field(default=1.0, frozen=True)
    """Pump efficiency (dimensionless): the isentropic enthalpy rise divided by
    the actual one, which is also the electricity drawn per unit mass. Defaults
    to 1.0 (ideal pump). The example configs use **0.55**, the overall
    electric submersible pump (ESP) string efficiency of van 't Spijker &
    Ungemach (2016) (see ``docs/SOURCES.md#vantspijker2016``): pump 70% ×
    motor 90% × cable 97% × transformer 99% × frequency converter 94%. The
    overall figure is used, not the 70% pump-only one, because downhole pump
    power is billed as electricity drawn at the surface. See the class's
    Assumptions section for what this means for the fluid's enthalpy, and
    ``solve()``'s docstring for the pump model this scales."""
    target_extraction_pressure: float = Field(default=0.0, frozen=True)
    """Target outlet pressure from the pump (Pa). 0 means no active pump.
    Sourced from ``sim_config.target_extraction_pressure`` — the SAME
    single value ``SurfaceComponent`` uses, threaded in by
    ``_build_components`` (see that field's docstring in ``core/specs.py``
    for the duplicated-value bug this replaced)."""

    state: ProductionWellWithPumpState = Field(default_factory=ProductionWellWithPumpState)
    history: ProductionWellWithPumpHistory = Field(default_factory=ProductionWellWithPumpHistory)

    def _wellbore_losses(self, mdot: float, P_start: float, T_start: float) -> tuple[float, ...]:
        """Pure calc: friction + hydrostatic loss over this segment from a given starting state.

        No state writes — used both for the natural (no-pump) case and for
        every trial evaluation inside the pump-boost search in ``solve()``.

        Returns:
            ``(P_outlet, rho, mu, vel, re, ff, dp_f, dp_h)``.

        """
        rho = fluid_density(self.common.fluid_name, T_start, P_start, self.common.coolprop_backend)
        mu = fluid_viscosity(self.common.fluid_name, T_start, P_start, self.common.coolprop_backend)
        vel = mean_velocity(mdot, rho, self.diameter)
        re = reynolds_number(mdot, self.diameter, mu)
        ff = friction_factor_darcy(re, self.diameter, self.pipe_roughness)
        dp_f = pressure_drop_friction(ff, self.well_length, self.diameter, rho, vel)
        dp_h = hydrostatic_pressure(rho, self.well_length, self.gravity)
        P_outlet = P_start - dp_h - dp_f
        return P_outlet, rho, mu, vel, re, ff, dp_f, dp_h

    def solve(self, inlet: Stream) -> None:
        """Compute wellhead T and P including wellbore losses and pump boost.

        If a pump boost is needed, the boosted pump-discharge pressure is
        found by iterating (Secant method) rather than applied as a
        closed-form correction tacked onto the natural (un-boosted) result:
        this segment's OWN friction/hydrostatic loss depends on fluid
        density, which in turn depends on the (boosted) pressure — a
        genuine fixed-point problem, not a one-shot calculation.

        Pump work uses a standard isentropic-efficiency model (entropy at
        the true inlet state, isentropic enthalpy at the candidate discharge
        pressure, efficiency-derated to get the actual enthalpy rise, then
        flashed back to temperature) rather than assuming the compression
        is perfectly isothermal. The isothermal/isentropic gap is driven by
        TEMPERATURE, not pressure level or pressure-rise size:
        ``dH|_S - dH|_T = T*alpha*V*dP``, where ``alpha`` is the fluid's
        thermal expansion coefficient. Because ``alpha`` grows as
        temperature rises toward the fluid's own critical point, the same
        pressure boost applied at a higher temperature produces a larger
        isothermal/isentropic divergence than the identical boost applied
        near ambient temperature — the effect is set by how warm the fluid
        runs relative to its own critical point, not by the absolute
        pressure level.
        """
        s = self.state

        s.h_inlet.update(inlet.h.get_fresh())
        s.P_inlet.update(inlet.P.get_fresh())
        s.T_inlet.update(_temperature(self.common, s.h_inlet.get_fresh(), s.P_inlet.get_fresh()))
        s.mass_rate.update(inlet.mass_rate.get_fresh())

        T_in = s.T_inlet.get_fresh()
        P_in = s.P_inlet.get_fresh()
        mdot = s.mass_rate.get_fresh()

        P_after_natural, rho_n, mu_n, vel_n, re_n, ff_n, dp_f_n, dp_h_n = self._wellbore_losses(
            mdot,
            P_in,
            T_in,
        )
        target_Pa = self.target_extraction_pressure

        if target_Pa <= P_after_natural:
            s.rho.update(rho_n)
            s.mu.update(mu_n)
            s.velocity.update(vel_n)
            s.Re.update(re_n)
            s.friction_factor.update(ff_n)
            s.delta_p_friction.update(dp_f_n)
            s.delta_p_hydrostatic.update(dp_h_n)
            s.pump_delta_p.update(0.0)
            s.pump_power_watts.update(0.0)
            s.P_outlet.update(P_after_natural)
            s.T_outlet.update(T_in)  # simplified: insulated, no pump-induced T rise modeled yet
            s.h_outlet.update(_enthalpy(self.common, P_after_natural, T_in))

            self.outlet.h.update(s.h_outlet.get_fresh())
            self.outlet.P.update(P_after_natural)
            self.outlet.mass_rate.update(mdot)
            return

        before = FluidState.with_HP(
            self.common.fluid_name,
            s.h_inlet.get_fresh(),
            P_in,
            self.common.coolprop_backend,
        )

        def _discharge_state(P_pump_out: float) -> tuple[float, float]:
            """Isentropic-efficiency pump model: (P_pump_out) -> (h_actual, T_pump_out)."""
            h_isentropic = FluidState.with_PS(
                self.common.fluid_name,
                P_pump_out,
                before.S,
                self.common.coolprop_backend,
            ).H
            h_actual = before.H + (h_isentropic - before.H) / self.pump_efficiency
            t_pump_out = FluidState.with_HP(
                self.common.fluid_name,
                h_actual,
                P_pump_out,
                self.common.coolprop_backend,
            ).T
            return h_actual, t_pump_out

        def _residual(P_pump_out: float) -> float:
            _, t_pump_out = _discharge_state(P_pump_out)
            p_outlet, *_ = self._wellbore_losses(mdot, P_pump_out, t_pump_out)
            return p_outlet - target_Pa

        P_pump_out = secant_solve(
            _residual,
            x0=P_in,
            x1=P_in + (target_Pa - P_after_natural),
            tol=PUMP_BOOST_TOL_PA,
            max_iter=PUMP_BOOST_MAX_ITER,
            error_context=f"well component_idx={self.component_idx}: pump-boost pressure convergence",
        )
        h_actual, T_pump_out = _discharge_state(P_pump_out)
        P_outlet, rho, mu, vel, re, ff, dp_f, dp_h = self._wellbore_losses(mdot, P_pump_out, T_pump_out)

        pump_pwr = mdot * (h_actual - before.H)
        if pump_pwr < 0:
            raise InvalidPowerStateError(
                f"well component_idx={self.component_idx}: pump_power_watts={pump_pwr:.1f} W "
                f"is negative despite boosting to P_pump_out={P_pump_out:.1f} Pa (target "
                f"P_outlet={target_Pa:.1f} Pa) -- a passive pump cannot report negative power "
                "draw. This happens when the isentropic enthalpy rise used for pump work goes "
                "negative even though pressure increases (dH/dP|_S can be negative for a liquid "
                "whose thermal expansivity term dominates).",
            )

        s.rho.update(rho)
        s.mu.update(mu)
        s.velocity.update(vel)
        s.Re.update(re)
        s.friction_factor.update(ff)
        s.delta_p_friction.update(dp_f)
        s.delta_p_hydrostatic.update(dp_h)
        s.pump_delta_p.update(P_pump_out - P_in)
        s.pump_power_watts.update(pump_pwr)
        s.P_outlet.update(P_outlet)
        s.T_outlet.update(T_pump_out)
        s.h_outlet.update(_enthalpy(self.common, P_outlet, T_pump_out))

        self.outlet.h.update(s.h_outlet.get_fresh())
        self.outlet.P.update(P_outlet)
        self.outlet.mass_rate.update(mdot)
