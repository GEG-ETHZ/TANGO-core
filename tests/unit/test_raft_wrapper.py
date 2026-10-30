# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""``RaftWrapper`` and the ``raft`` variant of ``grouped_subsurface``, against a stand-in for RAFT.

``FakeRaftModel`` honors ``geg_raft.api.RaftModel``'s coupling contract (each
``solve`` starts from the last accepted time; ``get_fresh`` accepts the
pending trial) with a trivial physics stand-in, so these tests need neither
RAFT nor its mesh (stored with DVC). The real RAFT is exercised in
``tests/regtest/test_raft_integration.py``.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from fake_raft_model import (
    FAKE_HEAT_TRANSFER_COEFFICIENT,
    FAKE_HEATING_K,
    FAKE_PRESSURE_GAIN_PA,
    FAKE_REYNOLDS,
    RAFT_TEMPLATE,
    FakeRaftModel,
)

import tango_core.external.raft_wrapper as raft_wrapper
from tango_core.components.well.grouped_subsurface import RaftGroupedSubsurface
from tango_core.core.errors import ConfigError, ConvergenceError, SaturationError
from tango_core.workflows.workflow import Workflow

_ROOT = Path(__file__).resolve().parents[2]
_RAFT_CONFIG = _ROOT / "templates" / "AGS_ORC_electric_raft.yml"
_YEAR_SECONDS = 31_536_000.0


@pytest.fixture(autouse=True)
def _use_fake_raft(fake_raft: type[FakeRaftModel]) -> None:
    """Every test here runs against ``FakeRaftModel`` (see tests/conftest.py)."""


@pytest.fixture
def config(raft_template: Path) -> dict[str, Any]:
    """The RAFT template (3 timesteps), using ``raft_template``."""
    cfg: dict[str, Any] = yaml.safe_load(_RAFT_CONFIG.read_text(encoding="utf-8"))
    cfg["sim_config"]["num_tsteps"] = 3
    cfg["components"]["grouped_subsurface"]["raft"]["template"] = str(raft_template)
    return cfg


def _run(cfg: dict[str, Any], num_tsteps: int) -> RaftGroupedSubsurface:
    cfg["sim_config"]["num_tsteps"] = num_tsteps
    wf = Workflow(cfg)
    wf.run()
    loop = wf._orchestrator.components["grouped_subsurface"]  # noqa: SLF001
    assert isinstance(loop, RaftGroupedSubsurface)
    return loop


def test_raft_config_is_the_template_plus_what_tango_owns(
    config: dict[str, Any],
    raft_template: Path,
) -> None:
    """Well size, coupling BCs and output come from tango; everything else is the template's."""
    _run(config, num_tsteps=1)
    raft_config = FakeRaftModel.instances[0].config
    template = yaml.safe_load(RAFT_TEMPLATE.read_text(encoding="utf-8"))
    assert raft_config["material"]["wells"]["diameter"] == [0.311]
    assert raft_config["material"]["wells"]["roughness"] == [5.5e-5]
    groups = {tuple(g["well"]): g for g in raft_config["boundary_conditions"] if "well" in g}
    # Mass flow and temperature in at the inlet, pressure at the outlet.
    assert groups[(0, "inlet")]["hydraulics"] == {"type": "flux", "function": "external"}
    assert groups[(0, "inlet")]["thermal"] == {"type": "temperature", "function": "external"}
    assert groups[(0, "outlet")]["hydraulics"] == {"type": "pressure", "function": "external"}
    assert "thermal" not in groups[(0, "outlet")]
    assert Path(raft_config["mesh"]["file"]) == raft_template.parent / "mesh.msh"
    assert raft_config["material"]["solid"] == template["material"]["solid"]
    assert raft_config["material"]["fluid"] == template["material"]["fluid"]
    assert raft_config["simulation"]["timestep_max"] == template["simulation"]["timestep_max"]


