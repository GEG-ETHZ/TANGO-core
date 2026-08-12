"""SystemBCIteration — convergence-loop orchestrator for tango_next.

Auto-selected when sim_config.injection_mode is present in the input file.

━━━ What this solver is doing ━━━

The BC variable is ``p_inj_wellhead_no_frack`` — the injection wellhead
pressure (Pa) whose current best estimate, once it propagates through
hydrostatic head and friction losses down the injection well, lands the
reservoir inlet exactly at the fracking-safety ceiling (not above it, and
not needlessly below it either). The physical question: *what injection
wellhead pressure is required so that the fluid arrives at the reservoir
inlet at the target pressure?*

Target reservoir inlet pressure::

    target_reservoir_P = hydrostatic_pressure × (1 + overpressure_pct / 100)

Update rule (explicit Newton step on the mismatch at the reservoir inlet)::

    p_inj_wellhead_no_frack += target_reservoir_P − inj_well.outlet.P

Outer convergence criterion (relative, must ALL be satisfied)::

    |p_inj_wellhead_no_frack[N] − p_inj_wellhead_no_frack[N-1]|
        / p_inj_wellhead_no_frack[N-1]                      < tolerance
    |mass_rate[N] − mass_rate[N-1]| / mass_rate[N-1]   < tolerance   (AUTO_FLOW / AUTO_BOTH)
    |inj_well.inlet.P[N] − inj_well.inlet.P[N-1]| / …  < tolerance

``MANUAL`` and ``MANUAL_FRACKING_CHECK`` modes do a single pass (no outer loop).
``AUTO_PRESSURE`` / ``AUTO_FLOW`` / ``AUTO_BOTH`` iterate until all criteria are met.
See ``InjectionPolicy`` (``tango_next.core.policies``, vision doc §BC iteration mode).

━━━ Two independent sub-problems — do not conflate ━━━

1. **Injection BC (this outer loop)** — finds injection wellhead pressure.
   Convergence target: ``inj_well.outlet.P ≈ target_reservoir_P``.
   The surface inlet pressure is fixed externally at ``target_extraction_P``
   by the production pump (below) and does NOT participate in this loop.

2. **Production pump (inner loop, inside ④)** — finds pump ΔP needed to
   lift the produced fluid to ``target_extraction_P`` at the surface inlet.
   This sub-problem is independent of the injection BC; it runs once per
   outer iteration and reaches its own convergence before the outer loop
   checks its criterion.

━━━ Status — AUTO_PRESSURE/AUTO_FLOW implemented, AUTO_BOTH not yet ━━━

``AUTO_PRESSURE`` (``_converge_injection_pressure``) drives the update rule
above by writing ``surface.injection_pressure`` directly — a plain field
already declared on the abstract ``SurfaceComponent`` base specifically for
this ("Updated in-place by SystemBCIteration each convergence pass" — see
``components/surface/base.py``). This is the same mechanism ``MANUAL``/
``MANUAL_FRACKING_CHECK`` already solve through (``GraphSurface.solve()``
always pins its TESPy outlet connection's pressure to whatever
``injection_pressure`` currently holds); ``AUTO_PRESSURE`` just writes a new
value each outer iteration instead of leaving it at its YAML-configured
initial guess forever, and re-solves to T-convergence
(``_converge_injection_T``) after each pressure update. No topology- or
component-type-specific wiring is needed: ``surface.outlet`` -> ``inj_well.
inlet`` propagation already happens generically via ``_wire_one_stream``.

The one non-obvious requirement: each outer iteration must take a *fresh*
``snapshot_convergence_state()`` **after** writing ``injection_pressure``,
not once for the whole outer loop. ``injection_pressure`` is an ordinary
declared field, so it is itself captured/restored by
``_converge_injection_T``'s inner-loop snapshot/restore — a single upfront
snapshot would have the inner loop silently reset it back to its original
value on the very first inner iteration, and the outer loop's pressure
update would never actually reach the circuit. See
``_converge_injection_pressure``'s docstring for the full mechanism and how
this was confirmed.

``AUTO_FLOW`` (``_converge_injection_flow``) mirrors this but as a
fixed-point (Picard) iteration, not a Newton step: each pass recomputes
``fracking_flow()`` from the current solved outlet state and feeds it
straight back in as the next ``self.mass_rate`` (optionally capped at
``self.max_mass_rate``, mirroring old tango's field of the same name),
since ``fracking_flow()`` already IS the target value rather than a
correction toward it. No re-snapshot-per-iteration gotcha here — mass rate
is conserved through the whole circuit each pass (unlike pressure, which
only converges once BOTH branches around the plant's merge node happen to
agree), so it never gets silently reset by ``_converge_injection_T``'s
inner-loop restore. The gotcha here is different: a near-zero initial mass
rate makes the injection well's numerical model degenerate (division by
mass rate), producing a wild first ``fracking_flow()`` estimate that
overshoots past what the circuit can solve from a cold start — this is WHY
``sim_config.mass_rate`` is a required, physically-reasonable initial guess
for ``AUTO_FLOW``/``AUTO_BOTH`` too, not the ``0.0`` placeholder this used
to default to. See ``_converge_injection_flow``'s docstring for the full
mechanism and how this was confirmed.

``MANUAL_FRACKING_CHECK`` does NOT iterate ``p_inj_wellhead_no_frack`` at all
(single pass, same as ``MANUAL``, then ``_check_fracking`` compares the
solved result against both thresholds and raises ``FrackingViolationError``
on violation, with no pre-emptive correction of either value — see
``FrackingViolationError``'s docstring for the rationale). ``AUTO_PRESSURE``/
``AUTO_FLOW`` each also call ``_check_fracking`` once, after outer
convergence — each loop drives ITS OWN side to (approximately) the
threshold by construction, but the OTHER variable is user-fixed under that
policy and is not otherwise checked, so both directions still need the
same explicit check as a safety net.

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

from tango_next.core import fluid_utils
from tango_next.core.constants import PA_TO_MPA, W_TO_MW
from tango_next.core.errors import ConfigError, ConvergenceError, FrackingViolationError
from tango_next.core.policies import InjectionPolicy
from tango_next.orchestrators.system_direct import SystemDirect

if TYPE_CHECKING:
    from tango_next.components.economic.base import EconomicComponent
    from tango_next.components.reservoir.base import ReservoirComponent
    from tango_next.components.surface.base import SurfaceComponent
    from tango_next.components.well.base import WellComponent
    from tango_next.core.component import Component

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITER_NO_FRACK: int = 200
DEFAULT_TOLERANCE: float = 1e-4

# Inner injection-temperature convergence tolerance — must match old tango's
# CONVERGENCE_CRITERIA["dT_surface"] = 0.5 K.
_DT_SURFACE_TOL: float = 0.5  # K

# Default for max_inner_iterations (see SystemBCIteration.__init__) — must
# match old tango's MAX_NUM_ITR = 20.
DEFAULT_MAX_INNER_ITER: int = 20


class SystemBCIteration(SystemDirect):
    """Convergence-loop orchestrator for injection-pressure BC iteration.

    Subclasses ``SystemDirect``, reusing its component ordering/wiring
    (``self._ordered``, ``_wire_one_stream``) as the building block.
    ``MANUAL``/``MANUAL_FRACKING_CHECK`` drive a temperature-convergence loop
    (``_converge_injection_T``) that re-solves the whole circuit every
    iteration; iterative pressure policies (``AUTO_*``) will additionally
    wrap that in an outer Newton-step loop (not yet implemented).
    ``InjectionPolicy`` is the sole authority over how many passes a timestep
    takes; the choice between ``SystemDirect`` and ``SystemBCIteration`` is a
    topology question (does this graph declare a circuit with a BC variable to
    solve for at all), not a duplicate encoding of policy.

    Components are executed in ascending ``component_idx`` order each
    iteration. The injection well (idx 0) is solved first; the circuit
    continues through reservoir → production wells → surface → back to
    injection well.

    Args:
        components: Named components keyed by YAML name.
        n_tsteps: Total number of simulation timesteps.
        dt_years: Duration of each timestep (years).
        mass_rate: Mass flow rate (kg/s) — from ``sim_config.mass_rate``. For
            ``MANUAL``/``MANUAL_FRACKING_CHECK``/``AUTO_PRESSURE`` this is
            the fixed value used every timestep. For ``AUTO_FLOW``/
            ``AUTO_BOTH`` it is instead the INITIAL GUESS for the Picard
            iteration that converges ``mass_rate = fracking_flow()`` each
            pass — do not pass ``0.0`` or another near-zero value for those
            two policies (see ``_converge_injection_flow``'s docstring).
        bc_checkpoint_idx: ``component_idx`` of the boundary-condition
            checkpoint component (the surface) — from
            ``sim_config.bc_checkpoint_idx``. Used to look up the surface via
            ``_find_surface()`` for circuit-seeding and convergence checks.
        policy: Injection control policy (default ``MANUAL``).
        max_iter_no_frack: Maximum BC iterations per timestep (AUTO_* modes only).
        tolerance: Relative convergence tolerance on injection pressure.
        max_inner_iterations: Maximum iterations for the injection-
            temperature convergence loop (``_converge_injection_T``, used by
            ``MANUAL``/``MANUAL_FRACKING_CHECK``). Raises ``ConvergenceError``
            if exhausted without converging.
        max_mass_rate: Optional cap (kg/s) on the mass rate ``AUTO_FLOW``/
            ``AUTO_BOTH``'s Picard iteration converges to — from
            ``sim_config.max_mass_rate``. ``None`` (default) means uncapped.
            Meaningless for every other policy.
        economic: Optional economic component — see ``SystemDirect.__init__``.

    """

    def __init__(
        self,
        components: dict[str, Component],
        n_tsteps: int,
        dt_years: float,
        mass_rate: float,
        bc_checkpoint_idx: int,
        policy: InjectionPolicy = InjectionPolicy.MANUAL,
        max_iter_no_frack: int = DEFAULT_MAX_ITER_NO_FRACK,
        tolerance: float = DEFAULT_TOLERANCE,
        max_inner_iterations: int = DEFAULT_MAX_INNER_ITER,
        max_mass_rate: float | None = None,
        economic: EconomicComponent | None = None,
    ) -> None:
        """Initialise the base single-pass engine, then store BC-specific state.

        See the class docstring for the meaning of each argument.

        Args:
            components: Named components keyed by YAML name.
            n_tsteps: Total number of simulation timesteps.
            dt_years: Duration of each timestep (years).
            mass_rate: Mass flow rate (kg/s), or its initial guess.
            bc_checkpoint_idx: ``component_idx`` of the boundary-condition
                checkpoint component (the surface).
            policy: Injection control policy.
            max_iter_no_frack: Maximum BC iterations per timestep (AUTO_* modes
                only).
            tolerance: Relative convergence tolerance on injection pressure.
            max_inner_iterations: Maximum iterations for the injection-
                temperature convergence loop.
            max_mass_rate: Optional cap (kg/s) on ``AUTO_FLOW``/``AUTO_BOTH``'s
                converged mass rate.
            economic: Optional economic component — see ``SystemDirect.__init__``.

        """
        super().__init__(components, n_tsteps=n_tsteps, economic=economic)
        self.dt_years = dt_years
        self.mass_rate = mass_rate
        self.max_mass_rate = max_mass_rate
        self.bc_checkpoint_idx = bc_checkpoint_idx
        self.policy = policy
        self.max_iter_no_frack = max_iter_no_frack
        self.tolerance = tolerance
        self.max_inner_iterations = max_inner_iterations

    def _find_surface(self) -> SurfaceComponent | None:
        """Return the BC-checkpoint component (surface), or None if absent."""
        from tango_next.components.surface.base import SurfaceComponent  # noqa: PLC0415

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
        from tango_next.components.reservoir.base import ReservoirComponent  # noqa: PLC0415

        for component in self._ordered:
            if isinstance(component, ReservoirComponent):
                return component
        return None

    def _check_fracking(self, reservoir: ReservoirComponent, inj_well: WellComponent) -> None:
        """Raise ``FrackingViolationError`` if either fracking threshold is exceeded.

        Checks both independent mechanisms (see ``InjectionPolicy``'s class
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
            FrackingViolationError: If either threshold is exceeded.

        """
        p_res_in_no_frack = fluid_utils.target_reservoir_pressure(
            reservoir.hydro_static_pressure,
            reservoir.over_pressure_percentage,
        )
        if p_res_in_no_frack < inj_well.outlet.P:
            raise FrackingViolationError(
                f"Pressure-induced fracking: injection well outlet pressure "
                f"({inj_well.outlet.P * PA_TO_MPA:.4g} MPa) exceeds the reservoir "
                f"fracking threshold ({p_res_in_no_frack * PA_TO_MPA:.4g} MPa).",
            )

        well_spacing = getattr(reservoir, "well_spacing", None)
        fluid_name = getattr(getattr(inj_well, "common", None), "fluid_name", None)
        if well_spacing is None or fluid_name is None:
            # No known way to compute the flow-induced threshold for this
            # reservoir/well combination — skip rather than guess. Every
            # concrete reservoir type today (LumpedReservoir) declares
            # well_spacing, and every concrete well type declares common.
            return
        max_flow = fluid_utils.fracking_flow(
            thickness=reservoir.thickness,
            permeability=reservoir.permeability,
            hydro_static_pressure=reservoir.hydro_static_pressure,
            over_pressure_percentage=reservoir.over_pressure_percentage,
            well_spacing=well_spacing,
            wellbore_diameter=inj_well.diameter,
            mu=fluid_utils.fluid_viscosity(fluid_name, inj_well.outlet.T, inj_well.outlet.P),
            rho=fluid_utils.fluid_density(fluid_name, inj_well.outlet.T, inj_well.outlet.P),
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
        there is no prior surface outlet, so we pre-populate the injection well
        inlet with cold injection conditions derived from the surface config.

        This matches old tango's behaviour: injection well is solved first, and
        on timestep 0 the surface outlet has not yet been computed, so the cold
        initial guess is used.
        """
        inj_well = self._by_idx.get(0)
        if inj_well is None:
            return
        if inj_well.inlet.mass_rate == 0.0:
            surface = self._find_surface()
            if surface is not None:
                inj_well.inlet.T = surface.common.surface_temperature
                inj_well.inlet.P = getattr(surface, "injection_pressure", surface.common.surface_pressure)
            inj_well.inlet.mass_rate = self.mass_rate

    # ------------------------------------------------------------------
    # Timestep execution
    # ------------------------------------------------------------------

    def run_timestep(self, t: int) -> None:
        """Execute one timestep according to ``self.policy``.

        Args:
            t: Zero-based timestep index.

        Raises:
            NotImplementedError: For any policy not yet implemented.
            ConvergenceError: (AUTO_* modes, once implemented) if convergence is not reached.

        """
        from tango_next.components.well.base import WellComponent  # noqa: PLC0415

        self._seed_circuit_inlet()
        surface: SurfaceComponent | None = self._find_surface()
        inj_well = self._by_idx.get(0)
        if inj_well is not None:
            inj_well.inlet.mass_rate = self.mass_rate

        if self.policy in (InjectionPolicy.MANUAL, InjectionPolicy.MANUAL_FRACKING_CHECK):
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
                self._converge_injection_T(surface, snapshot)

            if self.policy == InjectionPolicy.MANUAL_FRACKING_CHECK:
                # Single pass already ran above (same as MANUAL) — check both
                # fracking directions against the result. No pre-emptive
                # correction: a violation raises, it does not get nudged
                # back under the threshold and silently re-solved (see
                # FrackingViolationError's docstring).
                reservoir = self._find_reservoir()
                if reservoir is not None and isinstance(inj_well, WellComponent):
                    self._check_fracking(reservoir, inj_well)

            return

        if self.policy == InjectionPolicy.AUTO_PRESSURE:
            if surface is None or not isinstance(inj_well, WellComponent):
                raise ConfigError(
                    "InjectionPolicy.AUTO_PRESSURE requires a surface (BC checkpoint) "
                    "and an injection well (component_idx 0).",
                )
            reservoir = self._find_reservoir()
            if reservoir is None:
                raise ConfigError(
                    "InjectionPolicy.AUTO_PRESSURE requires a reservoir component — "
                    "there is no fracking-safety target to converge toward without one.",
                )
            self._converge_injection_pressure(surface, inj_well, reservoir)
            self._check_fracking(reservoir, inj_well)
            return

        if self.policy == InjectionPolicy.AUTO_FLOW:
            if surface is None or not isinstance(inj_well, WellComponent):
                raise ConfigError(
                    "InjectionPolicy.AUTO_FLOW requires a surface (BC checkpoint) "
                    "and an injection well (component_idx 0).",
                )
            reservoir = self._find_reservoir()
            if reservoir is None:
                raise ConfigError(
                    "InjectionPolicy.AUTO_FLOW requires a reservoir component — "
                    "there is no fracking-flow threshold to converge toward without one.",
                )
            self._converge_injection_flow(surface, inj_well, reservoir)
            self._check_fracking(reservoir, inj_well)
            return

        # AUTO_BOTH — not yet implemented. Needs a joint update rule
        # (co-iterate p_inj_wellhead_no_frack via _converge_injection_pressure's
        # Newton step AND mass_rate via _converge_injection_flow's Picard step,
        # each pass, until both stabilize), plus — per its own enum
        # docstring — "if no feasible injection pressure exists at the target
        # flow rate, the flow rate is reduced until a feasible pressure can be
        # achieved," which is a real design question neither of the other two
        # policies needs to answer (they each hold one variable fixed).
        # Confirmed (2026-06-16) to raise NotImplementedError until that joint
        # update rule is implemented.
        #
        # This is the ONE InjectionPolicy variant with a genuine old-tango
        # analog (per the class docstring's mapping table) — worth building
        # its old-vs-new numeric parity test alongside it, unlike
        # AUTO_PRESSURE/AUTO_FLOW which have none. Confirmed by reading
        # BC_calculator.py's iterator() directly (2026-08-13): under
        # mass_rate.type == "automatic" (plain, non-Hotmaps, non-
        # controlled_power_generation branch), old tango unconditionally sets
        # mass_rate = self.fracing_flow() every pass — check_fracing does NOT
        # gate this for "automatic" (it only gates the cap for "manual"/
        # "manual_func"). Combined with test_p's Newton step running whenever
        # mass_rate.type != "manual", "automatic" ALWAYS co-drives pressure
        # AND flow simultaneously — there is no way to configure old tango to
        # iterate pressure alone with a fixed mass rate (ruling out any
        # AUTO_PRESSURE-only parity target), nor flow alone with a fixed
        # pressure (ruling out AUTO_FLOW). A separate, unconditional
        # `mass_rate >= bc_iteration["max_mass_rate"]` cap also applies AFTER
        # whichever branch computes mass_rate, regardless of type — this is
        # sim_config.max_mass_rate's real old-tango analog, distinct from
        # check_fracing's per-type cap.
        raise NotImplementedError(
            f"InjectionPolicy.{self.policy.name} requires a joint pressure/flow-rate "
            "update rule (not yet implemented).",
        )

    def _converge_injection_pressure(
        self,
        surface: SurfaceComponent,
        inj_well: WellComponent,
        reservoir: ReservoirComponent,
    ) -> None:
        """Outer Newton-step loop driving ``p_inj_wellhead_no_frack`` to the
        pressure-induced fracking threshold (``AUTO_PRESSURE`` only).

        The BC variable is fed to the circuit by writing ``surface.injection_pressure``
        directly (not by writing ``inj_well.inlet.P`` directly) — ``GraphSurface.
        solve()`` forces its TESPy outlet connection to this value, and the
        existing per-component wiring (``_wire_one_stream``) carries it from
        ``surface.outlet`` to ``inj_well.inlet`` the same way any other
        component-to-component quantity propagates. No topology- or
        component-type-specific code is needed for this to work.

        Each outer iteration re-snapshots every component's convergence state
        (see ``Component.snapshot_convergence_state``) **after** writing
        ``injection_pressure`` — this is required, not just tidy:
        ``injection_pressure`` is an ordinary declared field, so it is itself
        captured (and restored) by the snapshot/restore mechanism
        ``_converge_injection_T``'s inner loop uses every iteration. Taking one
        snapshot before the whole outer loop (as ``MANUAL``/``MANUAL_FRACKING_CHECK``
        do once per timestep) would have the inner loop's very first
        ``restore_convergence_state`` call silently reset ``injection_pressure``
        straight back to whatever it was when that single snapshot was taken —
        the outer loop would then update its own ``p_inj_wellhead_no_frack``
        variable every iteration while the circuit itself kept re-solving at the
        *original* pressure forever. Confirmed empirically (2026-08-13): with a
        single upfront snapshot, ``inj_well.outlet.P`` never moves past its
        first-iteration value no matter how many outer iterations run; with a
        fresh per-outer-iteration snapshot taken after writing
        ``injection_pressure``, the same config converges in 2-3 outer iterations.

        Args:
            surface: BC-checkpoint component (``sim_config.bc_checkpoint_idx``).
            inj_well: Injection well (``component_idx == 0``).
            reservoir: The circuit's reservoir component.

        Raises:
            ConvergenceError: If ``self.max_iter_no_frack`` outer iterations are
                exhausted without ``p_inj_wellhead_no_frack`` settling within
                ``self.tolerance`` (relative).

        """
        target_reservoir_P = fluid_utils.target_reservoir_pressure(
            reservoir.hydro_static_pressure,
            reservoir.over_pressure_percentage,
        )
        p_inj_wellhead_no_frack = surface.injection_pressure

        for bc_iter in range(self.max_iter_no_frack):
            surface.injection_pressure = p_inj_wellhead_no_frack
            snapshot = {c.component_idx: c.snapshot_convergence_state() for c in self._ordered}
            self._converge_injection_T(surface, snapshot)

            p_new = p_inj_wellhead_no_frack + (target_reservoir_P - inj_well.outlet.P)
            rel_change = abs(p_new - p_inj_wellhead_no_frack) / abs(p_inj_wellhead_no_frack)
            logger.debug(
                "AUTO_PRESSURE: outer iter %d, p_inj_wellhead_no_frack=%.6g Pa, rel_change=%.2e",
                bc_iter + 1,
                p_new,
                rel_change,
            )
            p_inj_wellhead_no_frack = p_new
            if rel_change < self.tolerance:
                break
        else:
            raise ConvergenceError(
                f"AUTO_PRESSURE: max outer iterations ({self.max_iter_no_frack}) reached "
                f"without convergence (final p_inj_wellhead_no_frack="
                f"{p_inj_wellhead_no_frack:.6g} Pa, rel_change={rel_change:.2e} > "
                f"tol={self.tolerance:.2e})",
            )

    def _converge_injection_flow(
        self,
        surface: Component,
        inj_well: WellComponent,
        reservoir: ReservoirComponent,
    ) -> None:
        """Outer Picard loop driving ``self.mass_rate`` to the flow-induced
        fracking threshold (``AUTO_FLOW`` only).

        Unlike ``_converge_injection_pressure``'s Newton step, this is a
        fixed-point (Picard) iteration: each pass, recompute
        ``fracking_flow()`` from the CURRENT solved state (``inj_well.outlet``'s
        T/P feed ``fluid_viscosity``/``fluid_density``) and feed that value
        straight back in as the next mass rate — no explicit error/residual
        term, since ``fracking_flow()`` already IS the target value, not a
        correction toward it. Optionally capped at ``self.max_mass_rate``
        (``sim_config.max_mass_rate`` — old tango's field of the same name
        and purpose) each pass, so a reservoir/well combination whose natural
        fracking-flow threshold is inconveniently high (or numerically
        unreachable — see below) can still be run at a user-chosen ceiling.

        ``self.mass_rate`` (not a snapshotted Component field) is written
        directly to ``inj_well.inlet.mass_rate`` before each
        ``_converge_injection_T`` call, same idea as ``_converge_injection_pressure``
        writing ``surface.injection_pressure`` — but simpler: mass rate is
        conserved through the whole circuit each pass (no splits/merges
        affecting the total), so unlike ``injection_pressure`` it never gets
        silently reset by ``_converge_injection_T``'s inner-loop snapshot/
        restore (``inlet`` is unconditionally excluded from that mechanism —
        see ``Component.snapshot_convergence_state``), and a single snapshot
        taken once before the whole outer loop is correct here (no
        per-outer-iteration re-snapshot needed, unlike the pressure case).

        **The initial guess (``self.mass_rate`` at call time) matters a lot,
        for a real numerical reason, confirmed empirically (2026-08-13):**
        starting from a near-zero mass rate (e.g. ``0.0``, ``1.0``) makes the
        FIRST solve degenerate (the numerical well model divides by mass
        rate in more than one place) and can produce a wildly wrong outlet
        state, whose ``fracking_flow()`` estimate then overshoots into a
        mass rate the circuit can't solve from a cold start at all
        (``CoolPropError``, unrelated to fracking — see
        ``docs/tango_next_tasks.md``'s "Production-side circuit numerically
        unstable..." open item). Starting from a physically-reasonable guess
        (e.g. the config's normal operating mass rate) avoids this: each
        Picard step is then a comparatively small perturbation, and
        ``GraphSurface``'s underlying TESPy network — a persistent,
        warm-started solver across ``solve()`` calls, not rebuilt each
        iteration — tracks the moving solution via continuation rather than
        cold-starting at each new guess. This is WHY ``sim_config.mass_rate``
        is required (not optional/defaulted) even for ``AUTO_FLOW``/
        ``AUTO_BOTH`` — see that field's docstring in ``core/specs.py``.

        Args:
            surface: BC-checkpoint component (``sim_config.bc_checkpoint_idx``).
            inj_well: Injection well (``component_idx == 0``).
            reservoir: The circuit's reservoir component.

        Raises:
            ConfigError: If the reservoir/well combination doesn't declare
                ``well_spacing``/``common.fluid_name`` — ``fracking_flow()``
                cannot be computed without them, and (unlike ``_check_fracking``'s
                optional secondary check) this policy has no meaningful
                fallback if it can't.
            ConvergenceError: If ``self.max_iter_no_frack`` outer iterations are
                exhausted without ``mass_rate`` settling within
                ``self.tolerance`` (relative).

        """
        well_spacing = getattr(reservoir, "well_spacing", None)
        fluid_name = getattr(getattr(inj_well, "common", None), "fluid_name", None)
        if well_spacing is None or fluid_name is None:
            raise ConfigError(
                "InjectionPolicy.AUTO_FLOW requires the reservoir to declare well_spacing "
                "and the injection well to declare common.fluid_name — fracking_flow() "
                "cannot be computed without them.",
            )

        snapshot = {c.component_idx: c.snapshot_convergence_state() for c in self._ordered}
        mass_rate = self.mass_rate

        for bc_iter in range(self.max_iter_no_frack):
            inj_well.inlet.mass_rate = mass_rate
            self._converge_injection_T(surface, snapshot)

            mu = fluid_utils.fluid_viscosity(fluid_name, inj_well.outlet.T, inj_well.outlet.P)
            rho = fluid_utils.fluid_density(fluid_name, inj_well.outlet.T, inj_well.outlet.P)
            new_mass_rate = fluid_utils.fracking_flow(
                thickness=reservoir.thickness,
                permeability=reservoir.permeability,
                hydro_static_pressure=reservoir.hydro_static_pressure,
                over_pressure_percentage=reservoir.over_pressure_percentage,
                well_spacing=well_spacing,
                wellbore_diameter=inj_well.diameter,
                mu=mu,
                rho=rho,
            )
            if self.max_mass_rate is not None:
                new_mass_rate = min(new_mass_rate, self.max_mass_rate)

            rel_change = abs(new_mass_rate - mass_rate) / max(abs(mass_rate), 1e-8)
            logger.debug(
                "AUTO_FLOW: outer iter %d, mass_rate=%.6g kg/s, rel_change=%.2e",
                bc_iter + 1,
                new_mass_rate,
                rel_change,
            )
            mass_rate = new_mass_rate
            if rel_change < self.tolerance:
                break
        else:
            raise ConvergenceError(
                f"AUTO_FLOW: max outer iterations ({self.max_iter_no_frack}) reached "
                f"without convergence (final mass_rate={mass_rate:.6g} kg/s, "
                f"rel_change={rel_change:.2e} > tol={self.tolerance:.2e})",
            )

        # Persist the converged value: _check_fracking (called by run_timestep
        # right after this) reads self.mass_rate, and the NEXT timestep's
        # outer loop starts from it too — a far better initial guess than
        # restarting from sim_config.mass_rate's cold value every timestep.
        self.mass_rate = mass_rate

    def _converge_injection_T(
        self,
        surface: Component,
        snapshot: dict[int, dict[str, Any]],
    ) -> None:
        """Converge injection temperature, re-solving the whole circuit every iteration.

        Every component in the circuit — reservoir included, no exceptions —
        is restored to its end-of-previous-timestep snapshot and genuinely
        re-solved on every iteration. This matters physically: the
        reservoir's real output
        (via the production wellhead) does reach back to influence the
        converged injection temperature. The condenser branch's own outlet
        state (T/P/enthalpy) is pinned, but the mass flow through it is
        not — the separator's flash fraction depends on the actual
        wellhead-fed inlet enthalpy, so both branches carry wellhead
        effects into the merge (the liquid branch through its state, the
        condenser branch through its mass weight).

        Each iteration: restore every component from ``snapshot`` (so this
        iteration starts from "state as committed at the end of the
        previous timestep," not from whatever the last iteration left
        behind), solve the whole circuit in order, wire streams as usual.
        Repeat until the injection temperature (surface outlet) changes by
        less than ``_DT_SURFACE_TOL`` between iterations. The iteration
        that satisfies convergence is already the final, committed answer.

        Args:
            surface: Surface component (last in solve order).
            snapshot: Per-``component_idx`` result of
                ``Component.snapshot_convergence_state()``, captured once
                before this loop starts.

        Raises:
            ConvergenceError: If ``self.max_inner_iterations`` is exhausted
                without the injection temperature settling within
                ``_DT_SURFACE_TOL``. Not converging is treated as a hard
                failure, not a warning — silently continuing on an
                unconverged state would let a physically-inconsistent
                timestep pass as if it were a real answer.

        """
        T_inj_prev: float | None = None

        for inner_iter in range(self.max_inner_iterations):
            for component in self._ordered:
                component.restore_convergence_state(snapshot[component.component_idx])
                component.mark_all_stale()
                component.solve()
                self._wire_one_stream(component)

            T_inj_new = surface.outlet.T
            if T_inj_prev is not None and abs(T_inj_new - T_inj_prev) < _DT_SURFACE_TOL:
                logger.debug(
                    "T-convergence: inner iter %d, dT=%.4f K",
                    inner_iter + 1,
                    abs(T_inj_new - T_inj_prev),
                )
                break
            T_inj_prev = T_inj_new
        else:
            raise ConvergenceError(
                f"T-convergence: max inner iterations ({self.max_inner_iterations}) "
                f"reached without convergence (final dT="
                f"{abs(surface.outlet.T - (T_inj_prev if T_inj_prev is not None else float('nan'))):.4f} "
                f"K > tol={_DT_SURFACE_TOL:.4f} K)",
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
        # AUTO_FLOW/AUTO_BOTH iterate mass_rate toward fracking_flow() every
        # timestep (see _converge_injection_flow) — self.mass_rate at this
        # point is only the config's initial guess, not a fixed operating
        # value, so the startup log says so explicitly rather than printing
        # a number that's about to change.
        auto_flow_modes = (InjectionPolicy.AUTO_FLOW, InjectionPolicy.AUTO_BOTH)
        if self.policy in auto_flow_modes:
            cap_repr = f", capped at {self.max_mass_rate:.1f} kg/s" if self.max_mass_rate is not None else ""
            mass_rate_repr = f"auto (fracking_flow(), initial guess {self.mass_rate:.1f} kg/s{cap_repr})"
        else:
            mass_rate_repr = f"{self.mass_rate:.1f} kg/s"
        logger.info(
            "SystemBCIteration: %d timesteps × %.2g yr, mass_rate=%s",
            self.n_tsteps,
            self.dt_years,
            mass_rate_repr,
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
        power_mw = net_power.get_fresh() * W_TO_MW if net_power is not None else float("nan")
        thermal_mw = net_thermal.get_fresh() * W_TO_MW if net_thermal is not None else float("nan")
        P_inj = p_outlet.get_fresh() if p_outlet is not None else float("nan")
        T_prod = surface.inlet.T
        logger.info(
            "t=%3d | T_prod=%.1f K | P_inj=%.4g MPa | net_power=%.3f MW | net_thermal=%.3f MW",
            t,
            T_prod,
            P_inj * PA_TO_MPA,
            power_mw,
            thermal_mw,
        )
