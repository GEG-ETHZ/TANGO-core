# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Time stepping: grid expansion, validation, time weighting, and runs on uneven steps.

See ``tango_core.core.time_stepping``.
"""

from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from tango_core.components.economic.doublet import DoubletEconomicComponent
from tango_core.components.well.base import WellRole, WellSection
from tango_core.components.well.numerical import NumericalWell
from tango_core.core.constants import YEAR_TO_SECOND
from tango_core.core.errors import ConfigError
from tango_core.core.stream import Stream
from tango_core.core.time_stepping import (
    FixedGrid,
    SyncRule,
    TimeHistory,
    TimesGrid,
    TimeStep,
    TimeStepping,
    sync_stream,
    time_weighted_mean,
)
from tango_core.orchestrators.system_direct import _check_external_state_steps
from tango_core.workflows.workflow import Workflow

_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_HYDRO = "hydro_sf_electric.yml"
_AGS = "AGS_ORC_electric_grouped_subsurface.yml"


def _load(name: str) -> dict[str, Any]:
    cfg: dict[str, Any] = yaml.safe_load((_TEMPLATES / name).read_text(encoding="utf-8"))
    return cfg


def _yearly(num_steps: int) -> dict[str, Any]:
    """A fixed grid of ``num_steps`` one-year steps."""
    return {"scheme": "fixed", "step": YEAR_TO_SECOND, "num_steps": num_steps}


def _with_time_stepping(cfg: dict[str, Any], grid: dict[str, Any]) -> dict[str, Any]:
    """Replace the shorthand with a ``time_stepping`` block putting every component on ``grid``."""
    cfg = copy.deepcopy(cfg)
    sim_config = cfg["sim_config"]
    del sim_config["num_tsteps"], sim_config["dt_years"]
    sim_config["time_stepping"] = {
        "subsystems": {"all": {"components": list(cfg["components"]), "grid": grid}},
    }
    return cfg


def _run(cfg: dict[str, Any]) -> Workflow:
    wf = Workflow(cfg)
    wf.run()
    return wf


# ---------------------------------------------------------------------------
# Grids
# ---------------------------------------------------------------------------


def test_fixed_grid_steps_solve_over_exactly_the_configured_length() -> None:
    """Each fixed step's dt is ``step`` itself, not a difference of two times."""
    steps = FixedGrid(scheme="fixed", step=0.1, num_steps=3).steps()  # type: ignore[arg-type]
    assert [s.dt for s in steps] == [0.1, 0.1, 0.1]
    assert [s.index for s in steps] == [0, 1, 2]
    assert steps[-1].t_end == pytest.approx(0.3)


@pytest.mark.parametrize("num_steps", [0, -1])
def test_fixed_grid_rejects_fewer_than_one_step(num_steps: int) -> None:
    """A fixed grid needs at least one step."""
    with pytest.raises(ValidationError, match="num_steps"):
        FixedGrid(scheme="fixed", step=1.0, num_steps=num_steps)  # type: ignore[arg-type]


def test_times_grid_steps_run_from_each_time_to_the_next() -> None:
    """Times are end times, not step lengths; the first step starts at 0."""
    steps = TimesGrid(scheme="times", times=[1.0, 100.0, 1000.0]).steps()  # type: ignore[arg-type]
    assert [(s.t_start, s.dt) for s in steps] == [(0.0, 1.0), (1.0, 99.0), (100.0, 900.0)]


@pytest.mark.parametrize("times", [[1.0, 1.0, 2.0], [2.0, 1.0]])
def test_times_grid_rejects_times_that_do_not_strictly_increase(times: list[float]) -> None:
    """Repeated or decreasing times are a config error."""
    with pytest.raises(ValidationError, match="strictly increase"):
        TimesGrid(scheme="times", times=times)  # type: ignore[arg-type]


def test_subsystems_whose_grids_end_at_different_times_are_rejected() -> None:
    """The project lifetime is where the grids end, so they must all end together."""
    with pytest.raises(ValidationError, match="same time"):
        TimeStepping.model_validate(
            {
                "subsystems": {
                    "a": {"components": ["x"], "grid": {"scheme": "times", "times": [1.0, 5.0]}},
                    "b": {"components": ["y"], "grid": {"scheme": "fixed", "step": 1.0, "num_steps": 4}},
                },
            },
        )