def test_each_timestep_is_accepted_once_after_its_last_trial(config: dict[str, Any]) -> None:
    """Every trial starts from the accepted state; one accept per timestep; trial count recorded."""
    loop = _run(config, num_tsteps=3)
    model = FakeRaftModel.instances[0]
    assert model.accepted_times == [_YEAR_SECONDS, 2 * _YEAR_SECONDS, 3 * _YEAR_SECONDS]
    trials_per_year = [sum(1 for start, _ in model.solves if start == k * _YEAR_SECONDS) for k in range(3)]
    assert loop.raft.history.trial_solves == [float(n) for n in trials_per_year]
    assert all(n >= 1 for n in trials_per_year)


def test_state_records_raft_values_and_loop_outlet_follows_them(config: dict[str, Any]) -> None:
    """RAFT's raw inlet/outlet values are recorded, and the loop's outlet is RAFT's."""
    loop = _run(config, num_tsteps=2)
    raft_history = loop.raft.history
    assert raft_history.mass_rate_inlet == [30.0, 30.0]
    assert raft_history.mass_rate_outlet == [30.0, 30.0]
    for t in range(2):
        assert raft_history.T_outlet[t] == pytest.approx(raft_history.T_inlet[t] + FAKE_HEATING_K)
        assert raft_history.P_outlet[t] == pytest.approx(raft_history.P_inlet[t] + FAKE_PRESSURE_GAIN_PA)
        assert loop.history.T_outlet[t] == raft_history.T_outlet[t]
        assert loop.history.P_outlet[t] == raft_history.P_outlet[t]
        assert loop.history.heat_extracted_watts[t] > 0
    assert all(seconds >= 0 for seconds in raft_history.solve_seconds)


def test_production_pressure_is_set_and_raft_solves_the_injection_pressure(config: dict[str, Any]) -> None:
    """Outlet at target_extraction_pressure; RAFT's inlet pressure is the loop's and the surface plant's injection pressure."""
    wf = Workflow(config)
    wf.run()
    loop = wf._orchestrator.components["grouped_subsurface"]  # noqa: SLF001
    surface = wf._orchestrator.components["surface"]  # noqa: SLF001
    assert isinstance(loop, RaftGroupedSubsurface)
    target = config["sim_config"]["target_extraction_pressure"]
    model = FakeRaftModel.instances[0]
    # tango sends the target as the outlet's pressure condition...
    assert loop.raft.history.P_outlet == pytest.approx([target] * len(loop.history.P_outlet), rel=1e-12)
    for t in range(len(loop.history.P_outlet)):
        # ...FakeRaftModel solves the inlet pressure as the outlet's minus its fixed gain...
        P_inj = target - FAKE_PRESSURE_GAIN_PA
        assert loop.raft.history.P_inlet[t] == pytest.approx(P_inj, rel=1e-12)
        assert loop.history.P_inlet[t] == loop.raft.history.P_inlet[t]
        assert loop.history.P_outlet[t] == pytest.approx(target, rel=1e-12)
        # ...and the surface plant delivers that injection pressure.
        assert surface.history.P_outlet[t] == pytest.approx(P_inj, rel=1e-9)
    assert model.solves, "RAFT was never called"


def test_state_records_raft_step_stats_of_the_accepted_trial(config: dict[str, Any]) -> None:
    """RAFT's ``solve_stats`` for each timestep's accepted trial are recorded."""
    loop = _run(config, num_tsteps=2)
    raft_history = loop.raft.history
    assert raft_history.accepted_steps == [1.0, 1.0]
    assert raft_history.attempts == [1.0, 1.0]
    assert raft_history.dt_min_proceeds == [0.0, 0.0]
    assert raft_history.dt_accepted == [[_YEAR_SECONDS], [_YEAR_SECONDS]]


