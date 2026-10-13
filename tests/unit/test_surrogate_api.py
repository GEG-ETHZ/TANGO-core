"""Fast, no-subprocess smoke test for ``tango.surrogate_api``'s pipeline.

Exercises every stage (LHS sampling -> real-sim sweep -> surrogate training ->
surrogate-driven NSGA2 -> real-sim validation) against
``opt_hydro_df_electric``'s real ``APP`` (decision variables, objectives,
baseline) with tiny sample/pop/gen counts. Checks
schema/shape/plumbing correctness only — a handful of LHS samples is nowhere
near enough for a genuinely accurate surrogate, so ``tolerance`` in the
validation step is left deliberately loose (this is not a surrogate-quality
test, same spirit as the existing tiny ``--n-max-gen 2 --pop-size 6`` CLI
smoke calls in ``just apps``).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tango.pymoo_api import PymooConfig
from tango.surrogate_api import (
    SurrogateValidationError,
    classifier_diagnostics_df,
    corrected_pareto_front,
    diagnostics_df,
    generate_lhs_samples,
    run_lhs_sweep,
    run_surrogate_optimization,
    train_surrogate,
    validate_surrogate_pareto,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_opt_hydro_df_electric() -> ModuleType:
    """Import ``opt_hydro_df_electric.py`` as a real top-level module.

    ``sys.path`` + a plain ``import_module`` (NOT ``importlib.util.spec_from_file_location``
    registered under a synthetic name) — ``run_lhs_sweep``'s ``multiprocessing``
    ``spawn`` workers need to unpickle this module's ``ParamSpec``/``ObjectiveSpec``
    instances in a FRESH interpreter, which requires ``import opt_hydro_df_electric``
    to actually resolve there too; a file-loaded module stashed only in the parent's
    ``sys.modules`` under a name with no real import path hangs the spawned pool
    instead of raising (confirmed the hard way — the first version of this test hung
    the whole run rather than failing fast).
    """
    app_dir = _REPO_ROOT / "applications/opt_hydro_df_electric"
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))
    return importlib.import_module("opt_hydro_df_electric")


@pytest.fixture(scope="module")
def app() -> ModuleType:
    """The real ``opt_hydro_df_electric`` app module, imported once per test module."""
    return _load_opt_hydro_df_electric()


def test_surrogate_pipeline_end_to_end(app: ModuleType, tmp_path: Path) -> None:
    """LHS -> real-sim sweep -> train -> surrogate NSGA2 -> real-sim validation, schema-only."""
    params = app.APP.param_specs()
    objectives = app.APP.objective_specs
    param_names = [p.name for p in params]
    objective_names = [o.name for o in objectives]

    base_cfg = app.APP.base_config()

    n_samples = 20
    x = generate_lhs_samples(params, n_samples=n_samples, seed=1)
    assert x.shape == (n_samples, len(params))

    training_df = run_lhs_sweep(
        base_cfg,
        params,
        objectives,
        x,
        n_workers=1,
        results_dir=tmp_path / "lhs_results",
        quiet=True,
    )
    assert len(training_df) == n_samples
    for col in [*param_names, *objective_names, "success", "error_type", "error_message", "row_idx"]:
        assert col in training_df.columns
    # Need >= 2 of each class for train_surrogate's StratifiedKFold(cv_folds=2)
    # feasibility-classifier CV below -- n_samples=20 makes an all-one-class
    # LHS draw very unlikely for this system's ~50/50 feasible split.
    assert training_df["success"].sum() >= 2, "expected several feasible LHS samples"
    assert (~training_df["success"]).sum() >= 2, "expected several infeasible LHS samples"

    surrogate = train_surrogate(
        training_df,
        param_names,
        objective_names,
        classifier_n_estimators=10,
        cv_folds=2,
        seed=1,
    )
    diag = diagnostics_df(surrogate)
    assert list(diag["objective"]) == objective_names
    assert {"cv_r2", "cv_mae"}.issubset(diag.columns)

    classifier_diag = classifier_diagnostics_df(surrogate)
    assert {"classifier_threshold", "cv_accuracy", "cv_recall_infeasible"}.issubset(classifier_diag.columns)

    pareto_df = run_surrogate_optimization(
        surrogate,
        params,
        PymooConfig(pop_size=6, n_max_gen=2, seed=1),
    )
    assert len(pareto_df) >= 1
    for col in [*param_names, *objective_names]:
        assert col in pareto_df.columns

    # Loose tolerance: 8 training samples can't produce an accurate surrogate.
    # This is a schema/plumbing check, not a surrogate-quality check.
    try:
        comparison = validate_surrogate_pareto(
            base_cfg,
            params,
            objectives,
            pareto_df,
            n_workers=1,
            results_dir=tmp_path / "validate_results",
            tolerance=1.0,
            quiet=True,
        )
    except SurrogateValidationError as exc:
        comparison = exc.comparison  # type: ignore[attr-defined]

    for name in objective_names:
        assert f"predicted_{name}" in comparison.columns
        assert f"actual_{name}" in comparison.columns
        assert f"rel_error_{name}" in comparison.columns
    assert "real_success" in comparison.columns

    corrected = corrected_pareto_front(comparison, param_names, objective_names)
    # Schema-only: at this tiny scale the corrected front may legitimately be
    # empty (few/no real-feasible designs among a 6-pop, 2-gen surrogate
    # search) -- only assert column shape, not that it's non-empty.
    for col in [*param_names, *objective_names, "euclidean"]:
        assert col in corrected.columns
    assert len(corrected) <= int(comparison["real_success"].sum())
