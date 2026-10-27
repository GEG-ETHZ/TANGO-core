"""Workflow — top-level entry point for tango simulations."""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from pydantic import ValidationError

from tango.components.economic.base import EconomicComponent
from tango.components.registry import COMPONENT_REGISTRY
from tango.core.component import Component, FlowComponent
from tango.core.errors import ConfigError
from tango.core.specs import Common, Description, Layout, SimConfig
from tango.orchestrators.system_bc_iteration import SystemBCIteration
from tango.orchestrators.system_direct import SystemDirect
from tango.workflows.linked_quantities import resolve_linked_quantities

logger = logging.getLogger(__name__)

# Reverse of COMPONENT_REGISTRY — every value is a distinct class (checked:
# no two (type, variant) keys map to the same class), so this is a safe,
# unambiguous way to recover the type/variant routing keys for a live
# component instance, needed by Workflow.to_dict() since Component itself
# never stores them (they're routing-only, stripped before construction).
_REVERSE_REGISTRY: dict[type[Component], tuple[str, str]] = {
    cls: key for key, cls in COMPONENT_REGISTRY.items()
}

# Keys single-sourced from common:/layout:/sim_config: and threaded to
# components via _build_components — never legitimately set in a
# component's own YAML block. ONE shared constant, used both to reject
# them at load time (_build_components) and to exclude them from
# Workflow.to_dict()'s per-component dump (they'd otherwise round-trip
# straight back into that same rejection). Keeping this in one place is
# deliberate: the target_extraction_pressure bug this generalizes existed
# BECAUSE two independent copies of "which fields are shared" could drift
# apart — a second hardcoded list here would repeat that exact mistake at
# the meta level.
_LAYOUT_EXTRA_KEYS = ("well_spacing", "well_pattern", "dt_years", "target_extraction_pressure")
_PROTECTED_COMPONENT_KEYS = frozenset({"common", *_LAYOUT_EXTRA_KEYS})