def test_state_records_the_accepted_well_profile(config: dict[str, Any]) -> None:
    """Each timestep records RAFT's profile along the well, enthalpy included, from inlet to outlet."""
    loop = _run(config, num_tsteps=2)
    raft_history = loop.raft.history
    lengths = [segment.well_length for segment in loop.segments()]
    s_corners = [0.0, lengths[0], lengths[0] + lengths[1], sum(lengths)]
    for t in range(2):
        assert raft_history.s_nodes[t] == pytest.approx(s_corners)
        assert raft_history.P_nodes[t][0] == raft_history.P_inlet[t]
        assert raft_history.P_nodes[t][-1] == raft_history.P_outlet[t]
        assert raft_history.T_nodes[t][0] == raft_history.T_inlet[t]
        assert raft_history.T_nodes[t][-1] == raft_history.T_outlet[t]
        assert raft_history.h_nodes[t][-1] == pytest.approx(loop.history.h_outlet[t])
        assert raft_history.h_nodes[t] == sorted(raft_history.h_nodes[t])
        assert raft_history.s_elements[t] == pytest.approx(
            [(a + b) / 2 for a, b in zip(s_corners, s_corners[1:])],
        )
        assert raft_history.mass_rate_elements[t] == [30.0] * 3
        assert raft_history.reynolds_elements[t] == [FAKE_REYNOLDS] * 3
        assert raft_history.heat_transfer_coefficient_elements[t] == [FAKE_HEAT_TRANSFER_COEFFICIENT] * 3


@pytest.mark.parametrize(("factor", "raises"), [(1.0005, False), (1.002, True)])
def test_element_flow_off_the_mass_rate_raises(config: dict[str, Any], factor: float, raises: bool) -> None:
    """An element carrying more than ``_MASS_RATE_REL_TOL`` off the loop's mass rate is a ConfigError."""
    FakeRaftModel.element_flow_factor = factor
    if raises:
        with pytest.raises(ConfigError, match="element at s = "):
            _run(config, num_tsteps=1)
    else:
        _run(config, num_tsteps=1)


def test_step_accepted_at_timestep_min_above_tolerance_raises(config: dict[str, Any]) -> None:
    """A step RAFT accepted at ``timestep_min`` despite its error is a ConvergenceError, not a silent pass."""
    FakeRaftModel.dt_min_proceeds = 1
    with pytest.raises(ConvergenceError, match="timestep_min"):
        _run(config, num_tsteps=1)


def test_config_round_trips(config: dict[str, Any], raft_template: Path) -> None:
    """``to_dict()`` keeps the ``raft:`` block and loads back."""
    wf = Workflow(config)
    dumped = wf.to_dict()
    assert dumped["components"]["grouped_subsurface"]["raft"]["template"] == str(raft_template)
    assert Workflow(copy.deepcopy(dumped)).to_dict() == dumped


@pytest.mark.parametrize(
    ("key", "value", "match"),
    [
        ("rock_k", 2.1, "therm_cond"),
        ("rock_density", 2650.0, "density"),
        ("surface_temperature", 284.15, "T_ini"),
        ("thermal_gradient", 0.03, "T_grad"),
    ],
)
def test_template_must_agree_with_the_site(
    config: dict[str, Any],
    key: str,
    value: float,
    match: str,
) -> None:
    """A tango site value that differs from the template's is a ConfigError naming the template key."""
    config["common"][key] = value
    with pytest.raises(ConfigError, match=match):
        Workflow(config)


def test_geometry_must_match_the_template_alignment(config: dict[str, Any]) -> None:
    """Changing a well length away from the template's alignment asks for a new mesh."""
    config["components"]["grouped_subsurface"]["injection_well"]["well_length"] = 5000.0
    with pytest.raises(ConfigError, match="new mesh"):
        Workflow(config)


def test_segments_must_share_diameter(config: dict[str, Any]) -> None:
    """RAFT models one well, so a segment with its own diameter is a ConfigError."""
    config["components"]["grouped_subsurface"]["horizontal_well"]["diameter"] = 0.25
    with pytest.raises(ConfigError, match="same diameter"):
        Workflow(config)


def test_unsupported_fluid_is_rejected(config: dict[str, Any]) -> None:
    """Only fluids with a RAFT fluid_type mapping are accepted."""
    template = yaml.safe_load(RAFT_TEMPLATE.read_text(encoding="utf-8"))
    common = Workflow(config)._common.model_copy(update={"fluid_name": "CO2"})  # noqa: SLF001
    with pytest.raises(ConfigError, match="fluid_name"):
        raft_wrapper._check_site(template, common, str(RAFT_TEMPLATE))  # noqa: SLF001