def test_project_lifetime_is_where_the_grid_ends() -> None:
    """``end`` is read off the grid, not given separately."""
    grid = {"scheme": "times", "times": [1.0, 5.0]}
    time_stepping = TimeStepping.model_validate({"subsystems": {"all": {"components": ["a"], "grid": grid}}})
    assert time_stepping.end == 5.0


# ---------------------------------------------------------------------------
# Sync intervals and sync rules
# ---------------------------------------------------------------------------


def _two_subsystems(fine_steps: int, coarse_steps: int, end: float = 2.0) -> TimeStepping:
    """Subsystem ``fine`` and ``coarse`` on fixed grids of the given step counts, both ending at ``end``."""
    return TimeStepping.model_validate(
        {
            "subsystems": {
                "fine": {
                    "components": ["x"],
                    "grid": {"scheme": "fixed", "step": end / fine_steps, "num_steps": fine_steps},
                },
                "coarse": {
                    "components": ["y"],
                    "grid": {"scheme": "fixed", "step": end / coarse_steps, "num_steps": coarse_steps},
                },
            },
        },
    )


def test_one_subsystem_makes_every_step_its_own_interval() -> None:
    """With a single subsystem the run advances one step per interval, as before subsystems existed."""
    grid = {"scheme": "times", "times": [1.0, 3.0, 6.0]}
    intervals = TimeStepping.model_validate(
        {"subsystems": {"all": {"components": ["a"], "grid": grid}}},
    ).intervals()
    assert [(i.t_start, i.t_end) for i in intervals] == [(0.0, 1.0), (1.0, 3.0), (3.0, 6.0)]
    assert [len(i.steps["all"]) for i in intervals] == [1, 1, 1]


def test_sync_intervals_end_at_the_times_every_grid_shares() -> None:
    """A fine grid takes its own steps between the coarse grid's step ends."""
    intervals = _two_subsystems(fine_steps=4, coarse_steps=2).intervals()
    assert [(i.t_start, i.t_end) for i in intervals] == [(0.0, 1.0), (1.0, 2.0)]
    assert [[s.t_end for s in i.steps["fine"]] for i in intervals] == [[0.5, 1.0], [1.5, 2.0]]
    assert [[s.t_end for s in i.steps["coarse"]] for i in intervals] == [[1.0], [2.0]]


def test_grids_with_no_shared_step_end_but_the_last_make_one_interval() -> None:
    """Grids that only meet at the end sync once, at the end."""
    intervals = _two_subsystems(fine_steps=3, coarse_steps=2, end=6.0).intervals()
    assert [(i.t_start, i.t_end) for i in intervals] == [(0.0, 6.0)]


def test_default_rule_holds_into_the_finer_side_and_averages_into_the_coarser() -> None:
    """With no ``sync`` entry, the finer receiver holds and the coarser one averages."""
    time_stepping = _two_subsystems(fine_steps=4, coarse_steps=2)
    assert time_stepping.sync_rule("coarse", "fine") is SyncRule.HOLD
    assert time_stepping.sync_rule("fine", "coarse") is SyncRule.PERIOD_AVERAGE


def test_a_configured_sync_rule_replaces_the_default() -> None:
    """``sync`` sets the rule per edge."""
    time_stepping = _two_subsystems(fine_steps=4, coarse_steps=2).model_copy(
        update={"sync": {"fine -> coarse": SyncRule.HOLD}},
    )
    assert time_stepping.sync_rule("fine", "coarse") is SyncRule.HOLD


@pytest.mark.parametrize("key", ["fine coarse", "fine -> fine", "fine -> nowhere"])
def test_a_sync_key_must_name_two_different_subsystems(key: str) -> None:
    """A malformed or unknown edge is a config error."""
    with pytest.raises(ValidationError, match="must be '<from> -> <to>'"):
        TimeStepping.model_validate(
            {**_two_subsystems(fine_steps=4, coarse_steps=2).model_dump(), "sync": {key: "hold"}},
        )


def _sent(*values: tuple[float, float, float]) -> list[tuple[TimeStep, Stream]]:
    """Sent streams ``(t_start, dt, h)`` with fixed P and mass rate."""
    return [
        (TimeStep(index=k, t_start=t_start, dt=dt), Stream.fresh(h=h, P=1.0e6, mass_rate=10.0))
        for k, (t_start, dt, h) in enumerate(values)
    ]


