"""SystemBCIteration — convergence-loop orchestrator for tango.

Auto-selected when sim_config.injection_mode is present in the input file.

━━━ What this solver is doing ━━━

Each timestep solves the closed circuit (injection well -> reservoir or
loop -> production well(s) -> surface -> back to the injection well) at a
fixed mass rate and injection wellhead pressure, both from the config. The
circuit's one unknown is the injection temperature/enthalpy: the surface
plant's outlet becomes the injection well's inlet, so
``_converge_injection_enthalpy`` re-solves the circuit until that enthalpy
stops moving.

Two independent sub-problems — do not conflate:

1. **Injection enthalpy (this loop)** — converges the surface outlet's
   enthalpy fed back into the injection well.
2. **Production pump (inner loop, inside the production well)** — finds the
   pump pressure rise needed to lift the produced fluid to
   ``target_extraction_P`` at the surface inlet.

``MANUAL_FRACKING_CHECK`` then compares the solved state against both
fracking limit, by pressure and by flow (see ``InjectionPolicy``), and raises
``FrackingViolationError`` on a violation; ``MANUAL`` doesn't check. There
is no mode that adjusts pressure or flow toward a fracking threshold:
finding a good operating point is an optimization question (LCOE vs.
power), answered by the ``opt_*`` applications with fracking as a search
constraint. See ``InjectionPolicy`` (``tango.core.policies``).

━━━ Planned: inner pump loop ━━━

The old BC_calculator had a hardcoded 5-iteration loop for pump_dp with a
``d(P_out)/d(P_in) ≈ 1`` assumption and silent failure on phase-boundary
crossings.  Replace with a convergence-based loop::

    for pump_iter in range(MAX_PUMP_ITER):  # MAX_PUMP_ITER = 50
        try:
            pump.solve(inlet_P=prod_well.outlet_P + pump_dp, ...)
        except SaturationError:
            pump_dp += (target - pump.outlet_P)
            continue  # also halve step on boundary-crossing
        dp_error = target - pump.outlet_P
        if abs(dp_error) / target < PUMP_TOLERANCE:
            break
        pump_dp += dp_error
    else:
        raise ConvergenceError(...)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from tango.components.reservoir.base import ReservoirComponent
from tango.components.surface.base import SurfaceComponent
from tango.components.well.base import WellComponent
from tango.components.well.numerical import NumericalInjectionWell
from tango.core import fluid_utils
from tango.core.accelerators import aitken_relax
from tango.core.constants import PA_TO_MPA, W_TO_MW
from tango.core.errors import ConfigError, ConvergenceError, CoolPropError, FrackingViolationError
from tango.core.fluid_state import FluidState
from tango.core.policies import InjectionPolicy
from tango.core.stream import Stream
from tango.orchestrators.system_direct import SystemDirect

if TYPE_CHECKING:
    from tango.components.economic.base import EconomicComponent
    from tango.core.component import FlowComponent

logger = logging.getLogger(__name__)


# Inner injection-enthalpy convergence tolerance: an ABSOLUTE change in the
# surface outlet's specific enthalpy between iterations. Absolute, not
# relative, because h's zero point is an arbitrary reference state that
# differs between fluids. Enthalpy, not temperature, because near a fluid's
# critical point T can stop moving while h is still off by kJ/kg.
_DH_SURFACE_TOL: float = 1_000.0  # J/kg
_INJECTION_T_FLOOR = 275  # K reset for an injection temperature that drops below freezing point. although this is very unlikely to happen

# Default for max_inner_iterations (see SystemBCIteration.__init__).
DEFAULT_MAX_INNER_ITER: int = 20


class SystemBCIteration(SystemDirect):
    """Convergence-loop orchestrator for injection-pressure BC iteration.

    Subclasses ``SystemDirect``, reusing its component ordering/wiring
    (``self._ordered``, ``_pending_inlets``/``_record_outlet``/``_next_inlet``)
    as the building block.
    Each timestep runs an injection-enthalpy convergence loop
    (``_converge_injection_enthalpy``) that re-solves the whole circuit every
    iteration; ``MANUAL_FRACKING_CHECK`` then checks the result against both
    fracking limit. The choice between ``SystemDirect`` and this class is a topology
    question (does this graph declare a circuit with a BC variable to solve
    for at all), not a duplicate encoding of policy.

    Components are executed in ascending ``component_idx`` order each
    iteration. The injection well (idx 0) is solved first; the circuit
    continues through reservoir → production wells → surface → back to
    injection well.

    Args:
        components: Named components keyed by YAML name.
        n_tsteps: Total number of simulation timesteps.
        dt_years: Duration of each timestep (years).
        mass_rate: Mass flow rate (kg/s) — from ``sim_config.mass_rate``, used
            every timestep.
        bc_checkpoint_idx: ``component_idx`` of the boundary-condition
            checkpoint component (the surface) — from
            ``sim_config.bc_checkpoint_idx``. Used to look up the surface via
            ``_find_surface()`` for circuit-seeding and convergence checks.
        policy: Injection control policy (default ``MANUAL``).
        max_inner_iterations: Maximum iterations for the injection-
            temperature convergence loop (``_converge_injection_enthalpy``, used by
            ``MANUAL``/``MANUAL_FRACKING_CHECK``). Raises ``ConvergenceError``
            if exhausted without converging.
        economic: Optional economic component — see ``SystemDirect.__init__``.

    """

    def __init__(
        self,
        components: dict[str, FlowComponent],
        n_tsteps: int,
        dt_years: float,
        mass_rate: float,
        bc_checkpoint_idx: int,
        policy: InjectionPolicy = InjectionPolicy.MANUAL,
        max_inner_iterations: int = DEFAULT_MAX_INNER_ITER,
        economic: EconomicComponent | None = None,
    ) -> None:
        """Initialize the base single-pass engine, then store BC-specific state.

        See the class docstring for the meaning of each argument.

        Args:
            components: Named components keyed by YAML name.
            n_tsteps: Total number of simulation timesteps.
            dt_years: Duration of each timestep (years).
            mass_rate: Mass flow rate (kg/s).
            bc_checkpoint_idx: ``component_idx`` of the boundary-condition
                checkpoint component (the surface).
            policy: Injection control policy.
            max_inner_iterations: Maximum iterations for the injection-
                temperature convergence loop.
            economic: Optional economic component — see ``SystemDirect.__init__``.

        """
        super().__init__(components, n_tsteps=n_tsteps, economic=economic)
        self.dt_years = dt_years
        self.mass_rate = mass_rate
        self.bc_checkpoint_idx = bc_checkpoint_idx
        self.policy = policy
        self.max_inner_iterations = max_inner_iterations

    def _find_surface(self) -> SurfaceComponent | None:
        """Return the BC-checkpoint component (surface), or None if absent."""
        component = self._by_idx.get(self.bc_checkpoint_idx)
        if component is None or not isinstance(component, SurfaceComponent):
            return None
        return component

    def _find_reservoir(self) -> ReservoirComponent | None:
        """Return the circuit's reservoir component, or None if absent.

        Duck-typed via ``isinstance`` against the abstract ``ReservoirComponent``
        base, same pattern as ``_find_surface`` — works for any concrete
        reservoir type (today just ``LumpedReservoir``), not one hardcoded
        class. A topology with no reservoir at all (e.g. AGS's closed loop)
        legitimately has no fracking physics to check; callers must treat
        ``None`` as "nothing to check," not an error.
        """
        for component in self._ordered:
            if isinstance(component, ReservoirComponent):
                return component
        return None

    def _find_injection_well(self) -> NumericalInjectionWell | None:
        """Return the circuit's reservoir component, or None if absent.

        Duck-typed via ``isinstance`` against the abstract ``NumericalInjectionWell``
        base, same pattern as ``_find_surface`` — NOTE: works for NumeircalInjectionWell only.
        """
        for component in self._ordered:
            if isinstance(component, NumericalInjectionWell):
                return component

        return None

    def _check_fracking(self, reservoir: ReservoirComponent, inj_well: WellComponent) -> None:
        """Raise ``FrackingViolationError`` if the reservoir's fracking limit is exceeded, by pressure or by flow.

        Checks the limit both ways (see ``InjectionPolicy``'s class
        docstring): pressure-induced (``inj_well.outlet.P`` vs.
        ``fluid_utils.target_reservoir_pressure()``) and flow-induced
        (``self.mass_rate`` vs. ``fluid_utils.fracking_flow()``). Called
        against whatever state the circuit is in *right now* — callers are
        responsible for calling this only once a pass has actually been
        solved (``inj_well.outlet`` populated).

        Args:
            reservoir: The circuit's reservoir component.
            inj_well: The circuit's injection well (``component_idx == 0``).

        Raises:
            FrackingViolationError: If the limit is exceeded either way.

        """
        inj_outlet_P = inj_well.outlet.P.get_fresh()
        p_res_in_no_frack = fluid_utils.target_reservoir_pressure(
            reservoir.hydro_static_pressure,
            reservoir.over_pressure_percentage,
        )
        if p_res_in_no_frack < inj_outlet_P:
            raise FrackingViolationError(
                f"Pressure-induced fracking: injection well outlet pressure "
                f"({inj_outlet_P * PA_TO_MPA:.4g} MPa) exceeds the reservoir "
                f"fracking threshold ({p_res_in_no_frack * PA_TO_MPA:.4g} MPa).",
            )

        well_spacing = getattr(reservoir, "well_spacing", None)
        fluid_name = getattr(getattr(inj_well, "common", None), "fluid_name", None)
        backend = getattr(getattr(inj_well, "common", None), "coolprop_backend", None)
        if well_spacing is None or fluid_name is None or backend is None:
            # No known way to compute the flow-induced threshold for this
            # reservoir/well combination — skip rather than guess. Every
            # concrete reservoir type today (LumpedReservoir) declares
            # well_spacing, and every concrete well type declares common.
            return
        inj_outlet_state = FluidState.with_HP(
            fluid_name,
            inj_well.outlet.h.get_fresh(),
            inj_outlet_P,
            backend,
        )
        max_flow = fluid_utils.fracking_flow(
            thickness=reservoir.thickness,
            permeability=reservoir.permeability,
            hydro_static_pressure=reservoir.hydro_static_pressure,
            over_pressure_percentage=reservoir.over_pressure_percentage,
            well_spacing=well_spacing,
            wellbore_diameter=inj_well.diameter,
            mu=inj_outlet_state.mu,
            rho=inj_outlet_state.rho,
        )
        if self.mass_rate > max_flow:
            raise FrackingViolationError(
                f"Flow-induced fracking: mass rate ({self.mass_rate:.3g} kg/s) exceeds "
                f"the reservoir fracking threshold ({max_flow:.3g} kg/s).",
            )

    def _seed_circuit_inlet(self) -> None:
        """Seed the circuit-first component's inlet on the very first timestep.

        The circuit is cut at the injection well (component_idx=0), which reads
        from the previous timestep's surface outlet.  On the very first pass
        there is no prior surface outlet, so we pre-populate
        ``self._pending_inlets[0]`` with cold injection conditions derived
        from the surface config.

        Injection well is solved first, and on timestep 0 the surface outlet
        has not yet been computed, so the cold initial guess is used.

        Guarded by ``0 not in self._pending_inlets`` — component_idx 0 gets an
        entry either from this seed (once, ever) or from the circuit's own
        wraparound wiring (every pass thereafter, via ``_record_outlet``);
        this checks which of those has already happened, replacing the old
        stored-field design's ``inj_well.inlet.mass_rate == 0.0`` heuristic
        (fragile — a real mass rate could coincidentally be 0.0) with an
        exact "has this ever been wired" check.
        """
        surface = self._find_surface()

        if 0 in self._pending_inlets:
            return
        inj_well = self._by_idx.get(0)
        if inj_well is None:
            return

        T = surface.common.surface_temperature if surface is not None else 280

        P = (
            getattr(surface, "injection_pressure", surface.common.surface_pressure)
            if surface is not None
            else 950_000  # NOTE: arbitrary default surface pressure Pa
        )
        # The configured cold-start condition is a temperature; convert it to
        # the stream's enthalpy once, here, with the circuit fluid's own backend.
        common = surface.common if surface is not None else inj_well.common  # type: ignore[attr-defined]
        h = FluidState.with_PT(common.fluid_name, P, T, common.coolprop_backend).H
        self._pending_inlets[0] = Stream.fresh(h=h, P=P, mass_rate=self.mass_rate)

    def _set_circuit_entry_enthalpy(self, h: float) -> None:
        """Overwrite ``self._pending_inlets[0]``'s enthalpy, preserving P/mass rate.

        This is how the injection-enthalpy loop hands its next guess to the
        injection well: the well's ``solve()`` reads its inlet from this
        stream, so a guess written anywhere else never reaches it.
        """
        current = self._pending_inlets.get(0, Stream.fresh())
        self._pending_inlets[0] = Stream.fresh(
            h=h,
            P=current.P.get_fresh(),
            mass_rate=current.mass_rate.get_fresh(),
        )

    def _set_circuit_entry_mass_rate(self, mass_rate: float) -> None:
        """Overwrite ``self._pending_inlets[0]``'s mass rate, preserving h/P.

        Used everywhere the old stored-field design did
        ``inj_well.inlet.mass_rate = value`` directly: h/P for
        component_idx 0 come from the circuit's own wraparound wiring (the
        surface's outlet, via ``_record_outlet``) or the initial cold-start
        seed — never reassigned here — while mass rate is independently
        pinned to the configured operating value every timestep.
        """
        current = self._pending_inlets.get(0, Stream.fresh())
        self._pending_inlets[0] = Stream.fresh(
            h=current.h.get_fresh(),
            P=current.P.get_fresh(),
            mass_rate=mass_rate,
        )

    # ------------------------------------------------------------------
    # Timestep execution
    # ------------------------------------------------------------------

    def run_timestep(self, t: int) -> None:
        """Execute one timestep according to ``self.policy``.

        Args:
            t: Zero-based timestep index.

        Raises:
            ConfigError: If the circuit has no injection well.
            FrackingViolationError: If the fracking limit is exceeded
                (``MANUAL_FRACKING_CHECK`` only).

        """
        from tango.components.well.base import WellComponent  # noqa: PLC0415

        self._seed_circuit_inlet()
        surface: SurfaceComponent | None = self._find_surface()
        inj_well = self._find_injection_well()

        if inj_well is None:
            raise ConfigError("""Need an injection well to converge injection temperature""")

        if inj_well is not None:
            self._set_circuit_entry_mass_rate(self.mass_rate)

        # Snapshot every component's convergence-sensitive state (see
        # Component.snapshot_convergence_state's docstring) as it stood
        # at the end of the PREVIOUS calendar timestep, before this
        # timestep solves anything. Every iteration below restores this
        # SAME snapshot first, so every re-solve attempt asks the same
        # question — "given last timestep's real state, what does this
        # timestep look like with THIS iteration's injection-T guess" —
        # rather than accumulating across attempts.
        snapshot = {c.component_idx: c.snapshot_convergence_state() for c in self._ordered}

        if surface is not None:
            try:
                self._converge_injection_enthalpy(inj_well, surface, snapshot)
            except CoolPropError as exc:
                raise CoolPropError(f"""
Iteration: {t}
Time: {t * self.dt_years} years
{exc}
                                    """) from exc

        if self.policy == InjectionPolicy.MANUAL_FRACKING_CHECK:
            # Single pass already ran above (same as MANUAL) — check both
            # fracking directions against the result. No pre-emptive
            # correction: a violation raises, it does not get nudged
            # back under the threshold and silently re-solved (see
            # FrackingViolationError's docstring).
            reservoir = self._find_reservoir()
            if reservoir is not None and isinstance(inj_well, WellComponent):
                self._check_fracking(reservoir, inj_well)

    def _converge_injection_enthalpy(
        self,
        inj_well: WellComponent,
        surface: FlowComponent,
        snapshot: dict[int, Any],
    ) -> None:
        """Converge the injection enthalpy, re-solving the whole circuit every iteration.

        Every component in the circuit — reservoir included, no exceptions —
        is restored to its end-of-previous-timestep snapshot and genuinely
        re-solved on every iteration. This matters physically: the
        reservoir's real output
        (via the production wellhead) does reach back to influence the
        converged injection state. The condenser branch's own outlet
        state (T/P/enthalpy) is pinned, but the mass flow through it is
        not — the separator's flash fraction depends on the actual
        wellhead-fed inlet enthalpy, so both branches carry wellhead
        effects into the merge (the liquid branch through its state, the
        condenser branch through its mass weight).

        Each iteration: restore every component from ``snapshot`` (so this
        iteration starts from "state as committed at the end of the
        previous timestep," not from whatever the last iteration left
        behind), solve the whole circuit in order, wire streams as usual.
        The injection well solves from its inlet stream
        (``self._pending_inlets[0]``): the previous timestep's surface
        outlet on the first iteration, then the Aitken-relaxed guess. The
        loop is converged once the surface outlet ``h`` differs by less than
        ``_DH_SURFACE_TOL`` from the enthalpy the injection well actually
        solved from, so the committed iteration closes the loop to within
        that tolerance.

        Args:
            inj_well: Injection well (``component_idx == 0``).
            surface: Surface component (last in solve order).
            snapshot: Per-``component_idx`` result of
                ``Component.snapshot_convergence_state()``, captured once
                before this loop starts.

        Raises:
            ConvergenceError: If ``self.max_inner_iterations`` is exhausted
                without the injection enthalpy settling within
                ``_DH_SURFACE_TOL``. Not converging is treated as a hard
                failure, not a warning — silently continuing on an
                unconverged state would let a physically-inconsistent
                timestep pass as if it were a real answer.

        """
        r_prev = None
        delta_prev = None
        # The enthalpy the injection well solves from on this iteration.
        h_inj_used: float = self._next_inlet(inj_well).h.get_fresh()

        for inner_iter in range(self.max_inner_iterations):
            retry_below_freezing = False
            for component in self._ordered:
                component.restore_convergence_state(snapshot[component.component_idx])
                component.mark_all_stale()
                try:
                    outlet = component.solve(self._next_inlet(component))
                except CoolPropError as exc:
                    if "Tmelt" in str(exc):
                        logger.warning(
                            "Converge Injection Enthalpy Iteration %d: injection-h guess "
                            "%.1f J/kg drove %s below water's freezing point; resetting "
                            "to the enthalpy at %.1f K and retrying.",
                            inner_iter,
                            h_inj_used,
                            component.__class__.__name__,
                            _INJECTION_T_FLOOR,
                        )
                        retry_below_freezing = True
                        common = inj_well.common  # type: ignore[attr-defined]
                        h_inj_used = FluidState.with_PT(
                            common.fluid_name,
                            self._next_inlet(inj_well).P.get_fresh(),
                            _INJECTION_T_FLOOR,
                            common.coolprop_backend,
                        ).H
                        self._set_circuit_entry_enthalpy(h_inj_used)
                        # The reset is a jump, not a relaxation step, so the
                        # residual and factor from before it would give Aitken
                        # a meaningless secant; restart its history instead.
                        r_prev = None
                        delta_prev = None
                        break

                    raise CoolPropError(f"""
                    Component: {component.__class__.__name__}
                    Component Index: {component.component_idx}
                    Converge Injection Enthalpy Iteration: {inner_iter}
                    {exc}
                    """) from exc

                self._record_outlet(component, outlet)

            if retry_below_freezing:
                continue

            h_surface_out = surface.outlet.h.get_fresh()
            if abs(h_surface_out - h_inj_used) < _DH_SURFACE_TOL:
                logger.debug(
                    "h-convergence finished: inner iter %d, h_inj =%.1f J/kg, dh=%.1f J/kg",
                    inner_iter + 1,  # e.g. print 1 when `inner_iter` is 0
                    h_surface_out,
                    abs(h_surface_out - h_inj_used),
                )
                return None

            # _record_outlet has already wired the surface outlet into the
            # injection well's inlet; replace its h with the relaxed guess.
            h_inj_used, r_prev, delta_prev = aitken_relax(
                iteration=inner_iter,
                x_tilde=h_surface_out,
                x_prev=h_inj_used,
                r_prev=r_prev,
                delta_prev=delta_prev,
            )
            self._set_circuit_entry_enthalpy(h_inj_used)

        else:
            raise ConvergenceError(
                f"h-convergence: max inner iterations ({self.max_inner_iterations}) "
                f"reached without convergence (final dh="
                f"{abs(surface.outlet.h.get_fresh() - h_inj_used):.1f} "
                f"J/kg > tol={_DH_SURFACE_TOL:.1f} J/kg)",
            )

    def _after_timestep(self, t: int) -> None:
        """Log a one-line per-timestep summary; called by the inherited ``run()`` loop."""
        self._log_timestep_summary(t)

    def run(self) -> None:
        """Execute the full simulation (all timesteps).

        Logs a startup line, then delegates the timestep loop to
        ``SystemDirect.run()`` (inherited), which calls ``_after_timestep``
        for the per-timestep summary.
        """
        logger.info(
            "SystemBCIteration: %d timesteps × %.2g yr, mass_rate=%.1f kg/s",
            self.n_tsteps,
            self.dt_years,
            self.mass_rate,
        )
        super().run()

    def _log_timestep_summary(self, t: int) -> None:
        """Emit a one-line INFO summary for a completed timestep.

        Duck-typed against ``surface.state`` rather than a specific concrete
        class — ``SurfaceComponent`` doesn't mandate a state shape, so this
        degrades gracefully (NaN) for any surface type missing one of these
        fields instead of hardcoding a class-specific isinstance check.
        """
        surface = self._find_surface()
        if surface is None:
            return
        state = getattr(surface, "state", None)
        net_power = getattr(state, "net_power_W", None)
        net_thermal = getattr(state, "net_thermal_W", None)
        p_outlet = getattr(state, "P_outlet", None)
        t_inlet = getattr(state, "T_inlet", None)
        power_mw = net_power.get_fresh() * W_TO_MW if net_power is not None else float("nan")
        thermal_mw = net_thermal.get_fresh() * W_TO_MW if net_thermal is not None else float("nan")
        P_inj = p_outlet.get_fresh() if p_outlet is not None else float("nan")
        # T_prod: the production T arriving at the surface — read from the
        # surface's OWN state.T_inlet (derived from the arriving inlet's (h, P),
        # see FlowComponent.solve()'s docstring), not a `surface.inlet` field —
        # `inlet` is no longer a stored Component field.
        T_prod = t_inlet.get_fresh() if t_inlet is not None else float("nan")
        logger.info(
            "t=%3d | T_prod=%.1f K | P_inj=%.4g MPa | net_power=%.3f MW | net_thermal=%.3f MW",
            t,
            T_prod,
            P_inj * PA_TO_MPA,
            power_mw,
            thermal_mw,
        )