def test_flow_lost_in_the_well_is_an_error(config: dict[str, Any]) -> None:
    """RAFT reporting a different inlet flow than the loop's mass rate is a ConfigError."""
    FakeRaftModel.flow_factor = 0.9
    with pytest.raises(ConfigError, match="constant along a sealed loop"):
        _run(config, num_tsteps=1)


def test_boiling_outlet_is_an_error(config: dict[str, Any]) -> None:
    """An outlet above saturation can't come from RAFT's single-phase model."""
    FakeRaftModel.outlet_temperature_k = 700.0
    with pytest.raises(SaturationError):
        _run(config, num_tsteps=1)


def test_raft_convergence_failure_becomes_a_tango_convergence_error(config: dict[str, Any]) -> None:
    """RAFT's TimestepError surfaces as tango's ConvergenceError."""
    FakeRaftModel.fail = True
    with pytest.raises(ConvergenceError, match="RAFT failed to converge"):
        _run(config, num_tsteps=1)


def test_missing_mesh_points_at_dvc(config: dict[str, Any], raft_template: Path) -> None:
    """The mesh is only needed once RAFT starts; if it's absent, the error says to `dvc pull`."""
    (raft_template.parent / "mesh.msh").unlink()
    wf = Workflow(config)
    with pytest.raises(ConfigError, match="dvc pull"):
        wf.run()


def test_missing_raft_gives_the_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the optional extra, starting RAFT says how to install it."""
    monkeypatch.undo()
    monkeypatch.setitem(sys.modules, "geg_raft.api", None)
    with pytest.raises(ConfigError, match="setup-raft"):
        raft_wrapper._raft_model_class()  # noqa: SLF001


@pytest.mark.parametrize(
    ("P", "T", "is_liquid"),
    [
        (1.0e6, 400.0, True),  # compressed liquid below the critical pressure
        (1.0e6, 500.0, False),  # boiling at 1 MPa (saturation ~453 K)
        (3.0e7, 500.0, True),  # above the critical pressure, below the critical temperature: can't boil
        (3.0e7, 700.0, False),  # supercritical
    ],
)
def test_liquid_check_handles_pressures_above_critical(P: float, T: float, is_liquid: bool) -> None:
    """Deep well nodes sit above water's critical pressure, where there is no saturation temperature."""
    if is_liquid:
        raft_wrapper._check_liquid("H2O", P, T, "HEOS")  # noqa: SLF001
    else:
        with pytest.raises(SaturationError):
            raft_wrapper._check_liquid("H2O", P, T, "HEOS")  # noqa: SLF001


def test_raft_writes_no_vtks_and_keeps_nothing_by_default(config: dict[str, Any]) -> None:
    """Without set_output_dir, RAFT's VTKs are off and its output directory is temporary."""
    _run(config, num_tsteps=1)
    raft_config = FakeRaftModel.instances[0].config
    assert raft_config["simulation"]["output_vtk"] == 0
    assert Path(raft_config["simulation"]["output_directory"]).name == "output"


def test_output_dir_keeps_raft_output_at_the_template_settings(
    config: dict[str, Any],
    tmp_path: Path,
) -> None:
    """set_output_dir points RAFT's output at that directory and keeps the template's output_vtk."""
    wf = Workflow(config)
    loop = wf._orchestrator.components["grouped_subsurface"]  # noqa: SLF001
    assert isinstance(loop, RaftGroupedSubsurface)
    target = tmp_path / "run.raft"
    loop.raft.set_output_dir(target)
    wf.run()
    model = FakeRaftModel.instances[0]
    raft_config = model.config
    template = yaml.safe_load(RAFT_TEMPLATE.read_text(encoding="utf-8"))
    # RAFT writes into <output_directory>/<config file stem>/, i.e. target.
    assert Path(raft_config["simulation"]["output_directory"]) == target.parent.resolve()
    assert model.config_name == "run.raft.yaml"
    assert raft_config["simulation"]["output_vtk"] == template["simulation"]["output_vtk"]
    with pytest.raises(RuntimeError, match="before RAFT starts"):
        loop.raft.set_output_dir(tmp_path / "late.raft")