class Workflow:
    """Parses a tango input file and drives the simulation.

    Orchestrator is selected automatically from the input file:
      sim_config.injection_mode present  →  SystemBCIteration
      sim_config.injection_mode absent   →  SystemDirect

    Usage::

        wf = Workflow.from_file("example_configs/hydro_sf_electric.yml")
        wf.run()

    ``from_file``/``from_str``/``to_file``/``to_str``/``to_dict`` are the
    supported (de)serialization surface — one controlled API for load/dump,
    insulated from which YAML library is used underneath.

    Every ``to_dict()`` call reconstructs fresh from this Workflow's actual
    current live state — ``common:``/``layout:``/ ``sim_config:`` from their
    retained, frozen, canonical ``Common``/ ``Layout``/``SimConfig`` instances,
    ``components:`` from each live component's own ``model_dump()`` (which,
    being Pydantic, is inherently live — no caching possible). A mutation to a
    genuinely-mutable field (e.g. ``surface.injection_pressure``) is reflected
    immediately, every time.

    Every top-level YAML block has a real schema: ``common:``/``layout:``/
    ``sim_config:`` validate against ``Common``/``Layout``/``SimConfig``
    (core/specs.py); ``components:`` and ``economic:`` are each validated
    per-component (every ``Component`` subclass, including
    ``DoubletEconomicComponent``, is its own schema). Unknown keys raise
    ConfigError at load time rather than being silently accepted and never
    read by anything. Unlike ``components:``, ``economic:`` is deliberately
    NOT part of the per-timestep circuit — see
    ``_build_economic_component()`` and ``SystemDirect.finalize()``.

    ``description:`` is the one top-level block that's entirely optional
    (see ``Description`` in core/specs.py) — a human-readable summary of
    what a config models and why, validated if present, simply absent
    (``self.description is None``) if not. ``title:`` is similar but
    unvalidated (just read raw as a plain string).

    ``common:`` gets one more guarantee beyond validation: every component
    that needs shared fluid/rock parameters holds a REFERENCE to the same
    ``Common`` instance (Pydantic does not copy nested model fields on
    construction), not an independent copy. ``Common`` is frozen, so
    there's exactly one place these values live and no way for one
    component to silently diverge from another — structurally, not via a
    guard list. See core/specs.py.

    This is also how fluid identity (``Common.fluid_name``) is guaranteed
    consistent across an entire flow path today: every component on the
    circuit reads it off the SAME shared ``Common``, so there is nothing to
    hand around or re-check per timestep (``Stream``, the per-component
    inlet/outlet type, deliberately carries no fluid-identity field of its
    own — see ``core/stream.py``). ``__init__`` asserts this identity once,
    right after building components, so a future refactor that accidentally
    constructs a second ``Common`` for one component fails loudly at
    construction time instead of silently drifting. If a real fluid
    *boundary* is ever introduced (e.g. a secondary/ORC loop with a
    different working fluid from the geofluid loop), that component would
    need an explicit second identity of its own — not a relaxation of this
    check for the whole Workflow.

    A common use for ``to_dict()``: parameter sweeps that mutate a copy of
    the config between runs — safe regardless of whether the ``Workflow``
    was originally built via ``from_file``/``from_str`` or a raw dict, since
    it always returns a fresh dict, never a shared reference::

        base_wf = Workflow.from_file(path)
        for rock_k in sweep_values:
            cfg = base_wf.to_dict()          # fresh reconstruction each call
            cfg["common"]["rock_k"] = rock_k
            Workflow(cfg).run()
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Build the orchestrator and components from a parsed config dict.

        Linked values across components (e.g. a doublet's reservoir depth and
        its wells' lengths) are filled in and checked first; see
        ``tango.workflows.linked_quantities``.
        """
        config = resolve_linked_quantities(config)
        self.title = config.get("title")

        try:
            self._economic: EconomicComponent | None = _build_economic_component(config["economic"])
        except KeyError:
            logger.warning("No economic component found, this simulation will run without economic outputs")
            self._economic = None

        try:
            self._common = Common(**config.get("common", {}))
            self._layout = Layout(**config.get("layout", {}))
            self._sim_config = SimConfig(**config.get("sim_config", {}))
            # Entirely optional — see Description's own docstring. Absent
            # `description:` block means self.description stays None;
            # nothing else in this method depends on it.
            self.description: Description | None = (
                Description(**config["description"]) if "description" in config else None
            )
        except ValidationError as exc:
            raise ConfigError(f"Invalid config:\n{exc}") from exc

        n_tsteps = self._sim_config.num_tsteps
        dt_years = self._sim_config.dt_years
        if self._economic is not None:
            # Total project lifetime (years) — DoubletEconomicComponent needs
            # this for its discount-rate/CRF term but has no sim_config
            # access of its own (see its _total_project_years property).
            self._economic._total_years = n_tsteps * dt_years  # noqa: SLF001

        components = _build_components(
            config["components"],
            self._common,
            self._layout,
            dt_years,
            self._sim_config.target_extraction_pressure,
        )
        _check_common_identity(components, self._common)

        if self._sim_config.injection_mode is not None:
            _check_loop_has_pressure_source(config["components"])

        # mass_rate/bc_checkpoint_idx requirements are both
        # enforced by SimConfig.check_injection_mode_requirements above
        # (raises ValueError -> caught as ConfigError by the try block
        # above) -- nothing left to check here, just read the validated
        # values. The asserts below are for mypy's benefit only (narrowing
        # `float | None`/`int | None` to non-Optional) -- they document
        # an invariant SimConfig already guarantees, not a new check.
        if self._sim_config.injection_mode is not None:
            assert self._sim_config.mass_rate is not None  # noqa: S101
            assert self._sim_config.bc_checkpoint_idx is not None  # noqa: S101
            self._orchestrator: SystemBCIteration | SystemDirect = (  # noqa NOTE: Rename System BC Iteration Aitkens if it is adopted as standard
                SystemBCIteration(
                    components,
                    n_tsteps=n_tsteps,
                    dt_years=dt_years,
                    mass_rate=self._sim_config.mass_rate,
                    bc_checkpoint_idx=self._sim_config.bc_checkpoint_idx,
                    policy=self._sim_config.injection_mode,
                    economic=self._economic,
                )
            )
        else:
            self._orchestrator = SystemDirect(components, n_tsteps=n_tsteps, economic=self._economic)

    @classmethod
    def from_file(cls, path: Path | str) -> Workflow:
        """Load a tango YAML input file and construct a Workflow.

        Args:
            path: Path to the ``.yml`` input file.

        Raises:
            ConfigError: If the file does not exist or cannot be parsed.

        """
        p = Path(path)
        if not p.exists():
            raise ConfigError(f"Input file not found: {p}")
        try:
            text = p.read_text()
        except OSError as exc:
            raise ConfigError(f"Failed to read input file: {p}\n{exc}") from exc
        logger.info("Loaded input file: %s", p)
        return cls.from_str(text)

    @classmethod
    def from_str(cls, s: str) -> Workflow:
        """Parse a YAML config string and construct a Workflow.

        Raises:
            ConfigError: If the string cannot be parsed as YAML.

        """
        try:
            config: dict[str, Any] = yaml.safe_load(s)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Failed to parse YAML:\n{exc}") from exc
        return cls(config)

    def to_dict(self) -> dict[str, Any]:
        """Reconstruct a config dict from this Workflow's CURRENT live state.

        Every call recomputes fresh — nothing here is a cached copy of
        whatever this Workflow happened to be constructed from (see the
        class docstring for why that matters). Mutating the returned dict
        never affects this Workflow or any other ``to_dict()`` call, since
        it's built fresh from ``model_dump()`` calls, not shared references.

        Uses plain ``model_dump()`` throughout, NOT ``mode="json"``:
        component state uses ``float('nan')`` as ``LockedState``'s "not yet
        computed" sentinel, and ``mode="json"`` converts NaN to ``None``
        (not valid JSON), which then fails to reload. Plain ``model_dump()``
        keeps it a real float — ``yaml.safe_dump``/``safe_load`` round-trip
        NaN correctly (the ``.nan`` tag). Enum fields (``injection_mode``,
        ``FrictionModel``, ...) are normalized to plain strings by
        ``_yaml_safe()`` afterward instead, since that's the only other
        thing plain ``model_dump()`` leaves non-YAML-safe.
        """
        components: dict[str, Any] = {}
        for name, component in self._orchestrator.components.items():
            comp_type, comp_variant = _REVERSE_REGISTRY[type(component)]
            # _PROTECTED_COMPONENT_KEYS excluded here for the same reason
            # "common" always was: these are sourced from
            # common:/layout:/sim_config: (single source of truth), not
            # owned by the component's own block — re-emitting them here
            # would round-trip straight into _build_components's guard that
            # forbids a component's own block from setting them.
            dumped = component.model_dump(exclude=set(_PROTECTED_COMPONENT_KEYS))
            components[name] = {"type": comp_type, "variant": comp_variant, **dumped}

        result: dict[str, Any] = {
            "common": self._common.model_dump(),
            "layout": self._layout.model_dump(exclude_none=True),
            "sim_config": self._sim_config.model_dump(exclude_none=True),
            "components": components,
        }
        if self.title is not None:
            result["title"] = self.title
        if self.description is not None:
            result["description"] = self.description.model_dump(exclude_none=True)
        if self._economic is not None:
            # Registry key is ("economic", impl) — the first element is a
            # fixed category label, not a YAML-facing value (unlike physical
            # components, where both tuple elements ARE the YAML-facing
            # values). The economic YAML block's own type field is the
            # SECOND element (e.g. "doublet") — see
            # _build_economic_component()'s docstring for why that field
            # plays the role a physical component's variant field plays.
            _comp_category, comp_impl = _REVERSE_REGISTRY[type(self._economic)]
            result["economic"] = {"type": comp_impl, **self._economic.model_dump()}
        return _yaml_safe(result)

    def to_str(self) -> str:
        """Serialize this Workflow's current live state back to a YAML string."""
        return yaml.safe_dump(self.to_dict(), sort_keys=False)

    def to_file(self, path: Path | str) -> None:
        """Write this Workflow's config to a YAML file at ``path``."""
        Path(path).write_text(self.to_str())

    def run(self) -> None:
        """Execute the full simulation."""
        self._orchestrator.run()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _yaml_safe(obj: Any) -> Any:
    """Recursively normalize a plain ``model_dump()`` result for ``yaml.safe_dump``.

    Plain (non-``mode="json"``) ``model_dump()`` leaves two kinds of
    non-YAML-safe values behind: enum members (``InjectionPolicy``,
    ``FrictionModel``, ``HeatTransferModel``, ...) and numpy scalars
    (``np.float64``/``np.int64``/... -- e.g. a history field populated
    from a numpy array's elements, which are numpy scalars, not plain
    Python ones, even though they print identically) -- everything else
    (plain floats including NaN, str, int, bool, None, nested dict/list)
    is already safe. Converts each enum to its plain ``.value`` string,
    each numpy scalar to its plain Python equivalent via ``.item()``.
    """
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {k: _yaml_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_yaml_safe(v) for v in obj]
    return obj