def test_period_average_weights_each_sent_value_by_its_overlap() -> None:
    """A coarse receiving step gets the time-weighted mean of the fine steps it spans."""
    received = sync_stream(
        SyncRule.PERIOD_AVERAGE,
        _sent((0.0, 1.0, 100.0), (1.0, 3.0, 200.0)),
        TimeStep(index=0, t_start=0.0, dt=4.0),
    )
    assert received.h.get_fresh() == pytest.approx((100.0 * 1.0 + 200.0 * 3.0) / 4.0)
    assert received.P.get_fresh() == 1.0e6
    assert received.mass_rate.get_fresh() == 10.0


def test_hold_passes_on_the_value_that_covers_the_receiving_step_start() -> None:
    """Each fine receiving step gets the coarse value in force when it starts."""
    sent = _sent((0.0, 2.0, 100.0), (2.0, 2.0, 200.0))
    received = [
        sync_stream(SyncRule.HOLD, sent, TimeStep(index=k, t_start=t, dt=1.0)).h.get_fresh()
        for k, t in enumerate([0.0, 1.0, 2.0, 3.0])
    ]
    assert received == [100.0, 100.0, 200.0, 200.0]


@pytest.mark.parametrize("rule", list(SyncRule))
def test_one_sent_value_over_the_same_step_passes_through_unchanged(rule: SyncRule) -> None:
    """On matching grids every rule passes the sent value on exactly, not merely to rounding."""
    h = 0.1 + 0.2  # not exactly representable, so a weighted re-average could round differently
    received = sync_stream(rule, _sent((0.0, 3.0, h)), TimeStep(index=0, t_start=0.0, dt=3.0))
    assert received.h.get_fresh() == h


# ---------------------------------------------------------------------------
# Time weighting
# ---------------------------------------------------------------------------


def test_time_weighted_mean_with_equal_durations_is_the_plain_mean() -> None:
    """Equal durations round exactly like ``sum / len``, so even grids reproduce earlier results."""
    values = [0.1, 0.2, 0.7]
    assert time_weighted_mean(values, [3.0, 3.0, 3.0]) == sum(values) / len(values)


def test_time_weighted_mean_counts_each_value_for_the_time_it_covers() -> None:
    """One short step must not count as much as one long step."""
    assert time_weighted_mean([10.0, 1.0], [1.0, 99.0]) == pytest.approx((10.0 + 99.0) / 100.0)


def test_time_weighted_mean_rejects_misaligned_durations() -> None:
    """Values and durations must pair up one to one."""
    with pytest.raises(ValueError, match="align"):
        time_weighted_mean([1.0, 2.0], [1.0])


def test_economic_net_power_is_time_weighted() -> None:
    """Surface output and downhole pump draw are both averaged by step length, not step count."""
    economic = DoubletEconomicComponent.from_dict(
        {"component_idx": -1, "project_maturity": "green_field", "discount_rate": 0.095},
    )
    assert isinstance(economic, DoubletEconomicComponent)
    durations = [1.0, 99.0]
    surface = SimpleNamespace(
        history=SimpleNamespace(net_power_W=[10.0, 1.0], net_thermal_W=[0.0, 2.0]),
        time_history=TimeHistory(t_start=[0.0, 1.0], dt=durations),
        power_plant={},
        common=SimpleNamespace(surface_temperature=290.0),
        approach_temperature=5.0,
    )
    pump = WellSection(WellRole.PRODUCTION, 1000.0, 0.2, (4.0, 0.0), tuple(durations))
    power_w, thermal_w = economic._read_net_power(surface, {}, [pump])  # type: ignore[arg-type]  # noqa: SLF001
    assert power_w == pytest.approx((10.0 + 99.0) / 100.0 - 4.0 / 100.0)
    assert thermal_w == pytest.approx(2.0 * 99.0 / 100.0)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_shorthand_and_time_stepping_together_are_rejected() -> None:
    """The run's time steps have one source: the shorthand or ``time_stepping``."""
    both = _with_time_stepping(_load(_HYDRO), _yearly(2))
    both["sim_config"]["num_tsteps"] = 2
    with pytest.raises(ConfigError, match="not both"):
        Workflow(both)


def test_missing_time_stepping_is_rejected() -> None:
    """A config with neither the shorthand nor ``time_stepping`` names what to add."""
    cfg = _load(_HYDRO)
    del cfg["sim_config"]["num_tsteps"], cfg["sim_config"]["dt_years"]
    with pytest.raises(ConfigError, match="time_stepping"):
        Workflow(cfg)


