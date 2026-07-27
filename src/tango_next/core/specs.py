"""Validated schemas for the top-level ``common:``/``layout:``/``sim_config:`` YAML blocks.

Every ``Component`` subclass is already its own schema (Pydantic fields,
``extra="forbid"``) — these three classes give the same guarantee to the
top-level blocks. Unknown keys raise at load time rather than being
silently accepted and never read by anything.

``economic:`` is deliberately NOT covered here yet: no ``EconomicComponent``
reads it (Phase 2 placeholder — see ``AGS_direct_heat.yml``'s comment),
so inventing a schema for fields nothing consumes risks getting the shape
wrong and having to redo it once the real component lands.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from tango_next.core.policies import InjectionPolicy


class Common(BaseModel):
    """Schema for the ``common:`` YAML block — shared fluid/rock parameters.

    A single ``Common`` instance is shared BY REFERENCE across every
    component that needs it (Pydantic does not copy nested model fields on
    construction — verified: ``well.common is reservoir.common`` is
    ``True`` when both are built from the same instance). Frozen (whole
    model): these values must stay fixed for a Workflow's lifetime. See
    ``workflows/workflow.py`` for when it's fine to change them anyway
    (rebuild a new Workflow from a modified dict).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    fluid_name: str = "Water"
    rock_density: float
    rock_cp: float
    rock_k: float
    thermal_gradient: float
    surface_temperature: float
    surface_pressure: float


class Layout(BaseModel):
    """Schema for the ``layout:`` YAML block — well-field geometry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    well_spacing: float = 707.0
    well_pattern: str | None = None
    """Not yet consumed by any tango_next component — reserved for the
    planned 5-spot/inverted-5-spot reservoir impedance variants (see
    reservoir/lumped.py's TODO). Declared (rather than omitted) so it's
    validated and documented instead of silently accepted-and-ignored."""
    well_pattern_dimens: list[int] | None = None
    """Not yet consumed — see well_pattern above."""


class SimConfig(BaseModel):
    """Schema for the ``sim_config:`` YAML block."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    num_tsteps: int
    dt_years: float
    injection_mode: InjectionPolicy | None = None
    """Absent selects SystemDirect (no BC iteration); present selects
    SystemBCIteration."""
    mass_rate: float | None = None
    """Required unless injection_mode is absent, or is AUTO_FLOW/AUTO_BOTH
    (mass rate computed from fracing_flow() instead)."""
    bc_checkpoint_idx: int | None = None
    """Required when injection_mode is present."""
