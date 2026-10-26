"""Fixtures shared across tests/: a stand-in for RAFT (see ``fake_raft_model``)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fake_raft_model import RAFT_TEMPLATE, FakeRaftModel, FakeTimestepError

import tango.external.raft_wrapper as raft_wrapper

_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fake_raft(monkeypatch: pytest.MonkeyPatch) -> type[FakeRaftModel]:
    """Use ``FakeRaftModel`` instead of RAFT (reset), and run from the repository root (RAFT template paths)."""
    FakeRaftModel.instances = []
    FakeRaftModel.flow_factor = 1.0
    FakeRaftModel.outlet_temperature_k = None
    FakeRaftModel.fail = False
    FakeRaftModel.dt_min_proceeds = 0
    monkeypatch.setattr(raft_wrapper, "_raft_model_class", lambda: FakeRaftModel)
    monkeypatch.setattr(raft_wrapper, "_raft_timestep_error", lambda: FakeTimestepError)
    monkeypatch.chdir(_ROOT)
    return FakeRaftModel


@pytest.fixture
def raft_template(tmp_path: Path) -> Path:
    """A copy of the example's RAFT template pointing at a stand-in mesh file."""
    template = yaml.safe_load(RAFT_TEMPLATE.read_text())
    (tmp_path / "mesh.msh").write_text("stand-in mesh: FakeRaftModel never reads it\n")
    template["mesh"]["file"] = "mesh.msh"
    path = tmp_path / "template.yaml"
    path.write_text(yaml.safe_dump(template))
    return path
