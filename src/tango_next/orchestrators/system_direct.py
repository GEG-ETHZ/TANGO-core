"""SystemDirect — single-pass orchestrator for tango_next.

Auto-selected when sim_config.injection_mode is absent — i.e. the input graph
declares no boundary-condition variable to solve for (e.g. a bare wellbore
test fixture). Executes each component exactly once per timestep, in
component_idx order, wiring each component's outlet into its downstream
neighbor's inlet immediately after it solves.

This is also the base class for SystemBCIteration (see that module's
docstring). SystemDirect owns the only implementation of "one circuit pass"
and "loop over timesteps" — SystemBCIteration reuses both via inheritance
instead of re-implementing them. The choice between the two orchestrator
classes is a topology question (does this graph declare a BC-iteration
circuit at all); InjectionPolicy is the sole authority over how many passes
a single timestep takes once that topology choice has been made.
"""

from __future__ import annotations

from tango_next.core.component import Component
from tango_next.core.orchestrator import Orchestrator


class SystemDirect(Orchestrator):
    """Single-pass orchestrator: one circuit pass per timestep, no BC concept.

    Also the base class for SystemBCIteration — see module docstring.
    """

    def __init__(self, components: dict[str, Component], n_tsteps: int = 1) -> None:
        """Initialise, sorting components by component_idx for circuit order."""
        self._components = components
        self.n_tsteps = n_tsteps

        # Sort components by component_idx for deterministic solve order.
        self._ordered: list[Component] = sorted(
            components.values(),
            key=lambda c: c.component_idx,
        )
        # Build idx → component lookup for stream wiring.
        self._by_idx: dict[int, Component] = {c.component_idx: c for c in self._ordered}

    @property
    def components(self) -> dict[str, Component]:
        """Return the named component dict."""
        return self._components

    def _wire_one_stream(self, component: Component) -> None:
        """Copy ``component.outlet`` to its immediate downstream component's inlet.

        Called once per component immediately after its ``solve()``, so each
        component in the circuit receives fresh upstream state within the same
        pass. Contrast with a batch wire-all-at-end approach, which would leave
        components 1-N reading stale (default-zero) inlet state on the first pass.

        Components without a ``next`` field in their spec (e.g. EconomicComponent)
        are silently skipped — they receive no downstream wiring.
        """
        next_idx: int | None = getattr(component, "next", None)
        if next_idx is None or next_idx not in self._by_idx:
            return
        downstream = self._by_idx[next_idx]
        src = component.outlet
        dst = downstream.inlet
        dst.T = src.T
        dst.P = src.P
        dst.mass_rate = src.mass_rate
        dst.rho = src.rho
        dst.mu = src.mu

    def run_timestep(self, t: int) -> None:
        """Execute one circuit pass: solve each component in order and wire streams."""
        for component in self._ordered:
            component.solve()
            self._wire_one_stream(component)

    def _after_timestep(self, t: int) -> None:
        """Hook called after each timestep in ``run()``; no-op by default.

        Overridden by SystemBCIteration to log a per-timestep summary, without
        duplicating the timestep loop itself.
        """
        return

    def record(self, t: int) -> None:
        """Cascade record to every component in the circuit."""
        for component in self._ordered:
            component.record(t)

    def run(self) -> None:
        """Execute all timesteps."""
        for t in range(self.n_tsteps):
            self.run_timestep(t)
            self._after_timestep(t)
            self.record(t)
