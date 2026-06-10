"""Abstract base for surface / power-plant components in tango_next."""

from __future__ import annotations

from abc import abstractmethod

from pydantic import ConfigDict

from tango_next.core.component import Component, ComponentSpec


class SurfaceSpec(ComponentSpec):
    """Base specification for surface / power-plant components."""

    model_config = ConfigDict(frozen=True)

    prev: int
    next: int
    surface_temperature: float
    """Ambient surface temperature (K)."""
    surface_pressure: float
    """Ambient surface pressure (Pa)."""
    injection_pressure: float
    """Initial guess for injection pressure used by SystemBCIteration (Pa)."""
    pipe_diameter: float
    """Surface pipe inner diameter (m)."""
    pipe_roughness: float
    """Absolute pipe wall roughness (m)."""
    approach_temperature: float
    """Heat exchanger approach temperature (K)."""
    target_extraction_pressure: float
    """Minimum required extraction pressure at the surface (Pa)."""


class SurfaceComponent(Component):
    """Abstract base for surface / power-plant components.

    The surface component is always at component_idx=0 (the BC checkpoint).
    Its injection_pressure field provides the initial guess to SystemBCIteration.
    Concrete implementations: FlexibleSingleFlash, FlexibleDoubleFlash, etc. (Phase 3+).
    """

    @property
    @abstractmethod
    def spec(self) -> SurfaceSpec:
        """The typed surface specification."""
        ...

    @abstractmethod
    def solve(self) -> None:
        """Compute power plant outputs and reinjection state from production inlet."""
        ...
