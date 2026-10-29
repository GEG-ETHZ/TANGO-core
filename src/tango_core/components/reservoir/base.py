# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Abstract base for reservoir components in tango."""

from __future__ import annotations

from abc import abstractmethod

from pydantic import Field, PositiveFloat

from tango_core.core.component import FlowComponent
from tango_core.core.constants import GRAVITY
from tango_core.core.stream import Stream


class ReservoirComponent(FlowComponent):
    """Abstract base for all reservoir components.

    External simulators (CMG, MOOSE) are meant to implement this interface
    as adapters; none exists yet, so ``LumpedReservoir`` is the only
    implementation. The native implementation assumes incompressible 1D
    Darcy flow;
    external simulators may relax this assumption during transients.
    """

    prev: int = Field(frozen=True)
    """Circuit index of the upstream component."""
    next: int = Field(frozen=True)
    """Circuit index of the downstream component."""
    reservoir_depth: PositiveFloat = Field(frozen=True)
    """Depth of the reservoir mid-point (m)."""
    thickness: PositiveFloat = Field(frozen=True)
    """Reservoir thickness (m)."""
    permeability: PositiveFloat = Field(frozen=True)
    """Reservoir permeability (m²)."""
    porosity: PositiveFloat = Field(frozen=True)
    """Reservoir porosity (dimensionless)."""
    hydro_static_pressure: PositiveFloat = Field(frozen=True)
    """Hydrostatic pressure at reservoir depth (Pa), used only for the
    fracking-safety ceiling. Derived from the config as ``brine_density ×
    gravity × reservoir_depth`` (see ``tango_core.workflows.linked_quantities``),
    so it's the same pressure the reservoir starts at; a config value that
    disagrees raises ``ConfigError``. For another in-situ density, set
    ``brine_density`` and leave this out."""
    over_pressure_percentage: PositiveFloat = Field(frozen=True)
    """Over-pressure as a percentage of hydrostatic pressure (%). Combines
    with ``hydro_static_pressure`` for the fracking-safety ceiling only."""
    brine_density: PositiveFloat = Field(default=1000.0, frozen=True)
    """Brine density (kg/m³). Sets both the reservoir's initial/undepleted
    pressure and ``hydro_static_pressure``, each ``brine_density × g ×
    reservoir_depth``."""
    gravity: PositiveFloat = Field(default=GRAVITY, frozen=True)
    """Gravitational acceleration (m/s²) — defaults to core/constants.py's
    GRAVITY, overridable per reservoir since gravity varies regionally."""

    @abstractmethod
    def solve(self, inlet: Stream) -> Stream:
        """Compute and return the reservoir outlet state from the injection inlet state."""
