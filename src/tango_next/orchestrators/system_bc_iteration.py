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

━━━ Phase 1 status — placeholder only ━━━

Phase 1 ``SingleFlashSurface.solve()`` sets ``outlet.P = self._injection_pressure``
(the current BC guess), so the loop trivially converges in 1 iteration because
``test_p`` never changes.  The BC machinery is correct in structure but not yet
driven by real physics.

━━━ Phase 2 tasks ━━━

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

━━━ Inner pump loop (Phase 2) ━━━

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
from typing import TYPE_CHECKING

from tango_next.core.policies import InjectionPolicy
from tango_next.orchestrators.system_direct import SystemDirect

if TYPE_CHECKING:
    from tango_next.components.surface.single_flash import SingleFlashSurface
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

    Subclasses ``SystemDirect``, reusing its single-circuit-pass
    ``run_timestep`` (inherited, then called via ``super()``) as the building
    block: single-pass policies (``MANUAL``, ``MANUAL_FRACING_CHECK``) call it
    once per timestep; iterative policies (``AUTO_*``) will call it repeatedly
    inside an outer Newton-step loop (Phase 2 — not yet implemented).
    ``InjectionPolicy`` is the sole authority over how many passes a timestep
    takes; the choice between ``SystemDirect`` and ``SystemBCIteration`` is a
    topology question (does this graph declare a circuit with a BC variable to
    solve for at all), not a duplicate encoding of policy.

    Components are executed in ascending ``component_idx`` order each pass.
    The injection well (idx 0) is solved first; the circuit continues
    through reservoir → production wells → surface → back to injection well.

    Args:
        components: Named components keyed by YAML name.
        n_tsteps: Total number of simulation timesteps.
        dt_years: Duration of each timestep (years).
        mass_rate: Mass flow rate (kg/s) — from ``sim_config.mass_rate``.
            Ignored (pass ``0.0``) for ``AUTO_FLOW`` / ``AUTO_BOTH``, where the
            solver computes mass rate from ``fracing_flow()`` each pass.
        fluid_name: CoolProp fluid name (e.g. ``"Water"``).
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
        fluid_name: str,
        policy: InjectionPolicy = InjectionPolicy.MANUAL,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> None:
        """Initialise the base single-pass engine, then BC-specific state."""
        super().__init__(components, n_tsteps=n_tsteps)
        self.dt_years = dt_years
        self.mass_rate = mass_rate
        self.fluid_name = fluid_name
        self.policy = policy
        self.max_iterations = max_iterations
        self.tolerance = tolerance

    def _find_surface(self) -> SingleFlashSurface | None:
        """Return the SingleFlashSurface component, or None if absent."""
        from tango_next.components.surface.single_flash import SingleFlashSurface  # noqa: PLC0415

        return next(
            (c for c in self._ordered if isinstance(c, SingleFlashSurface)),
            None,
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
                inj_well.inlet.T = surface.surface_temperature
                inj_well.inlet.P = getattr(surface, "injection_pressure", surface.surface_pressure)
            inj_well.inlet.mass_rate = self.mass_rate
            inj_well.inlet.fluid_name = self.fluid_name

    # ------------------------------------------------------------------
    # Timestep execution
    # ------------------------------------------------------------------

    def run_timestep(self, t: int) -> None:
        """Execute one timestep according to ``self.policy``.

        Args:
            t: Zero-based timestep index.

        Raises:
            NotImplementedError: For any policy not yet implemented.
            ConvergenceError: (AUTO_* modes, Phase 2) if convergence is not reached.

        """
        self._seed_circuit_inlet()
        surface: SingleFlashSurface | None = self._find_surface()
        inj_well = self._by_idx.get(0)
        if inj_well is not None:
            inj_well.inlet.mass_rate = self.mass_rate
            inj_well.inlet.fluid_name = self.fluid_name

        if self.policy == InjectionPolicy.MANUAL:
            # Save t_d_old for all numerical wells BEFORE the first pass so that
            # each inner-loop well solve advances t_d by exactly one del_t (not
            # multiple times).  Must capture the pre-pass values here.
            t_d_old_saved: dict[int, float] = {
                c.component_idx: c.t_d_old for c in self._ordered if hasattr(c, "t_d_old")
            }

            # Save reservoir energy_extracted BEFORE the main pass.  The main pass
            # runs the reservoir with the cold circuit-seed injection T (288 K), which
            # over-extracts energy.  After T-convergence we re-run the reservoir with
            # the converged injection T starting from this saved baseline.
            reservoir = next(
                (c for c in self._ordered if hasattr(c, "energy_extracted")),
                None,
            )
            energy_before = reservoir.energy_extracted if reservoir is not None else 0.0

            super().run_timestep(t)  # first full circuit pass

            if surface is not None:
                logger.info(
                    "t=%3d  MANUAL single pass  P_inj=%.4g Pa",
                    t,
                    surface.outlet.P,
                )

            # Inner injection-temperature convergence loop (Phase 1).
            # Mirrors old tango's update() which iterates injection_well →
            # production_wells → surface until dT_surface < 0.5 K.  The
            # reservoir is skipped inside the inner loop; it is re-run once
            # after convergence in Phase 2 with the corrected injection T.
            if surface is not None:
                self._converge_injection_T(surface, t_d_old_saved, reservoir, energy_before)

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
        t_d_old_saved: dict[int, float],
        reservoir: Component | None,
        energy_before: float,
    ) -> None:
        """Converge injection temperature then correct reservoir energy extraction.

        Two-phase operation that mirrors old tango's per-timestep inner loop:

        **Phase 1 — T-convergence** (inner loop):
        Iterates inj_well → prod_lower → prod_upper → surface until the
        injection temperature (surface outlet) changes by less than
        ``_DT_SURFACE_TOL``.  The reservoir is skipped each iteration (its
        outlet is frozen at the main-pass value) so it does not accumulate
        energy multiple times.

        **Phase 2 — reservoir correction**:
        After T-convergence, the injection well outlet carries the converged
        injection temperature.  The reservoir is re-run once from ``energy_before``
        (its pre-timestep value) using this converged injection T.  This matches
        old tango's ``old + delta`` energy pattern, where only the *last*
        intra-timestep call's delta is preserved.  Downstream components
        (prod_lower, prod_upper, surface) are then re-solved once more so the
        final recorded state is self-consistent.

        ``t_d_old`` is restored for every numerical well before each solve so
        that the Adams 2015 heat-loss time only advances by one ``del_t`` per
        outer timestep, regardless of how many inner iterations are needed.

        Args:
            surface: Surface component (last in solve order).
            t_d_old_saved: Pre-first-pass ``t_d_old`` snapshot for every
                component that has that attribute (numerical wells only).
            reservoir: Reservoir component (has ``energy_extracted``), or None.
            energy_before: ``reservoir.energy_extracted`` value captured before
                the main circuit pass.  Used to reset and re-apply a single
                correct delta in Phase 2.

        """
        if reservoir is None:
            return

        # Save reservoir outlet so it can be wired to its downstream neighbour
        # on each inner iteration (bypassing the un-solved reservoir).
        res_next_idx: int | None = getattr(reservoir, "next", None)
        res_downstream: Component | None = (
            self._by_idx.get(res_next_idx) if res_next_idx is not None else None
        )
        res_T = reservoir.outlet.T
        res_P = reservoir.outlet.P
        res_mdot = reservoir.outlet.mass_rate
        res_rho = reservoir.outlet.rho
        res_mu = reservoir.outlet.mu
        res_fluid = reservoir.outlet.fluid_name

        T_inj_prev = surface.outlet.T

        for inner_iter in range(_MAX_INNER_ITER):
            for component in self._ordered:
                if component is reservoir:
                    # Wire saved outlet to the downstream component instead of
                    # re-solving the reservoir.
                    if res_downstream is not None:
                        dst = res_downstream.inlet
                        dst.T = res_T
                        dst.P = res_P
                        dst.mass_rate = res_mdot
                        dst.rho = res_rho
                        dst.mu = res_mu
                        dst.fluid_name = res_fluid
                    continue  # skip solve() and _wire_one_stream()

                # Restore t_d_old so heat-loss time advances only once per outer
                # timestep, not once per inner iteration.
                if component.component_idx in t_d_old_saved:
                    component.t_d_old = t_d_old_saved[component.component_idx]

                component.solve()
                self._wire_one_stream(component)

            T_inj_new = surface.outlet.T
            if abs(T_inj_new - T_inj_prev) < _DT_SURFACE_TOL:
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
                abs(surface.outlet.T - T_inj_prev),
                _DT_SURFACE_TOL,
            )

        # ── Phase 2: reservoir correction ────────────────────────────────────
        # After T-convergence the injection well outlet carries the converged
        # injection temperature.  _wire_one_stream(injection_well) inside the
        # last inner iteration has already propagated that outlet to
        # reservoir.inlet.  Re-run the reservoir from energy_before so that
        # energy_extracted reflects the converged injection T (matches old
        # tango's "old + delta" pattern where only the last intra-timestep
        # call's delta is kept).  Then re-run the downstream components once
        # so the final recorded state is self-consistent with the corrected
        # reservoir outlet T.
        reservoir.energy_extracted = energy_before
        reservoir.solve()
        self._wire_one_stream(reservoir)

        for component in self._ordered:
            if component.component_idx <= reservoir.component_idx:
                continue  # injection_well and reservoir already done
            if component.component_idx in t_d_old_saved:
                component.t_d_old = t_d_old_saved[component.component_idx]
            component.solve()
            self._wire_one_stream(component)

    def _after_timestep(self, t: int) -> None:
        """Log a one-line per-timestep summary; called by the inherited ``run()`` loop."""
        self._log_timestep_summary(t)

    def run(self) -> None:
        """Execute the full simulation (all timesteps).

        Logs a startup line, then delegates the timestep loop to
        ``SystemDirect.run()`` (inherited), which calls ``_after_timestep``
        for the per-timestep summary.
        """
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
        """Emit a one-line INFO summary for a completed timestep."""
        surface = self._find_surface()
        if surface is None:
            return
        from tango_next.components.surface.single_flash import SingleFlashSurface  # noqa: PLC0415

        if isinstance(surface, SingleFlashSurface):
            gross_mw = surface.state.gross_power_watts / 1e6
            P_inj = surface.state.P_outlet
            T_prod = surface.inlet.T
            logger.info(
                "t=%3d | T_prod=%.1f K | P_inj=%.4g MPa | gross_power=%.3f MW",
                t,
                T_prod,
                P_inj / 1e6,
                gross_mw,
            )
