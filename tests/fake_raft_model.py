"""A stand-in for RAFT's ``geg_raft.api.RaftModel``, for tests of tango's side of the coupling.

``FakeRaftModel`` honors RAFT's coupling contract (each ``solve`` starts
from the last accepted time; ``get_fresh`` accepts the pending trial) with a
trivial physics stand-in, so tests need neither RAFT nor its mesh.
Installed by the ``fake_raft`` fixture in ``tests/conftest.py``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import yaml

_ROOT = Path(__file__).resolve().parents[1]
RAFT_TEMPLATE = _ROOT / "templates" / "raft" / "config_example_AGS_coupled_single.yaml"
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


FAKE_REYNOLDS = 1.0e5
"""Reynolds number ``FakeRaftModel`` reports in every well element."""
FAKE_HEAT_TRANSFER_COEFFICIENT = 100.0
"""Well-to-rock heat transfer coefficient (W/(m^2 K)) ``FakeRaftModel`` reports in every well element."""


@dataclass
class FakeWellProfile:
    """Stands in for ``geg_raft.postprocessing.WellProfile``: a node at each alignment point, an element between."""

    s: list[float]
    p: list[float]
    T: list[float]
    s_mid: list[float]
    q: list[float]
    reynolds: list[float]
    heat_transfer_coefficient: list[float]


class FakeTimestepError(RuntimeError):
    """Stands in for ``geg_raft.subsurface.TimestepError``."""


class FakeRaftModel:
    """A RAFT stand-in: outlet = inlet + fixed heating and pressure gain; enforces the coupling contract."""

    instances: ClassVar[list[FakeRaftModel]] = []
    flow_factor: ClassVar[float] = 1.0
    outlet_temperature_k: ClassVar[float | None] = None
    fail: ClassVar[bool] = False
    dt_min_proceeds: ClassVar[int] = 0
    element_flow_factor: ClassVar[float] = 1.0

    def __init__(self, config_name: str, t_start: float, config_dir: Path, verbosity: str) -> None:
        """Read the config tango wrote, as RAFT would."""
        del verbosity
        self.config: dict[str, Any] = yaml.safe_load(
            (Path(config_dir) / config_name).read_text(encoding="utf-8"),
        )
        self.config_name = config_name
        groups = {tuple(g["well"]): g for g in self.config["boundary_conditions"] if "well" in g}
        self.inlet_label = groups[(0, "inlet")]["label"]
        self.outlet_label = groups[(0, "outlet")]["label"]
        self.accepted_time = t_start
        self.pending_time: float | None = None
        self.solves: list[tuple[float, float]] = []
        self.accepted_times: list[float] = []
        self.solve_stats = FakeStepStats()
        alignment = self.config["mesh"]["wells"][0]["alignment"]
        segment_lengths = [math.dist(start, end) for start, end in alignment]
        self.s_nodes = [0.0]
        for length in segment_lengths:
            self.s_nodes.append(self.s_nodes[-1] + length)
        self.pending_profile: FakeWellProfile | None = None
        self.accepted_profile: FakeWellProfile | None = None
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
        P_out = inlet["p"] + FAKE_PRESSURE_GAIN_PA
        s_nodes = self.s_nodes
        fractions = [x / s_nodes[-1] for x in s_nodes]
        n_elements = len(s_nodes) - 1
        self.pending_profile = FakeWellProfile(
            s=list(s_nodes),
            p=[inlet["p"] + f * (P_out - inlet["p"]) for f in fractions],
            T=[inlet["T"] + f * (T_out - inlet["T"]) for f in fractions],
            s_mid=[(a + b) / 2 for a, b in zip(s_nodes, s_nodes[1:], strict=False)],
            q=[-q * FakeRaftModel.element_flow_factor] + [-q] * (n_elements - 1),
            reynolds=[FAKE_REYNOLDS] * n_elements,
            heat_transfer_coefficient=[FAKE_HEAT_TRANSFER_COEFFICIENT] * n_elements,
        )
        return {
            self.inlet_label: {
                "p": inlet["p"],
                "T": inlet["T"],
                "q": -q * FakeRaftModel.flow_factor,
                "mode": "pressure",
            },
            self.outlet_label: {"p": P_out, "T": T_out, "q": q, "mode": "flux"},
        }

    def get_fresh(self) -> None:
        """Accept the pending trial."""
        assert self.pending_time is not None, "nothing to accept"
        self.accepted_time = self.pending_time
        self.accepted_times.append(self.accepted_time)
        self.pending_time = None
        self.accepted_profile = self.pending_profile

    def well_profiles(self) -> list[FakeWellProfile]:
        """The pending trial's profile, else the last accepted one: linear in distance from inlet to outlet."""
        profile = self.pending_profile if self.pending_time is not None else self.accepted_profile
        assert profile is not None, "no solve yet"
        return [profile]
