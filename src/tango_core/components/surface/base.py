# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Abstract base for surface / power-plant components in tango."""

from __future__ import annotations

from abc import abstractmethod

from pydantic import Field, PositiveFloat

from tango_core.core.component import FlowComponent
from tango_core.core.specs import Common
from tango_core.core.stream import Stream


class SurfaceComponent(FlowComponent):
    """Abstract base for surface / power-plant components.

    The surface component is always at component_idx=0 (the BC checkpoint).
    Its injection_pressure field provides the initial guess to SystemBCIteration.
    Concrete implementation: GraphSurface, which builds its TESPy network
    from a YAML power_plant.nodes/edges block rather than hardcoding a fixed
    topology — see components/surface/graph.py for the single-flash,
    direct-heat, or any other plant design.
    """

    prev: int = Field(frozen=True)
    """Circuit index of the upstream component."""
    next: int = Field(frozen=True)
    """Circuit index of the downstream component."""
    common: Common = Field(frozen=True)
    """Shared fluid/rock parameters — a reference to the SAME Common
    instance every other component in the Workflow holds, not an
    independent copy. Provides surface_temperature/surface_pressure
    (ambient BC state). See core/specs.py."""
    injection_pressure: PositiveFloat
    """Injection wellhead pressure (Pa), fixed for the whole run.

    Not frozen, unlike the other fields here: tests and tools set it
    directly on a built component (see Component's class docstring).
    """
    pipe_diameter: PositiveFloat = Field(frozen=True)
    """Surface pipe inner diameter (m)."""
    pipe_roughness: PositiveFloat = Field(frozen=True)
    """Absolute pipe wall roughness (m)."""
    approach_temperature: PositiveFloat = Field(frozen=True)
    """Heat exchanger approach temperature (K).

    Residual gap between the cooled fluid's final temperature and the ambient
    temperature into which heat is being rejected.
    """
    target_extraction_pressure: PositiveFloat = Field(frozen=True)
    """Minimum required extraction pressure at the surface inlet (Pa).
    Sourced from ``sim_config.target_extraction_pressure`` — the SINGLE
    shared source, threaded in by ``_build_components`` (see that field's
    docstring in ``core/specs.py``). Any pump-bearing production well in
    the same Workflow declares a field of this exact same name and
    receives the identical value the same way — do not set this directly
    in a component's own YAML block (``_build_components`` now rejects
    that explicitly)."""

    @abstractmethod
    def solve(self, inlet: Stream) -> Stream:
        """Compute power plant outputs, and compute and return the reinjection state from the production inlet."""