def test_every_component_must_be_in_a_subsystem() -> None:
    """A component left out of every subsystem would have no grid."""
    cfg = _with_time_stepping(_load(_HYDRO), _yearly(1))
    left_out = cfg["sim_config"]["time_stepping"]["subsystems"]["all"]["components"].pop()
    with pytest.raises(ConfigError, match=left_out):
        Workflow(cfg)


def test_a_subsystem_may_not_name_an_unknown_component() -> None:
    """A misspelled component name is an error, not silently ignored."""
    cfg = _with_time_stepping(_load(_HYDRO), _yearly(1))
    cfg["sim_config"]["time_stepping"]["subsystems"]["all"]["components"].append("no_such_component")
    with pytest.raises(ConfigError, match="no_such_component"):
        Workflow(cfg)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def test_time_stepping_fixed_grid_matches_the_shorthand_exactly() -> None:
    """The shorthand is one shared fixed grid; spelling that grid out gives the identical run."""
    shorthand = _load(_HYDRO)
    shorthand["sim_config"]["num_tsteps"] = 2
    shorthand["sim_config"]["dt_years"] = 1.0
    spelled_out = _with_time_stepping(shorthand, _yearly(2))
    assert _run(spelled_out).to_dict()["components"] == _run(shorthand).to_dict()["components"]


def test_uneven_steps_advance_the_wells_by_their_own_lengths() -> None:
    """A numerical well's dimensionless time follows the real elapsed time, step by step."""
    times = [0.5 * YEAR_TO_SECOND, 2.0 * YEAR_TO_SECOND]
    wf = _run(_with_time_stepping(_load(_AGS), {"scheme": "times", "times": times}))
    loop = wf._orchestrator.components["grouped_subsurface"]  # noqa: SLF001
    well = loop.injection_well  # type: ignore[attr-defined]
    assert isinstance(well, NumericalWell)
    assert well.history.t_d == pytest.approx([well.t_scaling_factor * t for t in times])
    assert loop.time_history.t_end == pytest.approx(times)


def test_project_lifetime_comes_from_end() -> None:
    """The economics discount over the time where the grid ends, not over a step count."""
    times = [0.5 * YEAR_TO_SECOND, 2.0 * YEAR_TO_SECOND]
    wf = _run(_with_time_stepping(_load(_AGS), {"scheme": "times", "times": times}))
    economic = wf._economic  # noqa: SLF001
    assert isinstance(economic, DoubletEconomicComponent)
    assert economic._total_project_years == pytest.approx(2.0)  # noqa: SLF001


# ---------------------------------------------------------------------------
# Several subsystems: config checks
# ---------------------------------------------------------------------------

_AGS_ORC = "AGS_ORC_electric.yml"
_WELLS = ["injection_well", "horizontal_well", "production_well"]


def _fixed(step_years: float, num_steps: int) -> dict[str, Any]:
    """A fixed grid of ``num_steps`` steps of ``step_years`` years."""
    return {"scheme": "fixed", "step": step_years * YEAR_TO_SECOND, "num_steps": num_steps}


