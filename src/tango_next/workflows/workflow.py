"""Workflow — top-level entry point for tango_next simulations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from tango_next.components.registry import COMPONENT_REGISTRY
from tango_next.core.component import Component
from tango_next.core.errors import ConfigError
from tango_next.core.policies import InjectionPolicy
from tango_next.orchestrators.system_bc_iteration import SystemBCIteration
from tango_next.orchestrators.system_direct import SystemDirect

logger = logging.getLogger(__name__)


class Workflow:
    """Parses a tango_next input file and drives the simulation.

    Orchestrator is selected automatically from the input file:
      sim_config.injection_mode present  →  SystemBCIteration
      sim_config.injection_mode absent   →  SystemDirect

    Usage::

        wf = Workflow.from_file("examples/tango_next/flexible_SF_manual.yml")
        wf.run()
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Build the orchestrator and components from a parsed config dict."""
        self._config = config
        common: dict[str, Any] = config.get("common", {})
        layout: dict[str, Any] = config.get("layout", {})
        sim_config: dict[str, Any] = config.get("sim_config", {})

        n_tsteps: int = sim_config["num_tsteps"]
        dt_years: float = float(sim_config["dt_years"])
        fluid_name: str = common.get("fluid_name", "Water")

        components = _build_components(config["components"], common, layout, dt_years)

        if "injection_mode" in sim_config:
            policy = InjectionPolicy(
                sim_config.get("injection_mode", InjectionPolicy.MANUAL),
            )
            # AUTO_FLOW / AUTO_BOTH compute mass_rate from fracing_flow() each
            # pass — mass_rate is not prescribed and may be omitted from the YAML.
            if policy in (InjectionPolicy.AUTO_FLOW, InjectionPolicy.AUTO_BOTH):
                mass_rate: float = 0.0
            else:
                mass_rate = float(sim_config["mass_rate"])
            self._orchestrator: SystemBCIteration | SystemDirect = SystemBCIteration(
                components,
                n_tsteps=n_tsteps,
                dt_years=dt_years,
                mass_rate=mass_rate,
                fluid_name=fluid_name,
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
        with p.open() as fh:
            try:
                config: dict[str, Any] = yaml.safe_load(fh)
            except yaml.YAMLError as exc:
                raise ConfigError(f"Failed to parse YAML: {p}\n{exc}") from exc
        logger.info("Loaded input file: %s", p)
        return cls(config)

    def run(self) -> None:
        """Execute the full simulation."""
        self._orchestrator.run()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_components(
    components_block: dict[str, Any],
    common: dict[str, Any],
    layout: dict[str, Any],
    dt_years: float,
) -> dict[str, Component]:
    """Instantiate all components from the ``components:`` YAML block.

    Each component receives: (a) whichever ``common:`` / layout fields it
    explicitly declares as Pydantic fields, and (b) all keys from its own
    YAML block (minus the routing-only ``type`` and ``unit`` keys).
    Component-specific keys take precedence over shared ones.
    Unknown keys in a component's own block raise a Pydantic ``ValidationError``.

    Args:
        components_block: Parsed ``components:`` mapping from the input file.
        common: Parsed ``common:`` mapping (shared fluid/rock parameters).
        layout: Parsed ``layout:`` mapping (well-field geometry, e.g. well_spacing).
        dt_years: Simulation timestep duration (years), from ``sim_config.dt_years``.

    Returns:
        Dict of instantiated components keyed by their YAML name.

    """
    # Pull layout/sim_config fields that some components need at spec construction time
    layout_extras: dict[str, Any] = {
        "well_spacing": layout.get("well_spacing", 707.0),
        "surface_temperature": common.get(
            "surface_temperature",
            components_block.get("surface", {}).get("surface_temperature", 288.0),
        ),
        "dt_years": dt_years,
    }

    built: dict[str, Component] = {}
    for name, comp_cfg in components_block.items():
        comp_type: str = comp_cfg.get("type", "")
        comp_unit: str = comp_cfg.get("unit", "native")
        key = (comp_type, comp_unit)

        cls = COMPONENT_REGISTRY.get(key)
        if cls is None:
            logger.warning(
                "No component registered for type=%r unit=%r — skipping %r.",
                comp_type,
                comp_unit,
                name,
            )
            continue

        # Build merged dict for this component:
        # - From common/layout_extras: only fields the component actually declares
        #   (avoids flooding every component with irrelevant shared parameters)
        # - From comp_cfg: all keys except routing-only "type" and "unit"
        #   (Pydantic extra="forbid" will catch any unknown keys here)
        declared = set(cls.model_fields.keys())
        shared = {k: v for k, v in {**common, **layout_extras}.items() if k in declared}
        own = {k: v for k, v in comp_cfg.items() if k not in ("type", "unit")}
        merged: dict[str, Any] = {**shared, **own}

        try:
            component = cls.from_config(merged)  # type: ignore[attr-defined]
        except Exception as exc:
            raise ConfigError(
                f"Failed to build component {name!r} ({comp_type}/{comp_unit}): {exc}",
            ) from exc

        built[name] = component
        logger.debug("Built component %r  idx=%d", name, component.component_idx)

    return built
