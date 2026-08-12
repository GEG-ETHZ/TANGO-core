"""Validated schemas for the top-level ``common:``/``layout:``/``sim_config:`` YAML blocks.

Every ``Component`` subclass is already its own schema (Pydantic fields,
``extra="forbid"``) — these three classes give the same guarantee to the
top-level blocks. Unknown keys raise at load time rather than being
silently accepted and never read by anything.

``economic:`` is deliberately NOT covered here: it's not a top-level
schema in the same sense as ``common:``/``layout:``/``sim_config:`` — it's
validated as a ``Component`` subclass in its own right
(``NativeEconomicComponent``, ``components/economic/native.py``), the same
way ``components:`` entries are, via ``Workflow._build_economic_component()``.
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
    target_extraction_pressure: float
    """Minimum required extraction pressure at the surface inlet (Pa) — the
    SINGLE shared source of this value. Threaded to any component
    declaring a field of this exact name (``SurfaceComponent``,
    pump-bearing production wells) via ``_build_components``'s
    ``layout_extras`` mechanism, the same way ``well_spacing``/``dt_years``
    already are. Previously duplicated as two independently-set,
    unvalidated copies (``SurfaceComponent.target_extraction_pressure`` and
    each pump-bearing well's own ``pump_target_pressure_megapascals``) with
    nothing enforcing they matched — a real Rule 5 ("shared via reference,
    not separate copies that can drift") violation. See
    ``docs/bugs-fixed-in-tango-next.md``."""
    injection_mode: InjectionPolicy | None = None
    """Absent selects SystemDirect (no BC iteration); present selects
    SystemBCIteration."""
    mass_rate: float | None = None
    """Required whenever injection_mode is present. For MANUAL/
    MANUAL_FRACKING_CHECK/AUTO_PRESSURE this is the fixed mass rate used
    every timestep. For AUTO_FLOW/AUTO_BOTH it is instead the INITIAL GUESS
    for the Picard iteration that converges mass_rate = fracking_flow()
    each pass (mirrors injection_pressure's role as AUTO_PRESSURE's initial
    guess). Do not default this to 0.0 or another near-zero value for
    AUTO_FLOW/AUTO_BOTH: the numerical well model is genuinely degenerate at
    near-zero flow, and the resulting first Picard step can overshoot into
    a mass rate the circuit can't solve from a cold start (confirmed
    empirically 2026-08-13 — see SystemBCIteration._converge_injection_flow's
    docstring)."""
    max_mass_rate: float | None = None
    """Optional cap (kg/s) on the mass rate AUTO_FLOW/AUTO_BOTH's Picard
    iteration converges to — ``mass_rate = min(fracking_flow(...),
    max_mass_rate)`` each pass, mirroring old tango's field of the same
    name and purpose. None (default) means uncapped: mass_rate converges to
    whatever fracking_flow() actually computes. Must be omitted for every
    other injection_mode — there is nothing for it to cap."""
    bc_checkpoint_idx: int | None = None
    """Required when injection_mode is present."""
