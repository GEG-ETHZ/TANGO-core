"""Abstract base for surface / power-plant components in tango_next."""

from __future__ import annotations

from abc import abstractmethod

from tango_next.core.component import Component


class SurfaceComponent(Component):
    """Abstract base for surface / power-plant components.

    The surface component is always at component_idx=0 (the BC checkpoint).
    Its injection_pressure field provides the initial guess to SystemBCIteration.
    Concrete implementation: GraphSurface, which builds its TESPy network
    from a YAML power_plant.nodes/edges block rather than hardcoding a fixed
    topology — see components/surface/graph.py for the single-flash,
    direct-heat, or any other plant design.
    """

    prev: int
    """Circuit index of the upstream component."""
    next: int
    """Circuit index of the downstream component."""
    surface_temperature: float
    """Ambient surface temperature (K)."""
    surface_pressure: float
    """Ambient surface pressure (Pa)."""
    injection_pressure: float
    """Initial guess for injection wellhead pressure used by SystemBCIteration (Pa).
    Updated in-place by SystemBCIteration each convergence pass.
    """
    pipe_diameter: float
    """Surface pipe inner diameter (m)."""
    pipe_roughness: float
    """Absolute pipe wall roughness (m)."""
    approach_temperature: float
    """Heat exchanger approach temperature (K)."""
    target_extraction_pressure: float
    """Minimum required extraction pressure at the surface inlet (Pa)."""

    @abstractmethod
    def solve(self) -> None:
        """Compute power plant outputs and reinjection state from production inlet."""
