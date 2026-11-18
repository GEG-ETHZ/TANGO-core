# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Orchestrator ABC for tango."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tango_core.core.component import FlowComponent


class Orchestrator(ABC):
    """Abstract base for all tango orchestrators.

    Owns the component graph and executes components in the correct order
    within each sync interval.  Concrete subclasses: SystemDirect (single-pass,
    no BC concept) and SystemBCIteration (subclasses SystemDirect, adding
    injection-pressure/mass-rate BC iteration governed by InjectionPolicy).
    """

    @property
    @abstractmethod
    def components(self) -> dict[str, FlowComponent]:
        """Named components, keyed by the name used in the input file."""
        ...

    @abstractmethod
    def run_interval(self, i: int) -> None:
        """Execute one sync interval: every subsystem's steps up to the next sync time.

        With a single subsystem, an interval is one timestep (see
        ``tango_core.core.time_stepping``).

        Args:
            i: Zero-based sync interval index.

        """
        ...

    @abstractmethod
    def run(self) -> None:
        """Execute the full simulation across all timesteps."""
        ...