def _check_common_identity(components: dict[str, FlowComponent], common: Common) -> None:
    """Assert every component's ``common`` (if declared) is this Workflow's SAME instance.

    Called once, at construction time, right after ``_build_components``.
    ``_build_components`` already only ever hands out one shared reference,
    so this should never actually fail under normal use — it exists as a
    structural guarantee (checked once, not re-checked every timestep) that
    every component on a shared flow path (fluid identity, rock/thermal
    parameters) really is looking at the one canonical ``Common``, not an
    equal-but-separate copy that could silently drift. Uses ``is``, not
    ``==``: two separately-constructed ``Common`` instances with identical
    field values would compare equal but must still be rejected here.

    Args:
        components: Just-built components, keyed by YAML name.
        common: This Workflow's canonical, frozen ``Common`` instance.

    Raises:
        ConfigError: If any component's ``common`` is not the same object.

    """
    for name, component in components.items():
        component_common = getattr(component, "common", None)
        if component_common is not None and component_common is not common:
            raise ConfigError(
                f"Component {name!r} does not share this Workflow's single "
                "Common instance (fluid_name, rock/thermal parameters). "
                "Every component on a shared flow path must reference the "
                "exact same object, not an equal-but-separate copy — this "
                "indicates a bug in component construction, not a config error.",
            )


