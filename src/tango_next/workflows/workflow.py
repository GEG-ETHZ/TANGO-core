"""Workflow — top-level entry point for tango_next simulations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tango_next.core.errors import ConfigError
from tango_next.orchestrators.system_bc_iteration import SystemBCIteration
from tango_next.orchestrators.system_direct import SystemDirect


class Workflow:
    """Parses a tango_next input file and drives the simulation.

    Orchestrator is selected automatically from the input file:
      schedule.bc_iteration present  →  SystemBCIteration
      schedule.bc_iteration absent   →  SystemDirect
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        schedule: dict[str, Any] = config.get("schedule", {})
        if "bc_iteration" in schedule:
            self._orchestrator: SystemBCIteration | SystemDirect = SystemBCIteration({})
        else:
            self._orchestrator = SystemDirect({})

    @classmethod
    def from_file(cls, path: Path | str) -> Workflow:
        """Load a tango_next YAML input file and construct a Workflow."""
        p = Path(path)
        if not p.exists():
            raise ConfigError(f"Input file not found: {p}")
        with p.open() as fh:
            config: dict[str, Any] = yaml.safe_load(fh)
        return cls(config)

    def run(self) -> None:
        """Execute the full simulation."""
        self._orchestrator.run()
