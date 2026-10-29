"""Validated schemas for the top-level ``common:``/``layout:``/``sim_config:`` YAML blocks.

Every ``Component`` subclass is already its own schema (Pydantic fields,
``extra="forbid"``) — these three classes give the same guarantee to the
top-level blocks. Unknown keys raise at load time rather than being
silently accepted and never read by anything.

``economic:`` is deliberately NOT covered here: it's not a top-level
schema in the same sense as ``common:``/``layout:``/``sim_config:`` — it's
validated as a ``Component`` subclass in its own right
(``DoubletEconomicComponent``, ``components/economic/doublet.py``), the same
way ``components:`` entries are, via ``Workflow._build_economic_component()``.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from tango.components.reservoir.wellpattern_impedance import WellPattern
from tango.core.fluid_state import COOLPROP_BACKEND, CoolPropBackend
from tango.core.policies import InjectionPolicy

logger = logging.getLogger(__name__)


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

    fluid_name: str
    """Working fluid as a CoolProp fluid name, e.g. H2O or CO2."""
    rock_density: float
    """Rock density (kg/m3)."""
    rock_cp: float
    """Rock specific heat capacity (J/(kg K))."""
    rock_k: float
    """Rock thermal conductivity (W/(m K))."""
    thermal_gradient: float
    """Geothermal gradient (K/m)."""
    surface_temperature: float
    """Surface temperature (K): the ambient air temperature for cooling, and the top of the
    linear geotherm."""
    surface_pressure: float
    """Ambient surface pressure (Pa)."""
    coolprop_backend: CoolPropBackend = COOLPROP_BACKEND
    """CoolProp equation-of-state backend for all fluid-property lookups
    (``core/fluid_state.py``'s ``CoolPropBackend``). Defaults to exact
    ``HEOS``; the faster tabulated ``BICUBIC&HEOS`` is unreliable near phase
    boundaries (see its docstring)."""
    saturation_margin: float = Field(default=0.05, ge=0.0, lt=1.0)
    """Minimum relative distance (fraction) between a well cell's pressure and
    the fluid's saturation pressure at that cell's temperature.

    The well models assume single-phase flow, so a cell whose pressure lies
    within ``saturation_margin * p_sat(T)`` of ``p_sat(T)``, on either side,
    or inside the vapor-liquid dome, raises ``SaturationError``. Only applies
    below the fluid's critical temperature, where a saturation pressure
    exists. ``0`` rejects only states that are actually two-phase.

    The 5% default is engineering judgement: no published standard gives a
    margin to saturation for wells in this form. Related practice that
    motivated it: pump suction NPSH margin ratios of 1.1-1.3 (ANSI/HI
    9.6.1, application-dependent), the margin to the saturation line kept
    at supercritical-CO2 compressor inlets (sized case by case, e.g. by
    inlet Mach number), and dense-phase CO2 pipelines operated well above
    their phase-change pressure."""

    # NOTE: FIELD AND MODEL VALIDATION

    @field_validator("rock_density")
    @classmethod
    def check_rock_density(cls, density: float) -> float:
        """Validate that ``rock_density`` is a physically plausible value.

        ``rock_density`` is in kg/m^3 (SI, no unit suffix needed).

        Hard check (raises ``ValueError``): outside 1000-4000 kg/m^3 —
        roughly water's density on the low end to the densest common
        reservoir rock (e.g. basalt, ~3000 kg/m^3) with margin on the high
        end. A value outside this range is almost certainly a units
        mistake or a typo, not a real reservoir rock.

        Args:
            density: Candidate ``rock_density`` value, in kg/m^3.

        Returns:
            ``density`` unchanged, once it has passed the range check.

        Raises:
            ValueError: If ``density`` is outside the 1000-4000 kg/m^3 range.
        """
        if not (1000.0 <= density <= 4000.0):
            raise ValueError(
                f"""Rock density={density} kg/m^3 is outside of the plausible physical range for reservoir rock (1000-4000 kg/m^3)
                Please set rock_density to a value within this range in the input YAML file""",
            )
        return density

    @field_validator("rock_cp")
    @classmethod
    def check_rock_heat_capacity(cls, heat_capacity: float) -> float:
        """Validate that ``rock_cp`` (specific heat capacity) is plausible.

        ``rock_cp`` is in J/(kg*K) (SI, no unit suffix needed).

        Hard check (raises ``ValueError``): outside 500-1500 J/(kg*K) —
        the typical range for common reservoir rock types (e.g. granite
        ~790, sandstone ~920, limestone ~880 J/(kg*K)), with margin. A
        value outside this range is almost certainly a units mistake or a
        typo.

        Args:
            heat_capacity: Candidate ``rock_cp`` value, in J/(kg*K).

        Returns:
            ``heat_capacity`` unchanged, once it has passed the range check.

        Raises:
            ValueError: If ``heat_capacity`` is outside the 500-1500
                J/(kg*K) range.
        """
        if not (500.0 <= heat_capacity <= 1500.0):
            raise ValueError(
                f"""Rock heat capacity={heat_capacity} J/ kg/ K is outside of the plausible range for reservoir rock (500 - 1500 J/ kg/ K)
                Please set rock_cp to a value within this range in the input YAML file""",
            )
        return heat_capacity

    @field_validator("rock_k")
    @classmethod
    def check_rock_k(cls, conductivity: float) -> float:
        """Validate that ``rock_k`` (thermal conductivity) is plausible.

        ``rock_k`` is in W/(m*K) (SI, no unit suffix needed).

        Hard check (raises ``ValueError``): outside 0.1-6.0 W/(m*K) —
        the typical range for common reservoir rock types (e.g. shale
        ~1.5, sandstone ~3, quartzite ~6 W/(m*K)), with margin. A value
        outside this range is almost certainly a units mistake or a typo.

        Args:
            conductivity: Candidate ``rock_k`` value, in W/(m*K).

        Returns:
            ``conductivity`` unchanged, once it has passed the range check.

        Raises:
            ValueError: If ``conductivity`` is outside the 0.1-6.0 W/(m*K)
                range.
        """
        if not (0.1 <= conductivity <= 6.0):
            raise ValueError(
                f"""Rock thermal conductivity={conductivity} W/ m/ K is outside the plausible range for thermal rock conductivity (0.1 - 6.0 W/ m/ K)
                Please set rock_k to a value within this range in the input YAML file""",
            )
        return conductivity

    @field_validator("thermal_gradient")
    @classmethod
    def check_thermal_gradient(cls, gradient: float) -> float:
        """Validate that ``thermal_gradient`` is positive and plausible.

        ``thermal_gradient`` is in K/m (SI, no unit suffix needed) — e.g.
        a real-world "35 degC/km" site is entered here as ``0.035``, NOT
        ``35``. The warning threshold below is stated in K/km (a more
        intuitive unit for this quantity) purely for the log message, so
        it converts ``gradient`` (K/m) to K/km via ``* 1000`` before
        comparing — do not compare ``gradient`` directly against a
        K/km-scaled number, that silently makes the check unreachable for
        any real input.

        Hard check (raises ``ValueError``): non-positive. A geothermal
        reservoir requires a positive temperature gradient with depth by
        definition.

        Soft check (logs a warning, does NOT raise): equivalent to
        > 200 K/km (> 0.2 K/m). Real geothermal gradients are typically
        0.02-0.1 K/m (20-100 degC/km); anything above 200 K/km is either
        an exceptional site or, more likely, a units mistake (e.g. a
        K/km value entered directly instead of being converted to K/m).

        Args:
            gradient: Candidate ``thermal_gradient`` value, in K/m.

        Returns:
            ``gradient`` unchanged, once it has passed the hard check.

        Raises:
            ValueError: If ``gradient`` is not positive.
        """
        if gradient <= 0.0:
            raise ValueError(
                f"""Thermal gradient={gradient} must be positive
                Please set thermal_gradient to a positive value in the input YAML file""",
            )

        gradient_K_per_km = gradient * 1000
        if gradient_K_per_km > 200:
            logger.warning(
                "Thermal gradient is very high: %s K/m (%s K/km). Please note thermal_gradient's units are Kelvin per METER, not per kilometer.",
                gradient,
                gradient_K_per_km,
            )

        return gradient

    @field_validator("surface_temperature")
    @classmethod
    def check_surface_temperature(cls, te: float) -> float:
        """Validate that ``surface_temperature`` is a physically plausible value.

        ``surface_temperature`` (and this validator's ``te`` parameter) is
        in Kelvin — SI, so no unit suffix on the field name per this repo's
        unit-suffix-naming convention (see CONTRIBUTING.md). The
        error/warning messages below additionally show the Celsius
        equivalent purely for human readability; the value itself is
        always handled and returned in Kelvin, never converted.

        Hard check (raises ``ValueError``, construction fails): outside
        204-330 K (-69.15 to 58.85 degC). This is a wide envelope around
        the extremes of naturally-occurring ambient surface conditions on
        Earth, with margin — a value outside it is almost certainly a
        units mistake (e.g. a Celsius value entered where Kelvin is
        expected) or a typo, not a real site's ambient temperature.

        Soft check (logs a warning, does NOT raise — construction still
        succeeds): above 315 K (41.85 degC) or below 278 K (4.85 degC).
        Still physically plausible, but unusual enough for a geothermal
        site's ambient/surface temperature that it's worth a second look
        at the input rather than a hard failure.

        Args:
            te: Candidate ``surface_temperature`` value, in Kelvin.

        Returns:
            ``te`` unchanged, once it has passed the hard range check.

        Raises:
            ValueError: If ``te`` is outside the 204-330 K hard range.
        """
        if not (204 <= te <= 330):
            raise ValueError(
                f"""Surface temperature={te} K or {te - 273.15} degrees C this is outside of the plausible of 204K to 330K (-69.15 to 58.85 degrees Celcius)
                    Please set the surface_temperature (K) to a value within this range in input YAML file""",
            )

        elif te > 315:
            logger.warning(
                f"""Surface temperature={te} K or {te - 273.15} degrees Celsius, this is quite high! Please double check your value""",
            )

        elif te < 278:
            logger.warning(
                f"""Surface temperature={te} K or {te - 273.15} degrees Celsius, this is quite low! Please double check your value""",
            )

        return te

    @field_validator("surface_pressure")
    @classmethod
    def check_surface_pressure(cls, pressure: float) -> float:
        """Validate that ``surface_pressure`` is a physically plausible value.

        ``surface_pressure`` is in Pa (SI, no unit suffix needed).

        Hard check (raises ``ValueError``): outside 90000-108400 Pa —
        roughly the range of sea-level-adjusted atmospheric pressure
        recorded on Earth (extreme low/high weather systems), which also
        comfortably covers any inhabited-elevation geothermal site. A
        value outside this range is almost certainly a units mistake
        (e.g. a kPa or bar value entered directly) or a typo.

        Args:
            pressure: Candidate ``surface_pressure`` value, in Pa.

        Returns:
            ``pressure`` unchanged, once it has passed the range check.

        Raises:
            ValueError: If ``pressure`` is outside the 90000-108400 Pa
                range.
        """
        if not (90000 <= pressure <= 108400):
            raise ValueError(
                f"""Surface pressure={pressure} Pa is outside of the plausible range of values (90000 - 108400)
                Please set surface_pressure to a value within this range in input YAML file""",
            )

        return pressure


class Layout(BaseModel):
    """Schema for the ``layout:`` YAML block — well-field geometry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    well_spacing: float
    """Distance between the injection and production wells (m); for closed-loop AGS configs,
    the horizontal loop length."""
    well_pattern: WellPattern | None = None
    """Consumed by ``LumpedReservoir``. Typed as ``WellPattern`` itself
    (not ``str``) so Pydantic's own enum coercion — via ``WellPattern``'s
    case-insensitive ``_missing_`` hook — validates/rejects the raw YAML
    string before ``check_well_pattern`` below ever runs; that validator
    only adds the "recognized but not yet implemented" check Pydantic's
    own coercion can't. ``None`` for configs with no well-pattern-dependent
    reservoir impedance (e.g. ``AGS_direct_heat.yml``, which has no
    reservoir component at all)."""
    well_pattern_dimens: list[int] | None = None
    """Not yet consumed — TODO add to wellpattern_impedance.py calculations"""

    # NOTE: FIELD AND MODEL VALIDATIONS

    @field_validator("well_spacing")
    @classmethod
    def check_well_spacing(cls, spacing: float) -> float:
        """Validate that ``well_spacing`` is a physically plausible value.

        ``well_spacing`` is in m (SI, no unit suffix needed). Despite the
        name, this field does double duty: for doublet/multi-well
        reservoir patterns it's the true well-to-well spacing consumed by
        ``LumpedReservoir`` via ``WellPattern``; for closed-loop AGS
        configs with no reservoir component at all (e.g.
        ``AGS_direct_heat.yml``), it's repurposed as the horizontal loop
        length instead. The range below is wide enough to cover both uses.

        Hard check (raises ``ValueError``): outside 100-50000 m. A value
        outside this range is almost certainly a units mistake or a typo,
        not a real well spacing or loop length.

        Soft check (logs a warning, does NOT raise): above 2000 m. Still
        plausible (long AGS loops legitimately run to several km), but
        unusual enough to be worth a second look.

        Args:
            spacing: Candidate ``well_spacing`` value, in m.

        Returns:
            ``spacing`` unchanged, once it has passed the hard check.

        Raises:
            ValueError: If ``spacing`` is outside the 100-50000 m range.
        """
        if not (100.0 < spacing < 50000):
            raise ValueError(
                f"""Well Spacing {spacing} m is outside of plausible range (100m - 50000m)
                Please set well_spacing to a value within this range in input YAML file""",
            )

        elif spacing > 2000:
            logger.warning(f"well_spacing={spacing} over 2km! Please double check your value")

        return spacing

    @field_validator("well_pattern")
    @classmethod
    def check_well_pattern(cls, pattern: WellPattern | None) -> WellPattern | None:
        """Validate that ``well_pattern`` names a pattern with an implemented formula.

        By the time this runs, ``pattern`` is already either ``None`` or a
        real ``WellPattern`` member — Pydantic coerces (or rejects) the raw
        YAML string via ``WellPattern``'s own case-insensitive ``_missing_``
        hook as part of validating the field's ``WellPattern | None`` type,
        before any ``field_validator`` sees it (field validators default to
        ``mode="after"``, i.e. after type coercion). This validator only
        adds the one check Pydantic's own enum coercion can't: rejecting a
        real, recognized pattern that has no analytic impedance formula
        implemented yet.

        Args:
            pattern: Already-validated ``well_pattern`` value, or ``None``.

        Returns:
            ``pattern`` unchanged.

        Raises:
            NotImplementedError: If ``pattern`` is a real ``WellPattern``
                member with no analytic impedance formula implemented yet
                (see ``WellPattern.has_impedance_formula()``).
        """
        if pattern is None:
            return pattern

        if not pattern.has_impedance_formula():  # Check if the well pattern has an impedance formula
            raise NotImplementedError(
                f"This well pattern {pattern} exists but no analytic impedance formula has been implemented yet.",
            )

        return pattern


class SimConfig(BaseModel):
    """Schema for the ``sim_config:`` YAML block."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    num_tsteps: int
    """Number of timesteps in the run."""
    dt_years: float
    """Length of one timestep (years)."""
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
    ``docs/bugs-fixed-in-tango.md``."""
    injection_mode: InjectionPolicy | None = None
    """Absent selects SystemDirect (no BC iteration); present selects
    SystemBCIteration."""
    mass_rate: float | None = None
    """Mass flow rate (kg/s), used every timestep. Required whenever
    injection_mode is present."""
    bc_checkpoint_idx: int | None = None
    """Required when injection_mode is present."""

    # NOTE: FIELD AND MODEL VALIDATIONS

    @field_validator("dt_years")
    @classmethod
    def check_dt_years(cls, dt: float) -> float:
        """Validate that ``dt_years`` (timestep size) is positive.

        ``dt_years`` is in years (this field is the one deliberate
        exception to the "no unit suffix on SI fields" convention — years
        is the natural, human-scale unit for a geothermal timestep, not
        seconds).

        Args:
            dt: Candidate ``dt_years`` value, in years.

        Returns:
            ``dt`` unchanged, once it has passed the positivity check.

        Raises:
            ValueError: If ``dt`` is not positive.
        """
        if dt <= 0:
            raise ValueError(
                f"""dt_years={dt} must be a positive value!
                Please change dt_years in the input YAML file""",
            )
        # TODO: should we add warnings for large timesteps?
        return dt

    @field_validator("injection_mode", mode="before")
    @classmethod
    def reject_removed_injection_modes(cls, value: Any) -> Any:
        """Explain the removed automatic modes instead of a bare "invalid enum value".

        Raises:
            ValueError: ``value`` is ``auto-pressure``, ``auto-flow`` or ``auto-both``.
        """
        if value in _REMOVED_INJECTION_MODES:
            raise ValueError(
                f"injection_mode {value!r} was removed (see InjectionPolicy's docstring). Use "
                "manual or manual-fracking-check with a fixed mass_rate and injection_pressure; to "
                "find good operating points, run an applications/opt_*/ search.",
            )
        return value

    @model_validator(mode="after")
    def check_injection_mode_requirements(self) -> SimConfig:
        """Require ``bc_checkpoint_idx`` and ``mass_rate`` whenever ``injection_mode`` is set.

        ``injection_mode`` absent means ``SystemDirect`` (no BC iteration),
        which needs neither.

        Returns:
            ``self`` unchanged, once every applicable check has passed.

        Raises:
            ValueError: If ``injection_mode`` is set and ``bc_checkpoint_idx``
                or ``mass_rate`` is absent.
        """
        if self.injection_mode is None:
            return self
        if self.bc_checkpoint_idx is None:
            raise ValueError(
                f"""bc_checkpoint_idx is required when injection mode is set
                got injection_mode={self.injection_mode}""",
            )
        if self.mass_rate is None:
            raise ValueError(f"mass_rate is required when injection_mode={self.injection_mode}")
        return self


_REMOVED_INJECTION_MODES = frozenset({"auto-pressure", "auto-flow", "auto-both"})


class Description(BaseModel):
    """Schema for the optional top-level ``description:`` YAML block.

    Entirely optional — a config that omits ``description:`` is unaffected
    (see ``Workflow.__init__``); this only validates the block when it's
    present. Meant to answer, for whoever reads this config next without
    any other context:

    - ``summary`` — one line, whatever makes this file's purpose
      recognizable in a directory listing (required if the block is
      present at all; the whole point of the block is defeated by an
      empty one-liner).
    - ``author``/``date`` — optional attribution/provenance: who wrote
      this config and when. Deliberately plain, unvalidated strings
      (e.g. ``"2026-09"`` or ``"Chad Baker"`` are both fine) rather than a
      strictly-typed date/name field — this is documentation, not a data
      field anything downstream computes from, so validating its format
      would add friction without adding safety.
    - ``description`` — free text answering *What* (what physical system
      is being modeled, e.g. "double-flash power plant, Triemli site"),
      *Why* (why this particular run/config exists, e.g. "baseline for
      the opt_hydro_df_electric search"), and *How* (components, models,
      assumptions, whether there's an optimization loop, compute
      requirements) — whatever of those is relevant; not all three
      sections are mandatory for every config.

    Example::

        description:
          summary: Baseline single-flash config for the Triemli site
          author: Chad Baker
          date: "2026-09-18"
          description: >
            Manual mass-flow-rate single-flash system, the unmodified
            starting point for studies of the Triemli site.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: Annotated[str, StringConstraints(max_length=200, strip_whitespace=True)]
    """One-line purpose of the config."""
    author: str | None = None
    """Who wrote the config."""
    date: str | None = None
    """When the config was written, as free text."""
    description: Annotated[str, StringConstraints(max_length=2000, strip_whitespace=True)] = ""
    """Free text: what is modeled, why the config exists and how."""
