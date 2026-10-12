"""Unit tests for ``tango.pymoo_api``'s CLI/config plumbing and its parameter check.

``pymoo_api.py``'s optimization itself is exercised end-to-end by each
``opt_*`` app's smoke test (``test_opt_apps.py``). This file covers the
``termination_period`` CLI <-> ``PymooConfig`` wiring and
``Minimization``'s check that every parameter moves an objective or
constraint, on short (2-timestep) runs of real example configs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from tango.core.errors import ConfigError, InertParameterError
from tango.pymoo_api import Minimization, ObjectiveSpec, ParamSpec, PymooConfig, _Problem, build_pymoo_parser
from tango.workflows.workflow import Workflow

_EXAMPLE_CONFIGS = Path(__file__).resolve().parents[2] / "example_configs"


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
    """A 1-generation, population-2 search on a 2-timestep run of an example config."""
    cfg = yaml.safe_load((_EXAMPLE_CONFIGS / config).read_text())
    cfg["sim_config"]["num_tsteps"] = 2
    for path, value in overrides.pop("set", {}).items():
        _SetPath(tuple(path.split(".")))(cfg, value)
    return Minimization(
        base_workflow=Workflow(cfg),
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
    assert m.n_failures == 1


def test_param_check_skips_param_with_no_room(tmp_path: Path) -> None:
    """A param whose bounds leave no room on either side is skipped, not reported as inert."""
    pinned = _param("pinned_depth_m", "components.injection_well.well_length", (3000.0, 3000.0))
    m = _minimization("AGS_direct_heat.yml", [_param(*_MASS_RATE), pinned], tmp_path)
    m._check_param_sensitivity(_Problem(m))  # noqa: SLF001
