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
      sim_config.bc_iteration present  →  SystemBCIteration
      sim_config.bc_iteration absent   →  SystemDirect

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

        n_tsteps: int = sim_config["time"]["num_tsteps"]
        dt_years: float = float(sim_config["time"]["dt_years"])
        fluid_name: str = common.get("fluid_name", "Water")

        components = _build_components(config["components"], common, layout, dt_years)

        if "bc_iteration" in sim_config:
            policy = InjectionPolicy(
                sim_config["bc_iteration"].get("mode", InjectionPolicy.MANUAL),
            )
            # AUTO_FLOW / AUTO_BOTH compute mass_rate from fracing_flow() each
            # pass — the YAML mass_rate value is only meaningful (and required)
            # for policies where flow rate is user-prescribed.
            if policy in (InjectionPolicy.AUTO_FLOW, InjectionPolicy.AUTO_BOTH):
                mass_rate: float = 0.0
            else:
                mass_rate = float(sim_config["mass_rate"]["value"])
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

    Each component dict is merged with ``common:`` (lowest priority), layout
    fields some components need at construction time, and ``dt_years`` (e.g.
    for components that track dimensionless time across timesteps, such as
    ``NumericalInjectionWell``).  Component-specific keys take precedence
    over all of these.

    Args:
        components_block: Parsed ``components:`` mapping from the input file.
        common: Parsed ``common:`` mapping (shared fluid/rock parameters).
        layout: Parsed ``layout:`` mapping (well-field geometry, e.g. well_spacing).
        dt_years: Simulation timestep duration (years), from ``sim_config.time.dt_years``.

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

        # Merge: common < layout_extras < component-specific (highest priority)
        merged: dict[str, Any] = {**common, **layout_extras, **comp_cfg}

        try:
            component = cls.from_config(merged)  # type: ignore[attr-defined]
        except Exception as exc:
            raise ConfigError(
                f"Failed to build component {name!r} ({comp_type}/{comp_unit}): {exc}",
            ) from exc

        built[name] = component
        logger.debug("Built component %r  idx=%d", name, component.component_idx)

    return built