# TESPy component types that add pressure/work to the fluid, PLUS
# "PumpOrValve" (not a real TESPy class -- GraphSurface resolves it to
# either "Valve" or "Compressor" per solve(), building BOTH networks and
# picking whichever is physically valid -- see graph.py's _NetworkBundle)
# -- checked against every power_plant node's raw "type" string, not the
# live TESPy object, so this runs on the parsed config directly (see
# _check_loop_has_pressure_source). A "PumpOrValve" node always counts as
# a pressure source even though its common-case resolution is a passive
# Valve: it always has a real Compressor-resolved leg available and
# checks itself every solve() (GraphSurface._check_pump_or_valve_validity)
# for exactly the "natural pressure ran out" gap this whole check exists
# to reject, so it can never silently regress to unchecked
# thermosiphon-only circulation the way an config with no circulation
# node at all could. "Pump" isn't a real GraphSurface component type
# today (see graph.py's _COMPONENT_TYPES) -- TESPy's Compressor class is
# used to model a liquid pump via its generic pressure-rise abstraction
# (see hydro_df_electric.yml's brine_pump/condensate_pump) -- included here anyway in
# case a dedicated "Pump" type is ever registered, so this check doesn't
# need updating the day that happens.
_PRESSURE_SOURCE_NODE_TYPES = frozenset({"Compressor", "Pump", "PumpOrValve"})


def _check_loop_has_pressure_source(components_cfg: dict[str, dict[str, Any]]) -> None:
    """Require at least one pressure-adding device somewhere in a closed loop.

    Called only when ``sim_config.injection_mode`` is present — i.e. this
    config is a genuine closed circuit (``SystemBCIteration``), not a bare
    open test fixture. Something has to drive circulation around a closed
    loop; relying on thermosiphon effect (the density difference between a
    cold descending leg and a hot ascending leg) alone, with NO mechanical
    fallback anywhere, is not a simplification a real system can get away
    with -- a pump-less closed loop can converge on a design whose
    wellhead pressure sits arbitrarily close to the fluid's own
    saturation pressure, with nothing to fall back on if that margin runs
    out. See TANGO Commandments (CONTRIBUTING.md) for the rule this
    enforces.

    Checks TWO places a pressure source can legitimately live: a well
    component's own ``type`` ending in ``_with_pump`` (the production-side
    downhole pump, e.g. ``hydro_df_electric.yml``), or any
    ``power_plant.nodes`` entry whose ``type`` is in
    ``_PRESSURE_SOURCE_NODE_TYPES`` (a surface circulation pump, or a
    ``PumpOrValve`` node -- see that constant's own docstring for why a
    ``PumpOrValve`` node counts even though it usually resolves to a
    passive ``Valve``). Checks the RAW CONFIG dict, not constructed
    components — cheaper, and avoids reaching into ``GraphSurface``'s
    internal TESPy node objects for something the YAML already states
    directly (see TANGO Commandments' config-is-object rule).

    Scoped to the WHOLE workflow, not per-loop: today there is only ever
    one fluid circuit per ``Workflow`` (no multi-loop/grouped-subsystem
    support yet — see ``docs/TANGO_vision_and_roadmap/README.md``'s "Grouped
    subsystems" open design question), so a whole-workflow check is
    equivalent to a per-loop one. Revisit this scoping once a config can
    genuinely contain more than one independent fluid loop (e.g. a future
    ORC secondary working-fluid loop) — this function would then need to
    check each loop independently rather than the workflow as a whole.

    Args:
        components_cfg: The raw, un-constructed ``components:`` config dict
            (``config["components"]``), keyed by YAML component name.

    Raises:
        ConfigError: If no pressure source is found anywhere in the config.

    """
    for comp_cfg in components_cfg.values():
        if str(comp_cfg.get("type", "")).endswith("_with_pump"):
            return
        for node_cfg in comp_cfg.get("power_plant", {}).get("nodes", {}).values():
            if node_cfg.get("type") in _PRESSURE_SOURCE_NODE_TYPES:
                return
    raise ConfigError(
        "This config forms a closed loop (sim_config.injection_mode is set) but has no "
        "pressure-adding device anywhere -- no well component's type ends in '_with_pump', "
        "and no power_plant.nodes entry is a Compressor/Pump/PumpOrValve. Something must "
        "drive circulation around a closed loop; thermosiphon effect alone (with nothing "
        "mechanical to fall back on) is not a valid substitute -- see TANGO Commandments "
        "(CONTRIBUTING.md) and this function's own docstring for why.",
    )


