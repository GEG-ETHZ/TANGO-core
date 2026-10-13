"""Smoke tests for every ``applications/opt_*`` app built on ``tango.pymoo_api.OptApp``.

Each app's real ``APP`` runs a full optimization with its own ``--smoke``
settings (tiny population, any relaxed constraints), a single process, a fixed
seed, and every decision variable narrowed to ±1%
around its value in the app's own example config, so every evaluation
converges and the test checks the wiring (param application, objectives,
reports, CSV output, plots), not the physics. The optimization runs take
several minutes together, so they're marked slow; the bounds and round-trip
checks run by default.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

from tango.pymoo_api import OptApp
from tango.workflows.workflow import Workflow

_APPLICATIONS_DIR = Path(__file__).resolve().parents[2] / "applications"
_APP_NAMES = sorted(
    p.parent.name
    for p in _APPLICATIONS_DIR.glob("opt_*/opt_*.py")
    if p.stem == p.parent.name and "APP = OptApp(" in p.read_text()
)


def _load(name: str) -> OptApp:
    """Import ``applications/<name>/<name>.py`` as a real top-level module and return its ``APP``.

    A real import (not a file-loaded module under a synthetic name), so its
    ``ParamSpec``/``ObjectiveSpec`` callables pickle by module name.
    """
    app_dir = str(_APPLICATIONS_DIR / name)
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    module: ModuleType = importlib.import_module(name)
    app: OptApp = module.APP
    return app


def _narrow_bounds(app: OptApp) -> dict[str, tuple[float, float]]:
    """±1% around each decision variable's value in the app's base config."""
    cfg = Workflow(app.base_config()).to_dict()
    bounds = {}
    for spec in app.param_specs():
        assert spec.read is not None, f"{spec.name} has no read()"
        value = spec.read(cfg)
        bounds[spec.name] = (value - 0.01 * abs(value), value + 0.01 * abs(value))
    return bounds


@pytest.mark.parametrize("name", _APP_NAMES)
def test_default_bounds_contain_base_design(name: str) -> None:
    """Each app's example-config design point lies inside its production bounds."""
    app = _load(name)
    cfg = Workflow(app.base_config()).to_dict()
    for spec in app.param_specs():
        assert spec.read is not None, f"{spec.name} has no read()"
        value = spec.read(cfg)
        lo, hi = spec.bounds
        assert lo <= value <= hi, f"{name}: {spec.name}={value} outside {spec.bounds}"


@pytest.mark.parametrize("name", _APP_NAMES)
def test_param_apply_round_trips(name: str) -> None:
    """Applying a value to a config and reading it back returns the same value."""
    app = _load(name)
    cfg = app.base_config()
    for spec in app.param_specs():
        lo, hi = spec.bounds
        value = lo + 0.37 * (hi - lo)
        cfg = spec.apply(cfg, value)
        assert spec.read is not None
        assert spec.read(cfg) == pytest.approx(value), f"{name}: {spec.name}"


@pytest.mark.slow
@pytest.mark.parametrize("name", _APP_NAMES)
def test_optimization_writes_finite_pareto_csv_and_plots(name: str, tmp_path: Path) -> None:
    """A ``--smoke`` run finishes, writes finite results, and plots from them."""
    app = _load(name)
    params = app.param_specs(_narrow_bounds(app))
    args = app.parse_args(
        ["--smoke", "--n-processes", "1", "--seed", "1", "--quiet", "--save-dir", str(tmp_path)],
    )
    _res, df, m = app.run_optimization(args, param_specs=params)

    assert m.n_failures == 0
    results = pd.read_csv(tmp_path / "pareto_results.csv")
    assert len(results) >= 1
    expected = (
        [f"par:{p.name}" for p in params]
        + [f"obj:{o.name}" for o in app.objective_specs]
        + [f"rep:{r.name}" for r in app.report_specs]
    )
    for col in expected:
        assert col in results.columns, f"{name}: missing column {col}"
    assert np.isfinite(results[expected].to_numpy(dtype=float)).all()

    app.make_plots(df, tmp_path)
    for plot in ("pareto_parallel_coordinates.png", "pareto_scatter.png", "pareto_scatter_by_param.png"):
        assert (tmp_path / plot).exists(), f"{name}: {plot} not written"


def test_smoke_refuses_default_outputs_dir() -> None:
    """--smoke without a throwaway --save-dir would overwrite the app's DVC-tracked outputs/."""
    app = _load(_APP_NAMES[0])
    with pytest.raises(SystemExit):
        app.parse_args(["--smoke"])