def _with_subsystems(cfg: dict[str, Any], subsystems: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """Replace the shorthand with a ``time_stepping`` block of the given subsystems."""
    cfg = copy.deepcopy(cfg)
    del cfg["sim_config"]["num_tsteps"], cfg["sim_config"]["dt_years"]
    cfg["sim_config"]["time_stepping"] = {"subsystems": subsystems, **extra}
    return cfg


def _wells_and_surface(
    wells_grid: dict[str, Any],
    surface_grid: dict[str, Any],
    **extra: Any,
) -> dict[str, Any]:
    """``templates/AGS_ORC_electric.yml`` with its three wells and its surface plant as two subsystems."""
    return _with_subsystems(
        _load(_AGS_ORC),
        {
            "subsurface": {"components": _WELLS, "grid": wells_grid},
            "surface": {"components": ["surface"], "grid": surface_grid},
        },
        **extra,
    )


def test_a_subsystem_must_be_a_contiguous_run_of_the_circuit() -> None:
    """A subsystem that skips a component of another subsystem is rejected."""
    cfg = _with_subsystems(
        _load(_AGS_ORC),
        {
            "ends": {"components": ["injection_well", "production_well"], "grid": _fixed(1.0, 2)},
            "middle": {"components": ["horizontal_well", "surface"], "grid": _fixed(1.0, 2)},
        },
    )
    with pytest.raises(ConfigError, match="contiguous"):
        Workflow(cfg)


def test_a_sync_rule_for_an_edge_the_circuit_lacks_is_rejected() -> None:
    """A rule for a direction no stream flows in would be silently unused."""
    cfg = _with_subsystems(
        _load(_AGS_ORC),
        {
            "a": {"components": ["injection_well"], "grid": _fixed(1.0, 2)},
            "b": {"components": ["horizontal_well"], "grid": _fixed(1.0, 2)},
            "c": {"components": ["production_well", "surface"], "grid": _fixed(1.0, 2)},
        },
        sync={"a -> c": "hold"},
    )
    with pytest.raises(ConfigError, match="no stream flows that way"):
        Workflow(cfg)


def test_a_sync_rule_into_the_converged_circuit_entry_is_rejected() -> None:
    """With injection_mode set, the circuit entry's inlet is the converged injection stream, not a synced one."""
    cfg = _wells_and_surface(_fixed(0.5, 4), _fixed(1.0, 2), sync={"surface -> subsurface": "hold"})
    with pytest.raises(ConfigError, match="circuit entry"):
        Workflow(cfg)


def test_a_component_with_external_state_takes_one_step_per_interval() -> None:
    """A component whose simulator commits only on accept cannot take several steps before the interval converges."""
    external = SimpleNamespace(keeps_external_state=True, component_idx=0)
    interval = _two_subsystems(fine_steps=4, coarse_steps=2).intervals()[0]
    with pytest.raises(ConfigError, match="one step per sync interval"):
        _check_external_state_steps([("fine", [external])], [interval])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# Several subsystems: runs on templates/AGS_ORC_electric.yml (25 years)
# ---------------------------------------------------------------------------

_SUBSYSTEM_TOLERANCE = 0.01
"""Relative gap allowed between a run with 6-month steps and the 1-year
run, for LCOE and mean net power. Engineering judgment put 2.5% as the
bound; the measured gaps are about 0.6%, so the test holds them to 1%."""


def _lcoe_and_net_power(wf: Workflow) -> tuple[float, float]:
    economic = wf._economic  # noqa: SLF001
    assert isinstance(economic, DoubletEconomicComponent)
    return economic.state.LCOE.get_fresh(), economic.state.net_power_W.get_fresh()


@pytest.fixture(scope="module")
def all_one_year() -> Workflow:
    """Run A: the template as shipped, one subsystem on 1-year steps."""
    return _run(_load(_AGS_ORC))


def test_two_subsystems_on_the_same_grid_match_one_subsystem_exactly(all_one_year: Workflow) -> None:
    """Run B: splitting the circuit into subsystems on identical grids changes nothing, in any recorded value."""
    split = _run(_wells_and_surface(_fixed(1.0, 25), _fixed(1.0, 25)))
    assert split.to_dict()["components"] == all_one_year.to_dict()["components"]
    assert split.to_dict()["economic"] == all_one_year.to_dict()["economic"]


def test_wells_on_six_month_steps_stay_close_to_the_one_year_run(all_one_year: Workflow) -> None:
    """Run C: wells on 6-month steps, surface plant on 1-year steps, each with its own history."""
    mixed = _run(_wells_and_surface(_fixed(0.5, 50), _fixed(1.0, 25)))
    components = mixed._orchestrator.components  # noqa: SLF001
    assert len(components["production_well"].time_history.t_end) == 50
    assert len(components["surface"].time_history.t_end) == 25
    for value, reference in zip(_lcoe_and_net_power(mixed), _lcoe_and_net_power(all_one_year), strict=True):
        assert value == pytest.approx(reference, rel=_SUBSYSTEM_TOLERANCE)


def test_everything_on_six_month_steps_stays_close_to_the_one_year_run(all_one_year: Workflow) -> None:
    """Run D: the whole circuit on 6-month steps, the other end of the error bracket for run C."""
    fine = _run(
        _with_subsystems(
            _load(_AGS_ORC),
            {"all": {"components": [*_WELLS, "surface"], "grid": _fixed(0.5, 50)}},
        ),
    )
    for value, reference in zip(_lcoe_and_net_power(fine), _lcoe_and_net_power(all_one_year), strict=True):
        assert value == pytest.approx(reference, rel=_SUBSYSTEM_TOLERANCE)
