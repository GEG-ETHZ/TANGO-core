"""The ``raft`` variant of ``grouped_subsurface`` with the real RAFT (optional ``raft`` extra).

Skipped when RAFT isn't installed. One simulated year on RAFT's AGS mesh
takes about two minutes, so this is marked ``slow``; the full 25-year
example is covered by ``test_templates.py``.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
import yaml

from tango.components.well.grouped_subsurface import RaftGroupedSubsurface
from tango.core.constants import YEAR_TO_SECOND
from tango.workflows.workflow import Workflow

pytest.importorskip("geg_raft")

_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.slow
def test_one_year_with_raft_closes_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A year runs, RAFT keeps the loop's mass rate, heats the fluid, and records its work."""
    monkeypatch.chdir(_ROOT)
    cfg: dict[str, Any] = yaml.safe_load(
        (_ROOT / "templates" / "AGS_ORC_electric_raft.yml").read_text(encoding="utf-8"),
    )
    cfg["sim_config"]["num_tsteps"] = 1
    wf = Workflow(cfg)
    wf.run()

    loop = wf._orchestrator.components["grouped_subsurface"]  # noqa: SLF001
    assert isinstance(loop, RaftGroupedSubsurface)
    raft = loop.raft.history
    assert raft.mass_rate_outlet == [30.0]
    assert math.isclose(raft.mass_rate_inlet[0], 30.0, rel_tol=1e-3)
    assert raft.trial_solves[0] >= 1
    assert math.isclose(sum(raft.dt_accepted[0]), YEAR_TO_SECOND, rel_tol=1e-9)
    assert raft.accepted_steps[0] == len(raft.dt_accepted[0])
    loop_length = sum(segment.well_length for segment in loop.segments())
    assert raft.s_nodes[0][0] == 0.0
    assert math.isclose(raft.s_nodes[0][-1], loop_length, rel_tol=1e-9)
    assert math.isclose(raft.P_nodes[0][0], raft.P_inlet[0], rel_tol=1e-9)
    assert math.isclose(raft.T_nodes[0][-1], raft.T_outlet[0], rel_tol=1e-9)
    assert math.isclose(raft.h_nodes[0][-1], loop.history.h_outlet[0], rel_tol=1e-9)
    assert len(raft.mass_rate_elements[0]) == len(raft.s_nodes[0]) - 1
    assert all(math.isclose(q, 30.0, rel_tol=1e-3) for q in raft.mass_rate_elements[0])
    assert raft.T_outlet[0] > raft.T_inlet[0] + 50.0, (
        "8 km of hot rock should heat the loop by far more than 50 K"
    )
    assert loop.history.T_outlet == raft.T_outlet
    assert loop.history.heat_extracted_watts[0] > 0
