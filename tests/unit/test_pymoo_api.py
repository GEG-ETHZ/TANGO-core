# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ``tango_core.pymoo_api``'s CLI/config plumbing and its parameter check.

``pymoo_api.py``'s optimization itself is exercised end-to-end by each
``opt_*`` app's smoke test (``test_opt_apps.py``). This file covers the
``termination_period`` CLI <-> ``PymooConfig`` wiring and
``Minimization``'s check that every parameter moves an objective or
constraint, on short (2-timestep) runs of real templates.
"""

from __future__ import annotations

import copy
import logging
import multiprocessing
import pickle
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from tango_core.core.errors import ConfigError, InertParameterError
from tango_core.pymoo_api import (
    Minimization,
    ObjectiveSpec,
    ParamSpec,
    PymooConfig,
    _Problem,
    build_pymoo_parser,
    ideal_distance,
)
from tango_core.workflows.workflow import Workflow

# Frozen scenarios, not templates/: these tests force mass rates and
# bounds that only make sense for a specific design, and the example
# configs' designs change whenever they're re-optimized.
_SCENARIOS = Path(__file__).resolve().parents[1] / "regtest" / "fixtures" / "scenarios"


def test_pymoo_config_termination_period_default_matches_pymoo_default() -> None:
    """``PymooConfig.termination_period`` defaults to 50, matching pymoo's own
    ``DefaultMultiObjectiveTermination``'s ``period`` default -- so a caller
    that never touches this field gets pymoo's own default behavior,
    unchanged.
    """
    assert PymooConfig().termination_period == 50


def test_build_pymoo_parser_exposes_termination_period_flag_with_default() -> None:
    """``--termination-period`` is a real CLI flag, defaulting to
    ``PymooConfig``'s own default when neither ``params.yaml`` nor an
    explicit flag overrides it.
    """
    parser = build_pymoo_parser(description="test", default_output_dir=Path("outputs"))
    args = parser.parse_args([])
    assert args.termination_period == 50


def test_build_pymoo_parser_termination_period_flag_is_overridable() -> None:
    """An explicit CLI flag overrides the default."""
    parser = build_pymoo_parser(description="test", default_output_dir=Path("outputs"))
    args = parser.parse_args(["--termination-period", "10"])
    assert args.termination_period == 10


def test_build_pymoo_parser_termination_period_flag_reads_from_params() -> None:
    """A ``params.yaml``-sourced ``params`` dict overrides ``PymooConfig``'s
    own default (same precedence as every other pymoo hyperparameter here --
    see ``build_pymoo_parser``'s own docstring).
    """
    parser = build_pymoo_parser(
        description="test",
        default_output_dir=Path("outputs"),
        params={"termination_period": 15},
    )
    args = parser.parse_args([])
    assert args.termination_period == 15


@dataclass
class _SetPath:
    """Picklable apply/read pair for one dotted config path."""

    path: tuple[str, ...]

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        target = cfg
        for key in self.path[:-1]:
            target = target[key]
        target[self.path[-1]] = float(value)
        return cfg

    def read(self, cfg: dict[str, Any]) -> float:
        value: Any = cfg
        for key in self.path:
            value = value[key]
        return float(value)


def _param(name: str, path: str, bounds: tuple[float, float], *, with_read: bool = True) -> ParamSpec:
    apply = _SetPath(tuple(path.split(".")))
    return ParamSpec(name=name, apply=apply, bounds=bounds, read=apply.read if with_read else None)


@dataclass
class _Lcoe:
    def __call__(self, wf: Workflow) -> float:
        return float(wf.to_dict()["economic"]["state"]["LCOE"])


def _minimization(config: str, params: list[ParamSpec], tmp_path: Path, **overrides: Any) -> Minimization:
    """A 1-generation, population-2 search on a 2-timestep run of a template."""
    cfg = yaml.safe_load((_SCENARIOS / config).read_text(encoding="utf-8"))
    cfg["sim_config"]["num_tsteps"] = 2
    for path, value in overrides.pop("set", {}).items():
        _SetPath(tuple(path.split(".")))(cfg, value)
    return Minimization(
        base_cfg=cfg,
        params=params,
        objectives=[ObjectiveSpec(name="LCOE", evaluate=_Lcoe())],
        pymoo_config=PymooConfig(n_max_gen=1, pop_size=2, seed=1),
        save_dir=tmp_path,
        **overrides,
    )


_MASS_RATE = ("mass_rate_kg_per_s", "sim_config.mass_rate", (20.0, 40.0))
# AGS's production well has no pump, so target_extraction_pressure is read by
# nothing in AGS_direct_heat.yml: a real inert parameter.
_INERT = ("target_extraction_pressure_Pa", "sim_config.target_extraction_pressure", (5.0e6, 9.0e6))


def test_param_check_passes_live_params(tmp_path: Path) -> None:
    """A parameter that moves LCOE passes the check and the search runs."""
    m = _minimization("AGS_direct_heat.yml", [_param(*_MASS_RATE)], tmp_path)
    m.run()


def test_param_check_raises_on_inert_param_naming_it(tmp_path: Path) -> None:
    """A parameter nothing reads raises InertParameterError naming only that parameter."""
    m = _minimization("AGS_direct_heat.yml", [_param(*_MASS_RATE), _param(*_INERT)], tmp_path)
    with pytest.raises(InertParameterError, match="target_extraction_pressure_Pa") as excinfo:
        m.run()
    assert "mass_rate_kg_per_s" not in str(excinfo.value)


def test_param_check_warns_on_one_sided_dead_param_at_a_bound(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A dead param whose baseline sits on a bound has one testable side, so it warns instead of raising."""
    name, path, _bounds = _INERT
    at_lower_bound = _param(name, path, (7.0e6, 9.0e6))  # AGS_direct_heat.yml sets 7 MPa
    m = _minimization("AGS_direct_heat.yml", [_param(*_MASS_RATE), at_lower_bound], tmp_path)
    with caplog.at_level(logging.WARNING, logger="tango_core.pymoo_api"):
        m._check_param_sensitivity(_Problem(m))  # noqa: SLF001
    assert f"moving {name} up from its lower bound" in caplog.text


def test_param_check_can_be_turned_off(tmp_path: Path) -> None:
    """check_param_sensitivity=False skips the check, so an inert parameter doesn't stop the search."""
    m = _minimization("AGS_direct_heat.yml", [_param(*_INERT)], tmp_path, check_param_sensitivity=False)
    m.run()


def test_param_check_falls_back_to_bounds_midpoint_without_read(tmp_path: Path) -> None:
    """Without ParamSpec.read the baseline is the bounds midpoint, and the check still runs."""
    m = _minimization("AGS_direct_heat.yml", [_param(*_MASS_RATE, with_read=False)], tmp_path)
    assert m._baseline_x()[0] == pytest.approx(30.0)  # noqa: SLF001
    m.run()


def test_param_check_raises_on_infeasible_baseline(tmp_path: Path) -> None:
    """A baseline that fracks the reservoir is a setup error, not something to perturb from."""
    m = _minimization(
        "hydro_sf_electric.yml",
        [_param("mass_rate_kg_per_s", "sim_config.mass_rate", (20.0, 80.0))],
        tmp_path,
        set={"components.surface.injection_pressure": 9.0e6},
    )
    with pytest.raises(ConfigError, match="baseline design .* is infeasible"):
        m.run()


@dataclass
class _NanObjective:
    def __call__(self, wf: Workflow) -> float:
        return float("nan")


def test_non_finite_objective_counts_as_infeasible(tmp_path: Path) -> None:
    """A design whose objective is NaN (e.g. LCOE when net power <= 0) is a constraint violation, not a front member."""
    m = _minimization("AGS_direct_heat.yml", [_param(*_MASS_RATE)], tmp_path)
    m.objectives = [ObjectiveSpec(name="nan", evaluate=_NanObjective())]
    _f, g = m._evaluate_one([30.0])  # noqa: SLF001
    assert g[0] > 0


def test_failures_are_counted_across_worker_processes(tmp_path: Path) -> None:
    """With n_processes > 1, n_failures still counts every infeasible evaluation (counted in the main process)."""
    m = _minimization("AGS_direct_heat.yml", [_param(*_MASS_RATE)], tmp_path, check_param_sensitivity=False)
    m.objectives = [ObjectiveSpec(name="nan", evaluate=_NanObjective())]
    m.pymoo_config.n_processes = 2
    m.run()
    assert m.n_failures == m.pymoo_config.pop_size  # one generation, every design infeasible


def test_worker_pool_is_shut_down_when_run_raises(tmp_path: Path) -> None:
    """run() owns its worker pool, so no worker process outlives a run that raises."""
    m = _minimization("AGS_direct_heat.yml", [_param(*_MASS_RATE), _param(*_INERT)], tmp_path)
    m.pymoo_config.n_processes = 2
    with pytest.raises(InertParameterError):
        m.run()
    assert multiprocessing.active_children() == []


def test_param_check_skips_param_with_no_room(tmp_path: Path) -> None:
    """A param whose bounds leave no room on either side is skipped, not reported as inert."""
    diameter = yaml.safe_load((_SCENARIOS / "AGS_direct_heat.yml").read_text(encoding="utf-8"))["components"][
        "injection_well"
    ]["diameter"]
    pinned = _param("pinned_diameter_m", "components.injection_well.diameter", (diameter, diameter))
    m = _minimization("AGS_direct_heat.yml", [_param(*_MASS_RATE), pinned], tmp_path)
    m._check_param_sensitivity(_Problem(m))  # noqa: SLF001


def test_minimization_pickles_for_worker_processes(tmp_path: Path) -> None:
    """A Minimization on a TESPy (GraphSurface) config pickles, and the copy still evaluates designs.

    ``n_processes > 1`` sends the problem to worker processes by pickling
    it. A TESPy network can't be pickled (its pint units registry holds
    lambdas), so ``Minimization`` must hold only plain data, never a live
    ``Workflow``.
    """
    mass_rate = _param(*_MASS_RATE)
    mgr = _minimization("hydro_ORC_electric.yml", [mass_rate], tmp_path)
    copy = pickle.loads(pickle.dumps(_Problem(mgr)))
    assert not any(isinstance(value, Workflow) for value in vars(copy.mgr).values())
    f, g = copy.mgr._evaluate_one([30.0])  # noqa: SLF001
    assert np.isfinite(f).all()
    assert g[0] <= 0


def test_evaluation_resolves_well_cells_for_its_own_length(tmp_path: Path) -> None:
    """A loop-length param gets the default resolution for the NEW length, not the base design's cell count."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "applications" / "opt_AGS_direct_heat"))
    from opt_AGS_direct_heat import APP  # noqa: PLC0415

    loop_length = next(p for p in APP.param_specs() if p.name == "loop_length_m")
    mgr = _minimization("AGS_direct_heat.yml", [loop_length], tmp_path)
    cfg = loop_length.apply(copy.deepcopy(mgr.base_cfg), 8000.0)
    loop = Workflow(cfg)._orchestrator.components["horizontal_well"]  # noqa: SLF001
    assert loop.num_cells == 40


def test_ideal_distance_is_normalized_distance_to_the_best_of_each_objective() -> None:
    """Each objective counts 0-1 regardless of units; the two ends of a front sit at distance 1."""
    # LCOE and negated power (both minimized), on very different scales.
    f = np.array([[0.5, -1.0e6], [1.0, -2.0e6], [0.75, -1.5e6], [0.6, -1.9e6]])
    np.testing.assert_allclose(
        ideal_distance(f),
        [1.0, 1.0, np.hypot(0.5, 0.5), np.hypot(0.2, 0.1)],
    )


def test_ideal_distance_ignores_how_designs_are_spaced_along_the_front() -> None:
    """Crowding extra designs at one end of the front doesn't change any design's distance."""
    f = np.array([[0.5, -1.0e6], [1.0, -2.0e6], [0.6, -1.9e6]])
    crowded = np.vstack([f, [[0.51, -1.05e6], [0.52, -1.1e6], [0.53, -1.15e6]]])
    np.testing.assert_allclose(ideal_distance(crowded)[:3], ideal_distance(f))


def test_ideal_distance_treats_a_constant_objective_as_zero() -> None:
    """An objective with the same value for every design adds nothing (no division by zero)."""
    np.testing.assert_allclose(ideal_distance(np.array([[1.0, 3.0], [2.0, 3.0]])), [0.0, 1.0])


def test_archive_keeps_every_non_dominated_feasible_design_across_generations(tmp_path: Path) -> None:
    """report_archive's archive holds the non-dominated feasible designs of all generations, once each."""
    from pymoo.core.population import Population  # noqa: PLC0415

    mgr = _minimization("hydro_ORC_electric.yml", [_param(*_MASS_RATE)], tmp_path)

    class _Algorithm:
        off: Population

    algorithm = _Algorithm()
    feasible, infeasible = [[-1.0]], [[1.0]]
    # Generation 1: two non-dominated designs and one infeasible one.
    algorithm.off = Population.new(
        X=np.array([[10.0], [20.0], [30.0]]),
        F=np.array([[1.0, 4.0], [2.0, 3.0], [0.0, 0.0]]),
        G=np.array([*feasible, *feasible, *infeasible]),
    )
    mgr._update_archive(algorithm)  # noqa: SLF001
    # Generation 2: one design dominates [2, 3], one duplicates [1, 4], one extends the front.
    algorithm.off = Population.new(
        X=np.array([[21.0], [11.0], [40.0]]),
        F=np.array([[1.5, 2.5], [1.0, 4.0], [3.0, 1.0]]),
        G=np.array([*feasible, *feasible, *feasible]),
    )
    mgr._update_archive(algorithm)  # noqa: SLF001
    assert mgr._archive_f is not None  # noqa: SLF001
    got = sorted(map(tuple, mgr._archive_f.tolist()))  # noqa: SLF001
    assert got == [(1.0, 4.0), (1.5, 2.5), (3.0, 1.0)]
