"""Orchestrator ABC for tango."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tango.core.component import FlowComponent


class Orchestrator(ABC):
    """Abstract base for all tango orchestrators.

    Owns the component graph and executes components in the correct order
    within each timestep.  Concrete subclasses: SystemDirect (single-pass,
    no BC concept) and SystemBCIteration (subclasses SystemDirect, adding
    injection-pressure/mass-rate BC iteration governed by InjectionPolicy).
    """

    @property
    @abstractmethod
    def components(self) -> dict[str, FlowComponent]:
        """Named components, keyed by the name used in the input file."""
        ...

    @abstractmethod
    def run_timestep(self, t: int) -> None:
        """Execute one simulation timestep.

        Args:
            t: Zero-based timestep index.

        """
        ...

    @abstractmethod
    def run(self) -> None:
        """Execute the full simulation across all timesteps."""
        ...
