"""SystemBCIteration — convergence-loop orchestrator for tango_next.

Auto-selected when sim_config.injection_mode is present in the input file.

━━━ What this solver is doing ━━━

The BC variable is ``test_p`` — the injection wellhead pressure (Pa). <--- `test_p` seems like kind of a vague name (TODO: fix this line)
The physical question: *what injection wellhead pressure is required so that,
after hydrostatic head and friction losses in the injection well, the fluid
arrives at the reservoir inlet at the target pressure?*

Target reservoir inlet pressure::

    target_reservoir_P = hydrostatic_pressure × (1 + overpressure_pct / 100)

Update rule (explicit, matches src/tango/ FlowRateCalculator.iterator)::

    test_p += target_reservoir_P − inj_well.outlet.P

Outer convergence criterion (relative, must ALL be satisfied)::

    |test_p[N] − test_p[N-1]| / test_p[N-1]           < tolerance
    |mass_rate[N] − mass_rate[N-1]| / mass_rate[N-1]   < tolerance   (AUTO_FLOW / AUTO_BOTH)
    |inj_well.inlet.P[N] − inj_well.inlet.P[N-1]| / …  < tolerance

``MANUAL`` and ``MANUAL_FRACING_CHECK`` modes do a single pass (no outer loop).
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

━━━ Current status — placeholder only ━━━

Currently, the surface component's ``solve()`` (currently ``GraphSurface``) sets
``outlet.P = self.injection_pressure`` (the current BC guess), so the loop
trivially converges in 1 iteration because ``test_p`` never changes.  The BC
machinery is correct in structure but not yet driven by real physics.

━━━ Planned: real BC-iteration physics ━━━

Replace the current placeholder with the explicit update rule above.
The surface must NOT set ``outlet.P = _injection_pressure``; instead:
  - Feed ``test_p`` as ``injection_well.inlet.P`` directly (not via surface).
  - After ``injection_well.solve()``, compute the new ``test_p`` from the update rule.
  - The surface gets its inlet from the production pump outlet (fixed at
    ``target_extraction_P``) and its outlet pressure comes from TESPy pump2.

In ``MANUAL_FRACING_CHECK`` mode (src/tango/ ``type: manual, check_fracing: True``):
when ``target_reservoir_P > inj_well.outlet.P``, the update is skipped — the
reservoir inlet is below the fracing threshold, so no pressure adjustment is
needed.  This is correct behaviour.  ``test_p`` is only reduced when the initial
value drives the reservoir inlet above the fracing threshold.

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

from tango_next.core.constants import W_TO_MW
from tango_next.core.policies import InjectionPolicy
from tango_next.orchestrators.system_direct import SystemDirect

if TYPE_CHECKING:
    from tango_next.components.surface.base import SurfaceComponent
    from tango_next.core.component import Component

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS: int = 200
DEFAULT_TOLERANCE: float = 1e-4

# Inner injection-temperature convergence constants — must match old tango's
# CONVERGENCE_CRITERIA["dT_surface"] = 0.5 K and MAX_NUM_ITR = 20.
_DT_SURFACE_TOL: float = 0.5  # K
_MAX_INNER_ITER: int = 20


class SystemBCIteration(SystemDirect):
    """Convergence-loop orchestrator for injection-pressure BC iteration.

    Subclasses ``SystemDirect``, reusing its component ordering/wiring
    (``self._ordered``, ``_wire_one_stream``) as the building block.
    ``MANUAL``/``MANUAL_FRACING_CHECK`` drive a temperature-convergence loop
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
        mass_rate: Mass flow rate (kg/s) — from ``sim_config.mass_rate``.
            Ignored (pass ``0.0``) for ``AUTO_FLOW`` / ``AUTO_BOTH``, where the
            solver computes mass rate from ``fracing_flow()`` each pass.
        policy: Injection control policy (default ``MANUAL``).
        max_iterations: Maximum BC iterations per timestep (AUTO_* modes only).
        tolerance: Relative convergence tolerance on injection pressure.

    """

    def __init__(
        self,
        components: dict[str, Component],
        n_tsteps: int,
        dt_years: float,
        mass_rate: float,
        bc_checkpoint_idx: int,
        policy: InjectionPolicy = InjectionPolicy.MANUAL,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> None:
        """Initialise the base single-pass engine, then BC-specific state."""
        super().__init__(components, n_tsteps=n_tsteps)
        self.dt_years = dt_years
        self.mass_rate = mass_rate
        self.bc_checkpoint_idx = bc_checkpoint_idx
        self.policy = policy
        self.max_iterations = max_iterations
        self.tolerance = tolerance

    def _find_surface(self) -> SurfaceComponent | None:
        """Return the BC-checkpoint component (surface), or None if absent."""
        from tango_next.components.surface.base import SurfaceComponent  # noqa: PLC0415

        component = self._by_idx.get(self.bc_checkpoint_idx)
        if component is None or not isinstance(component, SurfaceComponent):
            return None
        return component

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
        self._seed_circuit_inlet()
        surface: SurfaceComponent | None = self._find_surface()
        inj_well = self._by_idx.get(0)
        if inj_well is not None:
            inj_well.inlet.mass_rate = self.mass_rate

        if self.policy == InjectionPolicy.MANUAL:
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

            return

        if self.policy == InjectionPolicy.MANUAL_FRACING_CHECK:
            # Phase 2: add fracing_flow() and threshold checks before/after the pass.
            raise NotImplementedError(
                "InjectionPolicy.MANUAL_FRACING_CHECK requires Phase 2 fracing logic "
                "(fracing_flow() Darcy calculation and reservoir threshold access).",
            )

        # AUTO_* modes — Phase 2: outer Newton-step convergence loop.
        # Sketch of the intended structure:
        #
        #   for bc_iter in range(self.max_iterations):
        #       super().run_timestep(t)  # one circuit pass, inherited from SystemDirect
        #       test_p_new = test_p_old + (target_reservoir_P - inj_well.outlet.P)
        #       if converged: break
        #   else:
        #       raise ConvergenceError(...)
        #
        # AUTO_FLOW and AUTO_BOTH also update mass_rate = fracing_flow() each pass.
        # AUTO_BOTH additionally co-iterates test_p and mass_rate jointly — confirmed
        # (2026-06-16) to raise NotImplementedError below like the other AUTO_* modes
        # until that joint update rule is implemented.
        raise NotImplementedError(
            f"InjectionPolicy.{self.policy.name} requires Phase 2 BC iteration "
            "(Newton-step pressure/flow-rate updates not yet implemented).",
        )

    def _converge_injection_T(
        self,
        surface: Component,
        snapshot: dict[int, dict[str, Any]],
    ) -> None:
        """Converge injection temperature, re-solving the whole circuit every iteration.

        Every component in the circuit — including the reservoir, which
        used to be frozen/skipped here — is restored to its
        end-of-previous-timestep snapshot and genuinely re-solved on every
        iteration. This matters physically: the reservoir's real output
        (via the production wellhead) does reach back to influence the
        converged injection temperature (through the surface plant's
        non-condenser branch merging back in), so freezing it during
        convergence was producing a self-inconsistent answer, not just an
        approximation.

        Each iteration: restore every component from ``snapshot`` (so this
        iteration starts from "state as committed at the end of the
        previous timestep," not from whatever the last iteration left
        behind), solve the whole circuit in order, wire streams as usual.
        Repeat until the injection temperature (surface outlet) changes by
        less than ``_DT_SURFACE_TOL`` between iterations. The iteration
        that satisfies convergence is already the final, committed answer —
        no separate correction pass afterward.

        Args:
            surface: Surface component (last in solve order).
            snapshot: Per-``component_idx`` result of
                ``Component.snapshot_convergence_state()``, captured once
                before this loop starts.

        """
        T_inj_prev: float | None = None

        for inner_iter in range(_MAX_INNER_ITER):
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
            logger.warning(
                "T-convergence: max inner iterations (%d) reached without convergence "
                "(final dT=%.4f K > tol=%.4f K)",
                _MAX_INNER_ITER,
                abs(surface.outlet.T - (T_inj_prev if T_inj_prev is not None else float("nan"))),
                _DT_SURFACE_TOL,
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
        # TODO: figure out what `auto_flow_modes` is doing here and comment this line accordingly
        auto_flow_modes = (InjectionPolicy.AUTO_FLOW, InjectionPolicy.AUTO_BOTH)
        mass_rate_repr = (
            "auto (fracing_flow())" if self.policy in auto_flow_modes else f"{self.mass_rate:.1f} kg/s"
        )
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
            P_inj / 1e6,
            power_mw,
            thermal_mw,
        )
