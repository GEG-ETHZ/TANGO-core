"""SystemBCIteration — convergence-loop orchestrator for tango_next.

Auto-selected when schedule.bc_iteration is present. Iterates injection_pressure
until mass flow is balanced across the circuit.

Replaces the misnamed SystemExternal from Phase 0 — external simulator support
(CMG, MOOSE, DWSIM) is a separate, composable concern, not an orchestrator variant.

Pump pressure iteration note (from Phase 0 analysis):
  The old BC_calculator had a hardcoded 5-iteration inner loop for pump_dp
  with a bad d(P_out)/d(P_in) ≈ 1 assumption and silent failure on phase-boundary
  crossings.  When implementing run_timestep(), use a convergence-based loop instead:

    for pump_iter in range(MAX_PUMP_ITER):  # MAX_PUMP_ITER = 50
        try:
            pump.solve(inlet_P=prod_well.outlet_P + pump_dp, ...)
        except SaturationError:
            pump_dp += (target - pump.outlet_P)
            continue  # also halve the step for conservative boundary-crossing fallback
        dp_error = target - pump.outlet_P
        if abs(dp_error) / target < PUMP_TOLERANCE:
            break
        pump_dp += dp_error
    else:
        raise ConvergenceError(...)
"""

from __future__ import annotations

from tango_next.core.component import Component
from tango_next.core.orchestrator import Orchestrator


class SystemBCIteration(Orchestrator):
    """Convergence-loop orchestrator.

    For each timestep, iteratively adjusts injection_pressure until mass
    flow is balanced (surface outlet mass rate ≈ injection well inlet mass rate).
    Solver variant (explicit / implicit) set by schedule.bc_iteration.solver.
    """

    DEFAULT_MAX_ITERATIONS: int = 200
    DEFAULT_TOLERANCE: float = 1e-4

    def __init__(
        self,
        components: dict[str, Component],
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> None:
        self._components = components
        self.max_iterations = max_iterations
        self.tolerance = tolerance

    @property
    def components(self) -> dict[str, Component]:
        return self._components

    def run_timestep(self, t: int) -> None:
        """Execute one timestep, iterating until mass flow convergence.

        Raises:
            ConvergenceError: If mass flow does not balance within max_iterations.

        """
        raise NotImplementedError("SystemBCIteration.run_timestep() not yet implemented")

    def run(self) -> None:
        """Execute all timesteps."""
        raise NotImplementedError("SystemBCIteration.run() not yet implemented")
