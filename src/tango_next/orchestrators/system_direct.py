"""SystemDirect — single-pass orchestrator for tango_next.

Auto-selected when schedule.bc_iteration is absent. Executes each component
exactly once per timestep in topological order with no convergence loop.
"""

from __future__ import annotations

from tango_next.core.component import Component
from tango_next.core.orchestrator import Orchestrator


class SystemDirect(Orchestrator):
    """Single-pass orchestrator: one solve() per component per timestep."""

    def __init__(self, components: dict[str, Component]) -> None:
        """Initialise with the named component dict."""
        self._components = components

    @property
    def components(self) -> dict[str, Component]:
        """Return the named component dict."""
        return self._components

    def run_timestep(self, t: int) -> None:
        """Execute one timestep: call solve() on each component in order."""
        for component in self._components.values():
            component.solve()

    def run(self) -> None:
        """Execute all timesteps."""
        raise NotImplementedError("SystemDirect.run() not yet implemented")