def _build_economic_component(economic_cfg: dict[str, Any] | None) -> EconomicComponent | None:
    """Build the ``economic:`` block's component, if present.

    Deliberately separate from ``_build_components``: the ``economic:``
    block is not part of the ``components:`` circuit (no ``prev``/``next``,
    no participation in per-timestep ``_ordered``/``_by_idx`` — see
    ``SystemDirect.finalize()``), so it doesn't need ``component_idx`` from
    the user at all; a sentinel value is used since it plays no role in
    solve ordering or stream wiring for this component.

    Uses the same ``(category, implementation)`` registry-key shape as
    physical components' ``(type, variant)``, with the YAML's ``type:``
    field (e.g. ``"doublet"``) playing the role ``variant:`` plays for
    physical components.

    Args:
        economic_cfg: Parsed ``economic:`` YAML block, or ``None``/empty if
            absent (no economic component for this Workflow).

    Returns:
        The built economic component, or ``None`` if ``economic_cfg`` is
        absent/empty.

    Raises:
        ConfigError: If ``type`` is not registered, or construction fails.

    """
    if not economic_cfg:
        return None
    comp_impl: str = economic_cfg.get("type", "doublet")
    key = ("economic", comp_impl)
    cls = COMPONENT_REGISTRY.get(key)
    if cls is None:
        raise ConfigError(
            f"economic: has type={comp_impl!r}, which is not registered in COMPONENT_REGISTRY.",
        )
    own = {k: v for k, v in economic_cfg.items() if k != "type"}
    own.setdefault("component_idx", -1)
    try:
        return cls.from_dict(own)  # type: ignore[return-value]
    except Exception as exc:
        raise ConfigError(f"Failed to build economic component: {exc}") from exc


