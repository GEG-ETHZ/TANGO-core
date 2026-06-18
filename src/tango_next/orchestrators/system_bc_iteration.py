"""SystemBCIteration — convergence-loop orchestrator for tango_next.

Auto-selected when sim_config.bc_iteration is present in the input file.

━━━ What this solver is doing ━━━

The BC variable is ``test_p`` — the injection wellhead pressure (Pa).
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
    The surface component (idx 0) is solved first; the circuit continues
    through injection well → reservoir → production wells → back to surface.

    Args:
        components: Named components keyed by YAML name.
        n_tsteps: Total number of simulation timesteps.
        dt_years: Duration of each timestep (years).
        mass_rate: Mass flow rate (kg/s) — from ``sim_config.mass_rate.value``.
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

    def _seed_surface_inlet(self) -> None:
        """Seed the surface component inlet from the current production state.

        On the very first iteration of timestep 0 there is no prior outlet;
        use the surface spec values as a cold-start approximation.
        """
        surface = self._by_idx.get(0)
        if surface is None:
            # No component at idx 0 — valid for wellbore-only test fixtures or
            # sub-systems without a surface plant.  Nothing to seed; the BC
            # iteration loop will also skip convergence checking in this case.
            return
        if surface.inlet.mass_rate == 0.0:
            from tango_next.components.surface.single_flash import SingleFlashSurface  # noqa: PLC0415

            if isinstance(surface, SingleFlashSurface):
                # Cold start: seed inlet from surface field values
                surface.inlet.T = surface.surface_temperature
                surface.inlet.P = surface.surface_pressure
            surface.inlet.mass_rate = self.mass_rate
            surface.inlet.fluid_name = self.fluid_name

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
        self._seed_surface_inlet()
        surface: SingleFlashSurface | None = self._by_idx.get(0)  # type: ignore[assignment]
        if surface is not None:
            surface.inlet.mass_rate = self.mass_rate
            surface.inlet.fluid_name = self.fluid_name

        if self.policy == InjectionPolicy.MANUAL:
            super().run_timestep(t)  # one circuit pass — inherited from SystemDirect
            if surface is not None:
                logger.info(
                    "t=%3d  MANUAL single pass  P_inj=%.4g Pa",
                    t,
                    surface.outlet.P,
                )
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
        surface = self._by_idx.get(0)
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
