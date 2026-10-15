"""A stand-in for RAFT's ``raft.api.RaftModel``, for tests of tango's side of the coupling.

``FakeRaftModel`` honors RAFT's coupling contract (each ``solve`` starts
from the last accepted time; ``get_fresh`` accepts the pending trial) with a
trivial physics stand-in, so tests need neither RAFT nor its mesh (stored
with DVC). Installed by the ``fake_raft`` fixture in ``tests/conftest.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import yaml

_ROOT = Path(__file__).resolve().parents[1]
RAFT_TEMPLATE = _ROOT / "example_configs" / "raft" / "config_example_AGS_coupled_single.yaml"
"""The RAFT example's config template."""

FAKE_HEATING_K = 60.0
"""Temperature rise (K) ``FakeRaftModel`` gives the fluid."""
FAKE_PRESSURE_GAIN_PA = 1.0e6
"""Pressure rise (Pa) ``FakeRaftModel`` gives the fluid."""


class FakeTimestepError(RuntimeError):
    """Stands in for ``raft.subsurface.TimestepError``."""


class FakeRaftModel:
    """A RAFT stand-in: outlet = inlet + fixed heating and pressure gain; enforces the coupling contract."""

    instances: ClassVar[list[FakeRaftModel]] = []
    flow_factor: ClassVar[float] = 1.0
    outlet_temperature_k: ClassVar[float | None] = None
    fail: ClassVar[bool] = False

    def __init__(self, config_name: str, t_start: float, config_dir: Path, verbosity: str) -> None:
        """Read the config tango wrote, as RAFT would."""
        del verbosity
        self.config: dict[str, Any] = yaml.safe_load((Path(config_dir) / config_name).read_text())
        groups = {tuple(g["well"]): g for g in self.config["boundary_conditions"] if "well" in g}
        self.inlet_label = groups[(0, "inlet")]["label"]
        self.outlet_label = groups[(0, "outlet")]["label"]
        self.accepted_time = t_start
        self.pending_time: float | None = None
        self.solves: list[tuple[float, float]] = []
        self.accepted_times: list[float] = []
        FakeRaftModel.instances.append(self)

    def solve(
        self,
        t_start: float,
        t_end: float,
        bcs: dict[str, dict[str, float]],
    ) -> dict[str, dict[str, Any]]:
        """Return the stand-in outlet; a trial must start from the accepted state."""
        assert t_start == self.accepted_time, "a trial must start from the accepted state"
        if FakeRaftModel.fail:
            raise FakeTimestepError("forced")
        self.solves.append((t_start, t_end))
        self.pending_time = t_end
        inlet = bcs[self.inlet_label]
        q = bcs[self.outlet_label]["q"]
        T_out = FakeRaftModel.outlet_temperature_k or inlet["T"] + FAKE_HEATING_K
        return {
            self.inlet_label: {
                "p": inlet["p"],
                "T": inlet["T"],
                "q": -q * FakeRaftModel.flow_factor,
                "mode": "pressure",
            },
            self.outlet_label: {"p": inlet["p"] + FAKE_PRESSURE_GAIN_PA, "T": T_out, "q": q, "mode": "flux"},
        }

    def get_fresh(self) -> None:
        """Accept the pending trial."""
        assert self.pending_time is not None, "nothing to accept"
        self.accepted_time = self.pending_time
        self.accepted_times.append(self.accepted_time)
        self.pending_time = None