def _build_components(
    components_block: dict[str, Any],
    common: Common,
    layout: Layout,
    dt_years: float,
    target_extraction_pressure: float,
) -> dict[str, FlowComponent]:
    """Instantiate all components from the ``components:`` YAML block.

    Each component receives:
      (a) a REFERENCE to the same ``common`` instance, if it declares a
          ``common`` field — not a copy. See ``Common``'s docstring
          (core/specs.py) for why this makes divergence structurally
          impossible rather than merely guarded against.
      (b) whichever layout/sim_config-derived fields it declares
          (``well_spacing``, ``dt_years``, ``target_extraction_pressure``)
          — still individually threaded per component, not shared-referenced
          via a single frozen object the way ``common`` is (see
          docs/tango_tasks.md for that scope decision) — but still a
          SINGLE source value copied out to every declaring component at
          construction time, not independently user-supplied per component.
      (c) all keys from its own YAML block.
    Unknown keys in a component's own block raise a Pydantic
    ``ValidationError`` (wrapped as ``ConfigError``) — this is now also how
    a component's own block trying to set e.g. ``rock_k`` gets rejected: it
    simply isn't a field the component declares anymore (only ``common``
    is), an ordinary unknown-key error rather than a special-cased guard.

    A component's own YAML block is also flatly forbidden from setting
    ``common`` or any ``layout_extras`` key (``well_spacing``,
    ``well_pattern``, ``dt_years``, ``target_extraction_pressure``) directly — module-level
    ``_PROTECTED_COMPONENT_KEYS`` is checked generically against every
    component's own block, once, rather than via a hand-written
    ``if key in own: raise`` per field. This is
    deliberate: those per-field checks were added one at a time as each
    duplication bug was found (``common`` first, then
    ``target_extraction_pressure`` — see ``docs/tango_tasks.md``'s
    2026-08-10 entry), and ``well_spacing``/``dt_years`` were caught
    missing this same protection by inspection, not by a bug report — a
    generic check closes that whole class of "forgot to add the guard for
    the next field" gap at once, including for any field added here in the
    future (by a human or an agent authoring new shared config surface).

    Args:
        components_block: Parsed ``components:`` mapping from the input file.
        common: Validated, shared ``common:`` block.
        layout: Validated ``layout:`` block.
        dt_years: Simulation timestep duration (years), from ``sim_config.dt_years``.
        target_extraction_pressure: Minimum required extraction pressure at
            the surface inlet (Pa), from ``sim_config.target_extraction_pressure``.

    Returns:
        Dict of instantiated components keyed by their YAML name.

    """
    layout_extras: dict[str, Any] = {
        "well_spacing": layout.well_spacing,
        "well_pattern": layout.well_pattern,
        "dt_years": dt_years,
        "target_extraction_pressure": target_extraction_pressure,
    }
    # Guards against the two lists (this dict's keys and module-level
    # _LAYOUT_EXTRA_KEYS) drifting apart — the exact "independent copies of
    # the same set of names" mistake this whole mechanism exists to
    # prevent, one level up. Cheap enough to just always check.
    assert set(layout_extras) == set(_LAYOUT_EXTRA_KEYS), (
        f"layout_extras keys {sorted(layout_extras)} != _LAYOUT_EXTRA_KEYS "
        f"{sorted(_LAYOUT_EXTRA_KEYS)} — update both together."
    )

    built: dict[str, FlowComponent] = {}
    for name, comp_cfg in components_block.items():
        comp_type: str = comp_cfg.get("type", "")
        comp_variant: str = comp_cfg.get("variant", "lumped")
        key = (comp_type, comp_variant)

        cls = COMPONENT_REGISTRY.get(key)
        if cls is None:
            raise ConfigError(
                f"Component {name!r} has type={comp_type!r} variant={comp_variant!r}, "
                "which is not registered in COMPONENT_REGISTRY.",
            )

        own = {k: v for k, v in comp_cfg.items() if k not in ("type", "variant")}
        collisions = _PROTECTED_COMPONENT_KEYS & own.keys()
        if collisions:
            raise ConfigError(
                f"Component {name!r} sets {sorted(collisions)!r} in its own YAML "
                "block — these are always sourced from common:/layout:/sim_config: "
                "(shared across every component that declares them) and cannot be "
                "set per-component. See docs/tango_tasks.md's "
                "'common:/component-block override ambiguity' section for the bugs "
                "this generic guard closes.",
            )

        # Build merged dict for this component:
        # - From layout_extras/common: only fields the component actually declares
        #   (avoids flooding every component with irrelevant shared parameters)
        # - From comp_cfg: all keys except routing-only "type" and "variant"
        #   (Pydantic extra="forbid" will catch any unknown keys here)
        declared = set(cls.model_fields.keys())
        shared: dict[str, Any] = {k: v for k, v in layout_extras.items() if k in declared}
        if "common" in declared:
            shared["common"] = common

        # `shared` and `own` are disjoint by construction (the collision check
        # above rejects any protected key in `own`), so this is a plain union,
        # not an override. Re-checked here so the merge can never silently
        # turn into "own wins over shared" if that guard is ever changed.
        overlap = shared.keys() & own.keys()
        assert not overlap, f"shared/own key overlap {sorted(overlap)} for component {name!r}"  # noqa: S101
        merged: dict[str, Any] = shared | own

        # Only validation failures are config errors. Anything raised by the
        # component's init() (property lookups, derived-geometry math, code
        # bugs) propagates unchanged rather than being relabeled as bad input.
        try:
            component = cls.from_dict(merged)
        except ValidationError as exc:
            raise ConfigError(
                f"Failed to build component {name!r} ({comp_type}/{comp_variant}): {exc}",
            ) from exc

        if not isinstance(component, FlowComponent):
            raise ConfigError(
                f"Component {name!r} ({comp_type}/{comp_variant}) has no fluid inlet/outlet, so it can't be "
                "part of the components: circuit (an economic component goes in its own economic: block).",
            )
        built[name] = component
        logger.debug("Built component %r  idx=%d", name, component.component_idx)

    return built
