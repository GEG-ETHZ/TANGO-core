"""A stand-in for RAFT's ``geg_raft.api.RaftModel``, for tests of tango's side of the coupling.

``FakeRaftModel`` honors RAFT's coupling contract (each ``solve`` starts
from the last accepted time; ``get_fresh`` accepts the pending trial) with a
trivial physics stand-in, so tests need neither RAFT nor its mesh.
Installed by the ``fake_raft`` fixture in ``tests/conftest.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class FakeStepStats:
    """Stands in for ``geg_raft.subsurface.StepStats``: one internal timestep spanning the whole trial."""

    attempts: int = 1
    cut_extrapolation: int = 0
    cut_newton: int = 0
    constraint_switches: int = 0
    dt_min_proceeds: int = 0
    dt_accepted: list[float] = field(default_factory=list)
    wall_time: float = 0.0

    @property
    def accepted_steps(self) -> int:
        """Number of internal timesteps taken."""
        return len(self.dt_accepted)


class FakeTimestepError(RuntimeError):
    """Stands in for ``geg_raft.subsurface.TimestepError``."""


class FakeRaftModel:
    """A RAFT stand-in: outlet = inlet + fixed heating and pressure gain; enforces the coupling contract."""

    instances: ClassVar[list[FakeRaftModel]] = []
    flow_factor: ClassVar[float] = 1.0
    outlet_temperature_k: ClassVar[float | None] = None
    fail: ClassVar[bool] = False
    dt_min_proceeds: ClassVar[int] = 0

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
        self.solve_stats = FakeStepStats()
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
        self.solve_stats = FakeStepStats(
            dt_min_proceeds=FakeRaftModel.dt_min_proceeds,
            dt_accepted=[t_end - t_start],
        )
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
