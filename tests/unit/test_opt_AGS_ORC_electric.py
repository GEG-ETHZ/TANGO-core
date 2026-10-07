"""Smoke test for ``applications/opt_AGS_ORC_electric``: the full optimization runs and writes its results.

Runs the app's real ``build_baseline``/``run_optimization`` with a tiny
population, a single process, a fixed seed, and every decision variable
narrowed to ±1% around its base-YAML value, so every evaluation converges and
the test checks the wiring (param application, objectives, CSV output), not
the physics.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def app() -> ModuleType:
    """The real ``opt_AGS_ORC_electric`` app module.

    Imported via ``sys.path`` + ``import_module`` so its ``ParamSpec``/
    ``ObjectiveSpec`` callables resolve under a real module name.
    """
    app_dir = _REPO_ROOT / "applications/opt_AGS_ORC_electric"
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))
    return importlib.import_module("opt_AGS_ORC_electric")


def _narrow_bounds(app: ModuleType) -> dict[str, tuple[float, float]]:
    """±1% around each decision variable's value in the base workflow's config."""
    base_wf, _ = app.build_baseline()
    cfg = base_wf.to_dict()
    components = cfg["components"]
    nodes = components["surface"]["power_plant"]["nodes"]
    base = {
        "depth_m": components["injection_well"]["well_length"],
        "loop_length_m": components["horizontal_well"]["well_length"],
        "loop_diameter_m": components["horizontal_well"]["diameter"],
        "vertical_well_diameter_m": components["injection_well"]["diameter"],
        "surface_pipe_diameter_m": components["surface"]["pipe_diameter"],
        "injection_pressure_Pa": components["surface"]["injection_pressure"],
        "mass_rate_kg_per_s": cfg["sim_config"]["mass_rate"],
        "orc_feed_pump_pressure_MPa": nodes["orc_feed_pump"]["p_out_megapascals"],
    }
    return {name: (0.99 * float(value), 1.01 * float(value)) for name, value in base.items()}


def test_default_bounds_contain_base_design(app: ModuleType) -> None:
    """The base YAML design point lies inside every production bound."""
    for name, (lo, hi) in _narrow_bounds(app).items():
        default_lo, default_hi = app.DEFAULT_BOUNDS[name]
        assert default_lo <= lo and hi <= default_hi, f"{name}: base value outside {app.DEFAULT_BOUNDS[name]}"


def test_optimization_writes_finite_pareto_csv(app: ModuleType, tmp_path: Path) -> None:
    """A pop-2, 2-generation run finishes and writes one finite column per variable and objective."""
    params = app._param_specs(bounds=_narrow_bounds(app))  # noqa: SLF001
    base_wf, _ = app.build_baseline()
    args = app.build_parser().parse_args(
        [
            "--n-max-gen",
            "2",
            "--pop-size",
            "2",
            "--n-processes",
            "1",
            "--seed",
            "1",
            "--quiet",
            "--save-dir",
            str(tmp_path),
        ],
    )
    _res, _df, m = app.run_optimization(base_wf, args, param_specs=params)

    assert m.n_failures == 0
    results = pd.read_csv(tmp_path / "pareto_results.csv")
    assert len(results) >= 1
    expected = [f"par:{p.name}" for p in params] + [f"obj:{o.name}" for o in app._objective_specs()]  # noqa: SLF001
    for col in expected:
        assert col in results.columns, f"missing column {col}"
    assert np.isfinite(results[expected].to_numpy(dtype=float)).all()
