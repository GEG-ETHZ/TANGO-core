"""Workflow — top-level entry point for tango_next simulations."""

from __future__ import annotations

import copy
import logging
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from tango_next.components.registry import COMPONENT_REGISTRY
from tango_next.core.component import Component
from tango_next.core.errors import ConfigError
from tango_next.core.policies import InjectionPolicy
from tango_next.core.specs import Common, Layout, SimConfig
from tango_next.orchestrators.system_bc_iteration import SystemBCIteration
from tango_next.orchestrators.system_direct import SystemDirect

logger = logging.getLogger(__name__)

# Reverse of COMPONENT_REGISTRY — every value is a distinct class (checked:
# no two (type, unit) keys map to the same class), so this is a safe,
# unambiguous way to recover the type/unit routing keys for a live
# component instance, needed by Workflow.to_dict() since Component itself
# never stores them (they're routing-only, stripped before construction).
_REVERSE_REGISTRY: dict[type[Component], tuple[str, str]] = {
    cls: key for key, cls in COMPONENT_REGISTRY.items()
}


class Workflow:
    """Parses a tango_next input file and drives the simulation.

    Orchestrator is selected automatically from the input file:
      sim_config.injection_mode present  →  SystemBCIteration
      sim_config.injection_mode absent   →  SystemDirect

    Usage::

        wf = Workflow.from_file("examples/tango_next/flexible_SF_manual.yml")
        wf.run()

    ``from_file``/``from_str``/``to_file``/``to_str``/``to_dict`` are the
    supported (de)serialization surface — one controlled API for load/dump,
    insulated from which YAML library is used underneath.

    There is deliberately no cached "original config dict" anywhere in this
    class (no ``self._config``). Caching the construction-time input lets an
    object and the dict people think it was built from silently drift
    apart: mutate a live component's non-frozen field and a cached dict
    would keep reporting the OLD value forever, with no way to tell they'd
    diverged. Every ``to_dict()`` call instead reconstructs fresh from this
    Workflow's actual current live state — ``common:``/``layout:``/
    ``sim_config:`` from their retained, frozen, canonical ``Common``/
    ``Layout``/``SimConfig`` instances, ``components:`` from each live
    component's own ``model_dump()`` (which, being Pydantic, is inherently
    live — no caching possible). A mutation to a genuinely-mutable field
    (e.g. ``surface.injection_pressure``) is reflected immediately, every
    time.

    Every top-level YAML block has a real schema: ``common:``/``layout:``/
    ``sim_config:`` validate against ``Common``/``Layout``/``SimConfig``
    (core/specs.py); ``components:`` was already validated per-component
    (every Component subclass is its own schema). Unknown keys raise
    ConfigError at load time rather than being silently accepted and never
    read by anything. (``economic:`` is the one deliberate, documented
    exception — a placeholder, no ``EconomicComponent`` consumes it
    yet, so it has no schema of its own and is retained
    verbatim/unvalidated purely so ``to_dict()`` doesn't silently drop it.)

    ``common:`` gets one more guarantee beyond validation: every component
    that needs shared fluid/rock parameters holds a REFERENCE to the same
    ``Common`` instance (Pydantic does not copy nested model fields on
    construction), not an independent copy. ``Common`` is frozen, so
    there's exactly one place these values live and no way for one
    component to silently diverge from another — structurally, not via a
    guard list. See core/specs.py.

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
        """Build the orchestrator and components from a parsed config dict."""
        self.title: str | None = config.get("title")
        # economic: is a Phase 2 placeholder — no EconomicComponent consumes
        # it yet (see AGS_direct_heat.yml's comment). No schema of its own;
        # retained verbatim so to_dict() round-trips it instead of silently
        # dropping it. Remove this passthrough once a real EconomicComponent
        # (and an Economic spec class) exists.
        self._economic_raw: dict[str, Any] = config.get("economic", {})
        try:
            self._common = Common(**config.get("common", {}))
            self._layout = Layout(**config.get("layout", {}))
            self._sim_config = SimConfig(**config.get("sim_config", {}))
        except ValidationError as exc:
            raise ConfigError(f"Invalid config:\n{exc}") from exc

        n_tsteps = self._sim_config.num_tsteps
        dt_years = self._sim_config.dt_years

        components = _build_components(config["components"], self._common, self._layout, dt_years)

        if self._sim_config.injection_mode is not None:
            policy = self._sim_config.injection_mode
            # AUTO_FLOW / AUTO_BOTH compute mass_rate from fracing_flow() each
            # pass — mass_rate is not prescribed and may be omitted from the YAML.
            if policy in (InjectionPolicy.AUTO_FLOW, InjectionPolicy.AUTO_BOTH):
                mass_rate: float = 0.0
            else:
                if self._sim_config.mass_rate is None:
                    raise ConfigError(
                        "sim_config.mass_rate is required unless injection_mode is AUTO_FLOW or AUTO_BOTH.",
                    )
                mass_rate = self._sim_config.mass_rate
            if self._sim_config.bc_checkpoint_idx is None:
                raise ConfigError(
                    "sim_config.bc_checkpoint_idx is required when injection_mode is present.",
                )
            self._orchestrator: SystemBCIteration | SystemDirect = SystemBCIteration(
                components,
                n_tsteps=n_tsteps,
                dt_years=dt_years,
                mass_rate=mass_rate,
                fluid_name=self._common.fluid_name,
                bc_checkpoint_idx=self._sim_config.bc_checkpoint_idx,
                policy=policy,
            )
        else:
            self._orchestrator = SystemDirect(components, n_tsteps=n_tsteps)

    @classmethod
    def from_file(cls, path: Path | str) -> Workflow:
        """Load a tango_next YAML input file and construct a Workflow.

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
            comp_type, comp_unit = _REVERSE_REGISTRY[type(component)]
            dumped = component.model_dump(exclude={"common"})
            components[name] = {"type": comp_type, "unit": comp_unit, **dumped}

        result: dict[str, Any] = {
            "common": self._common.model_dump(),
            "layout": self._layout.model_dump(exclude_none=True),
            "sim_config": self._sim_config.model_dump(exclude_none=True),
            "components": components,
        }
        if self.title is not None:
            result["title"] = self.title
        if self._economic_raw:
            result["economic"] = copy.deepcopy(self._economic_raw)
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

    Plain (non-``mode="json"``) ``model_dump()`` leaves exactly one kind of
    non-YAML-safe value behind: enum members (``InjectionPolicy``,
    ``FrictionModel``, ``HeatTransferModel``, ...) — everything else
    (floats including NaN, str, int, bool, None, nested dict/list) is
    already safe. Converts each enum to its plain ``.value`` string.
    """
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _yaml_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_yaml_safe(v) for v in obj]
    return obj


def _build_components(
    components_block: dict[str, Any],
    common: Common,
    layout: Layout,
    dt_years: float,
) -> dict[str, Component]:
    """Instantiate all components from the ``components:`` YAML block.

    Each component receives:
      (a) a REFERENCE to the same ``common`` instance, if it declares a
          ``common`` field — not a copy. See ``Common``'s docstring
          (core/specs.py) for why this makes divergence structurally
          impossible rather than merely guarded against.
      (b) whichever layout/sim_config-derived fields it declares
          (``well_spacing``, ``dt_years``) — still individually threaded
          per component, not shared-referenced (see
          docs/tango_next_tasks.md for that scope decision).
      (c) all keys from its own YAML block.
    Unknown keys in a component's own block raise a Pydantic
    ``ValidationError`` (wrapped as ``ConfigError``) — this is now also how
    a component's own block trying to set e.g. ``rock_k`` gets rejected: it
    simply isn't a field the component declares anymore (only ``common``
    is), an ordinary unknown-key error rather than a special-cased guard.

    Args:
        components_block: Parsed ``components:`` mapping from the input file.
        common: Validated, shared ``common:`` block.
        layout: Validated ``layout:`` block.
        dt_years: Simulation timestep duration (years), from ``sim_config.dt_years``.

    Returns:
        Dict of instantiated components keyed by their YAML name.

    """
    layout_extras: dict[str, Any] = {
        "well_spacing": layout.well_spacing,
        "dt_years": dt_years,
    }

    built: dict[str, Component] = {}
    for name, comp_cfg in components_block.items():
        comp_type: str = comp_cfg.get("type", "")
        comp_unit: str = comp_cfg.get("unit", "native")
        key = (comp_type, comp_unit)

        cls = COMPONENT_REGISTRY.get(key)
        if cls is None:
            raise ConfigError(
                f"Component {name!r} has type={comp_type!r} unit={comp_unit!r}, "
                "which is not registered in COMPONENT_REGISTRY.",
            )

        own = {k: v for k, v in comp_cfg.items() if k not in ("type", "unit")}
        if "common" in own:
            raise ConfigError(
                f"Component {name!r} sets 'common' in its own YAML block — "
                "common: is always the single shared instance for the whole "
                "Workflow and cannot be set per-component.",
            )

        # Build merged dict for this component:
        # - From layout_extras/common: only fields the component actually declares
        #   (avoids flooding every component with irrelevant shared parameters)
        # - From comp_cfg: all keys except routing-only "type" and "unit"
        #   (Pydantic extra="forbid" will catch any unknown keys here)
        declared = set(cls.model_fields.keys())
        shared: dict[str, Any] = {k: v for k, v in layout_extras.items() if k in declared}
        if "common" in declared:
            shared["common"] = common

        merged: dict[str, Any] = {**shared, **own}

        try:
            component = cls.from_dict(merged)  # type: ignore[attr-defined]
        except Exception as exc:
            raise ConfigError(
                f"Failed to build component {name!r} ({comp_type}/{comp_unit}): {exc}",
            ) from exc

        built[name] = component
        logger.debug("Built component %r  idx=%d", name, component.component_idx)

    return built
