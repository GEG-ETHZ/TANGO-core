"""Surrogate-model-assisted NSGA2 for tango_next's ``opt_*`` pymoo apps.

Deliberately independent of ``tango_next.pymoo_api`` INTERNALS — this module
only imports its PUBLIC names (``ParamSpec``, ``ObjectiveSpec``,
``PymooConfig``, ``ParetoProgressOutput``) and pymoo's own library APIs
directly, and does not touch ``Minimization``/``_evaluate_one``/etc. at all.
``ParetoProgressOutput`` specifically is reused (not reimplemented) so the
real-sim and surrogate-driven runs print an IDENTICAL per-generation
progress table — see ``run_surrogate_optimization``'s docstring. The
workflow this enables:

1. ``generate_lhs_samples`` — a generous Latin Hypercube sample over an app's
   ``ParamSpec`` bounds (this module's own LHS, not ``pymoo_api``'s ``LHS``
   import, which only pads a partially-seeded GA population).
2. ``run_lhs_sweep`` — evaluate every sampled point with the REAL simulation,
   in parallel, mirroring ``run_hydro_df_electric_sweep/sweep.py``'s
   spawn-context/``imap_unordered``/atomic-per-row-JSON pattern (this is a
   real, possibly-long, Euler-scale job — resumability matters here).
3. ``train_surrogate`` — one ``RandomForestRegressor`` per objective, fit on
   the successful rows from step 2.
4. ``run_surrogate_optimization`` — an NSGA2 search using the trained
   surrogate as the evaluator (classifier-gated, elementwise — see
   ``_SurrogateProblem``), not the real sim — cheap enough to run far
   larger population/generation counts than a real-sim search.
5. ``validate_surrogate_pareto`` — re-run the REAL simulation on the
   surrogate's pareto front and raise ``SurrogateValidationError`` if any
   objective is off by more than a tolerance (default 0.1%) for any design.

Each app's own ``ParamSpec``/``ObjectiveSpec`` factories (e.g.
``opt_hydro_df_electric.py``'s ``mass_rate_param``/``lcoe_objective``) are
reused as-is — this module stays as generic about what a "system" looks like
as ``pymoo_api.py`` itself.
"""

from __future__ import annotations

import copy
import json
import multiprocessing
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import joblib
import numpy as np
import pandas as pd
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.problem import ElementwiseProblem
from pymoo.optimize import minimize
from pymoo.termination.default import DefaultMultiObjectiveTermination as DMOT
from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
from scipy.stats import qmc
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score, recall_score
from sklearn.model_selection import KFold, StratifiedKFold, cross_val_predict

from tango_next.core.errors import ConvergenceError, CoolPropError, FrackingViolationError
from tango_next.pymoo_api import ParetoProgressOutput
from tango_next.workflows.workflow import Workflow

if TYPE_CHECKING:
    import numpy.typing as npt

    from tango_next.pymoo_api import ObjectiveSpec, ParamSpec, PymooConfig

# Same physical-infeasibility-vs-bug distinction pymoo_api.py's _CV_EXCEPTIONS
# makes (see that module's docstring) — a sampled LHS design failing one of
# these is an expected outcome, not a crash; anything else should still raise.
_INFEASIBLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    CoolPropError,
    FrackingViolationError,
    ConvergenceError,
)

# Same shape as pymoo_api.py's _CV_OBJECTIVE_FALLBACK/_FEASIBLE_G/_INFEASIBLE_G
# (private there, redefined here rather than imported — pymoo_api.py isn't
# touched by this module's own evaluation path). See that module's docstring
# for why the fallback objective value's magnitude doesn't matter: pymoo's
# constraint-domination ranking decides purely from G when G differs.
_CV_OBJECTIVE_FALLBACK = 0.0
_FEASIBLE_G = -1.0
_INFEASIBLE_G = 1.0


class SurrogateInfeasibleError(Exception):
    """Raised by ``SurrogateModel.evaluate_one`` when the feasibility classifier predicts failure.

    Mirrors ``pymoo_api.Minimization``'s ``_CV_EXCEPTIONS`` pattern (a
    specific, anticipated "this design doesn't work" signal, not a crash) —
    ``_SurrogateProblem._evaluate`` catches exactly this and turns it into a
    real pymoo constraint violation (``G > 0``), the same way
    ``Minimization._evaluate_one`` turns a real ``_CV_EXCEPTIONS`` into one.
    A caller building their OWN ``Minimization`` against a hybrid classifier-
    gated evaluator (rather than this module's independent surrogate driver)
    can pass this type via ``Minimization(..., extra_cv_exceptions=(SurrogateInfeasibleError,))``
    to get the identical treatment there.
    """


def generate_lhs_samples(
    params: list[ParamSpec],
    n_samples: int,
    seed: int | None = None,
) -> npt.NDArray[np.float64]:
    """Latin Hypercube sample over ``params``' bounds -> ``(n_samples, n_var)`` array."""
    sampler = qmc.LatinHypercube(d=len(params), seed=seed)
    unit = sampler.random(n=n_samples)
    lo = np.array([p.bounds[0] for p in params])
    hi = np.array([p.bounds[1] for p in params])
    return lo + unit * (hi - lo)


def build_config(base_cfg: dict[str, Any], params: list[ParamSpec], x: list[float]) -> dict[str, Any]:
    """Apply every ``ParamSpec`` to a fresh copy of ``base_cfg``.

    Same shape as ``pymoo_api.Minimization._build_config`` — reimplemented
    here rather than imported, since ``pymoo_api.py`` isn't touched by this
    module (``ParamSpec.apply`` is already a public field, so this is a
    handful of lines, not a real duplication of anything private).
    """
    cfg = copy.deepcopy(base_cfg)
    for spec, value in zip(params, x, strict=True):
        cfg = spec.apply(cfg, value)
    return cfg


def _param_objective_row(
    x: list[float],
    params: list[ParamSpec],
    objectives: list[ObjectiveSpec],
) -> dict[str, Any]:
    row: dict[str, Any] = {p.name: v for p, v in zip(params, x, strict=True)}
    row.update({o.name: None for o in objectives})
    row["success"] = False
    row["error_type"] = None
    row["error_message"] = None
    return row


def evaluate_training_row(
    x: list[float],
    base_cfg: dict[str, Any],
    params: list[ParamSpec],
    objectives: list[ObjectiveSpec],
) -> dict[str, Any]:
    """Build, run, and score one design — same physical-infeasibility handling
    as ``pymoo_api.Minimization._evaluate_one``, but returns a flat row dict
    (params + objectives + success/error info) instead of a pymoo
    objective/constraint tuple, since this is bulk training-data generation
    and validation, not a live GA evaluation.
    """
    row = _param_objective_row(x, params, objectives)
    cfg = build_config(base_cfg, params, x)
    try:
        wf = Workflow(cfg)
        wf.run()
    except _INFEASIBLE_EXCEPTIONS as exc:
        row["error_type"] = type(exc).__name__
        row["error_message"] = str(exc)
        return row
    for o in objectives:
        row[o.name] = o.evaluate(wf)
    row["success"] = True
    return row


def _evaluate_and_write(
    args: tuple[int, list[float], dict[str, Any], list[ParamSpec], list[ObjectiveSpec], Path],
) -> None:
    """Worker: evaluate one row and atomically write its JSON result file.

    Module-level (not a closure) and takes only picklable arguments — required
    for the ``spawn`` multiprocessing context (see ``run_hydro_df_electric_sweep/
    sweep.py``'s ``run_single_simulation`` for the same constraint).
    """
    row_idx, x, base_cfg, params, objectives, results_dir = args
    result_file = results_dir / f"{row_idx:06d}.json"
    if result_file.exists():
        return
    row = evaluate_training_row(x, base_cfg, params, objectives)
    row["row_idx"] = row_idx
    results_dir.mkdir(exist_ok=True, parents=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=results_dir, delete=False, suffix=".tmp") as f:
        json.dump(row, f)
        tmp_path = Path(f.name)
    tmp_path.rename(result_file)


def run_lhs_sweep(
    base_workflow: Workflow,
    params: list[ParamSpec],
    objectives: list[ObjectiveSpec],
    x: npt.NDArray[np.float64],
    n_workers: int,
    results_dir: Path,
    quiet: bool = False,
) -> pd.DataFrame:
    """Evaluate every row of ``x`` with the REAL simulation, in parallel.

    Mirrors ``run_hydro_df_electric_sweep/sweep.py``'s ``run_sweep()``: a
    spawn-context ``multiprocessing.Pool``, ``imap_unordered``, one atomic
    JSON file per design point under ``results_dir`` (resumable — an
    already-written row is skipped, so a killed run just needs to be
    restarted with the same ``results_dir``). This is a real, possibly-long,
    Euler-scale job (unlike the surrogate-driven GA below, which is cheap
    enough to just rerun from scratch if killed).
    """
    base_cfg = base_workflow.to_dict()
    n_samples = x.shape[0]
    results_dir.mkdir(exist_ok=True, parents=True)

    completed = {int(f.stem) for f in results_dir.glob("*.json")}
    pending = [i for i in range(n_samples) if i not in completed]
    if not quiet:
        print(f"LHS sweep status: {len(completed)}/{n_samples} completed, {len(pending)} pending")

    if pending:
        worker_args = [(i, list(x[i]), base_cfg, params, objectives, results_dir) for i in pending]
        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(n_workers) as pool:
            done = 0
            for _ in pool.imap_unordered(_evaluate_and_write, worker_args):
                done += 1
                if not quiet and done % max(1, n_workers) == 0:
                    print(f"LHS sweep progress: {done}/{len(pending)}")

    rows = [json.loads(f.read_text()) for f in sorted(results_dir.glob("*.json"))]
    return pd.DataFrame(rows).sort_values("row_idx").reset_index(drop=True)


@dataclass
class SurrogateModel:
    """One ``RandomForestRegressor`` per objective, a feasibility classifier, plus CV diagnostics.

    The regressors alone have no notion of "this design doesn't physically
    work" — trained only on FEASIBLE rows, they extrapolate smooth-looking
    (but meaningless) objective values into infeasible regions of the design
    space, which an unconstrained surrogate NSGA2 search then exploits
    (confirmed the hard way on a real Euler run: 74% of the surrogate's
    "optimal" pareto front turned out to fail the real simulation outright).
    ``classifier`` (trained on ALL rows — both classes are needed to learn
    the feasible/infeasible boundary, unlike the regressors) is what
    ``evaluate_one`` checks FIRST, raising ``SurrogateInfeasibleError``
    before ever consulting the regressors for a design it predicts won't
    work — see that method's docstring.
    """

    param_names: list[str]
    objective_names: list[str]
    models: dict[str, RandomForestRegressor]
    cv_r2: dict[str, float]
    cv_mae: dict[str, float]
    classifier: RandomForestClassifier
    classifier_cv_accuracy: float
    classifier_cv_recall_infeasible: float
    classifier_threshold: float = 0.5

    def predict(self, x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """``(n, n_var) -> (n, n_obj)``, columns in ``self.objective_names`` order.

        Regressor predictions ONLY — does not consult ``classifier`` at all.
        Used by diagnostics/plotting over already-selected points; live NSGA2
        evaluation goes through ``evaluate_one`` instead, which gates on the
        classifier first.
        """
        return np.column_stack([self.models[name].predict(x) for name in self.objective_names])

    def predict_feasible(self, x: npt.NDArray[np.float64]) -> npt.NDArray[np.bool_]:
        """``(n, n_var) -> (n,)`` bool — classifier's feasibility call at ``self.classifier_threshold``."""
        proba_feasible = self.classifier.predict_proba(x)[:, list(self.classifier.classes_).index(True)]
        return proba_feasible >= self.classifier_threshold

    def evaluate_one(self, x: list[float]) -> list[float]:
        """Classifier first; only run the regressors if it predicts feasible.

        Raises ``SurrogateInfeasibleError`` (rather than returning a
        fallback value) when the classifier predicts infeasible — mirrors
        ``pymoo_api.Minimization._evaluate_one``'s try/raise/except shape
        exactly, so ``_SurrogateProblem._evaluate`` (below) can turn it into
        a real pymoo constraint violation the same way.
        """
        x_arr = np.asarray(x, dtype=float).reshape(1, -1)
        if not self.predict_feasible(x_arr)[0]:
            msg = f"feasibility classifier predicts infeasible for x={x}"
            raise SurrogateInfeasibleError(msg)
        return [self.models[name].predict(x_arr)[0] for name in self.objective_names]


def train_surrogate(
    training_df: pd.DataFrame,
    param_names: list[str],
    objective_names: list[str],
    n_estimators: int = 300,
    cv_folds: int = 5,
    seed: int | None = 1,
    classifier_threshold: float = 0.5,
) -> SurrogateModel:
    """Fit one ``RandomForestRegressor`` per objective, plus a feasibility ``RandomForestClassifier``.

    The regressors train on the FEASIBLE rows only (an infeasible row has no
    ``y``). The classifier trains on EVERY row (both classes needed to learn
    the feasible/infeasible boundary at all — see ``SurrogateModel``'s
    docstring for why this classifier exists).

    Reports k-fold cross-validated R²/MAE per objective, and CV accuracy/
    infeasible-recall for the classifier, as trustworthiness signals
    (computed via ``cross_val_predict`` against a fresh, unfit estimator per
    fold — not read off the final models, which are refit on the full
    dataset afterward so no expensive real-sim data is thrown away on the
    models actually used downstream). Infeasible-recall (not overall
    accuracy) is the number to watch: a classifier that's 90% accurate but
    only catches half of true infeasible designs still lets NSGA2 exploit
    the other half — same failure mode the classifier exists to prevent.
    """
    feasible = training_df[training_df["success"]]
    n_dropped = len(training_df) - len(feasible)
    if n_dropped:
        print(
            f"train_surrogate: dropping {n_dropped}/{len(training_df)} infeasible LHS samples for the regressors",
        )
    if len(feasible) < cv_folds:
        msg = f"Only {len(feasible)} feasible training rows, need >= cv_folds ({cv_folds})"
        raise ValueError(msg)

    x = feasible[param_names].to_numpy(dtype=float)
    models: dict[str, RandomForestRegressor] = {}
    cv_r2: dict[str, float] = {}
    cv_mae: dict[str, float] = {}
    kfold = KFold(n_splits=cv_folds, shuffle=True, random_state=seed)
    for name in objective_names:
        y = feasible[name].to_numpy(dtype=float)
        cv_model = RandomForestRegressor(n_estimators=n_estimators, random_state=seed, n_jobs=-1)
        y_pred = cross_val_predict(cv_model, x, y, cv=kfold)
        cv_r2[name] = r2_score(y, y_pred)
        cv_mae[name] = mean_absolute_error(y, y_pred)

        model = RandomForestRegressor(n_estimators=n_estimators, random_state=seed, n_jobs=-1)
        model.fit(x, y)
        models[name] = model

    x_all = training_df[param_names].to_numpy(dtype=float)
    y_feasible_all = training_df["success"].to_numpy(dtype=bool)
    if len(np.unique(y_feasible_all)) < 2:  # noqa: PLR2004
        msg = "training_df has only one class (all feasible or all infeasible) -- can't train a classifier"
        raise ValueError(msg)

    stratified_kfold = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=seed)
    cv_classifier = RandomForestClassifier(n_estimators=n_estimators, random_state=seed, n_jobs=-1)
    y_feasible_pred = cross_val_predict(cv_classifier, x_all, y_feasible_all, cv=stratified_kfold)
    classifier_cv_accuracy = accuracy_score(y_feasible_all, y_feasible_pred)
    classifier_cv_recall_infeasible = recall_score(y_feasible_all, y_feasible_pred, pos_label=False)

    classifier = RandomForestClassifier(n_estimators=n_estimators, random_state=seed, n_jobs=-1)
    classifier.fit(x_all, y_feasible_all)

    return SurrogateModel(
        param_names=param_names,
        objective_names=objective_names,
        models=models,
        cv_r2=cv_r2,
        cv_mae=cv_mae,
        classifier=classifier,
        classifier_cv_accuracy=classifier_cv_accuracy,
        classifier_cv_recall_infeasible=classifier_cv_recall_infeasible,
        classifier_threshold=classifier_threshold,
    )


def diagnostics_df(surrogate: SurrogateModel) -> pd.DataFrame:
    """One row per objective: cross-validated R²/MAE — the trustworthiness readout."""
    return pd.DataFrame(
        {
            "objective": surrogate.objective_names,
            "cv_r2": [surrogate.cv_r2[n] for n in surrogate.objective_names],
            "cv_mae": [surrogate.cv_mae[n] for n in surrogate.objective_names],
        },
    )


def classifier_diagnostics_df(surrogate: SurrogateModel) -> pd.DataFrame:
    """One row: the feasibility classifier's CV accuracy/infeasible-recall — see ``train_surrogate``."""
    return pd.DataFrame(
        {
            "classifier_threshold": [surrogate.classifier_threshold],
            "cv_accuracy": [surrogate.classifier_cv_accuracy],
            "cv_recall_infeasible": [surrogate.classifier_cv_recall_infeasible],
        },
    )


def save_surrogate(surrogate: SurrogateModel, path: Path) -> None:
    """Persist ``surrogate`` (every per-objective forest + diagnostics) via joblib."""
    joblib.dump(surrogate, path)


def load_surrogate(path: Path) -> SurrogateModel:
    """Load a ``SurrogateModel`` previously written by ``save_surrogate``."""
    return joblib.load(path)


class _SurrogateProblem(ElementwiseProblem):
    """One design at a time: classifier first, regressors only if it predicts feasible.

    Elementwise (not batch) specifically so a per-design ``SurrogateInfeasibleError``
    can be caught and turned into a per-design constraint violation — a
    batch/vectorized ``_evaluate`` (predicting the whole population in one
    call) can't express "this ONE row is infeasible, the rest aren't" via a
    raised exception. Still fast: no real simulation, no multiprocessing —
    every evaluation is just a couple of already-fit sklearn ``predict``
    calls, negligible next to what running a full generation of real physics
    would cost.
    """

    def __init__(self, surrogate: SurrogateModel, params: list[ParamSpec]) -> None:
        super().__init__(
            n_var=len(params),
            n_obj=len(surrogate.objective_names),
            n_ieq_constr=1,
            xl=np.array([p.bounds[0] for p in params]),
            xu=np.array([p.bounds[1] for p in params]),
        )
        self.surrogate = surrogate

    def _evaluate(self, x: npt.NDArray[np.float64], out: dict[str, Any], *args: Any, **kwargs: Any) -> None:
        try:
            out["F"] = self.surrogate.evaluate_one(list(x))
            out["G"] = [_FEASIBLE_G]
        except SurrogateInfeasibleError:
            out["F"] = [_CV_OBJECTIVE_FALLBACK] * len(self.surrogate.objective_names)
            out["G"] = [_INFEASIBLE_G]


def run_surrogate_optimization(
    surrogate: SurrogateModel,
    params: list[ParamSpec],
    pymoo_config: PymooConfig,
    verbose: bool = True,
) -> pd.DataFrame:
    """NSGA2 search using ``surrogate`` as the evaluator instead of the real simulation.

    An independent driver — NOT ``Minimization.run()`` — using pymoo's own
    ``minimize()`` convenience function directly (no manual generation loop /
    per-generation checkpointing: a killed surrogate run is cheap enough to
    just rerun from scratch, unlike a real-sim optimization that
    ``Minimization.run()`` protects against a SLURM kill mid-run).

    ``_SurrogateProblem`` gives NSGA2 a real constraint violation (via
    ``surrogate.evaluate_one``'s feasibility-classifier gate) for any design
    predicted infeasible, the same way ``Minimization``'s own ``_Problem``
    does for a real physical failure — WITHOUT this, NSGA2 has no reason to
    avoid the surrogate's blind spots (regions with no feasible training
    data, where the regressors still confidently — and wrongly — predict
    plausible objective values) and will actively search into them.

    ``verbose=True`` by default (unlike a bare ``minimize()`` call) so a
    per-generation progress table prints, via ``pymoo_api.ParetoProgressOutput``
    — the exact SAME ``Output`` class ``Minimization.run()`` itself uses, not
    a second, independently-shaped one — so the real-sim and surrogate-driven
    runs print IDENTICAL tables (``n_gen``/``n_eval``/``n_nds``/``t [s]``/
    ``euclid_min (z)``), directly comparable line for line. Without the
    elapsed-time column specifically, there's no way to tell from the log
    whether a fast run converged early via ``ftol``/``xtol`` after a handful
    of generations or actually ran every one of ``n_max_gen``, which matters
    for a fair time comparison against the real-sim optimization.

    Returns a DataFrame with the same column shape as ``Minimization``'s own
    (param columns + objective columns), so it's plottable with any app's
    existing ``make_plots()`` unchanged.
    """
    problem = _SurrogateProblem(surrogate, params)
    algorithm = NSGA2(pop_size=pymoo_config.pop_size, output=ParetoProgressOutput())
    termination = DMOT(
        xtol=pymoo_config.xtol,
        ftol=pymoo_config.ftol,
        n_max_gen=pymoo_config.n_max_gen,
    )
    res = minimize(problem, algorithm, termination, seed=pymoo_config.seed, verbose=verbose)

    x = res.X if res.X is not None else np.empty((0, len(params)))
    f = res.F if res.F is not None else np.empty((0, len(surrogate.objective_names)))
    x = x if x.ndim == 2 else x.reshape(1, -1)
    f = f if f.ndim == 2 else f.reshape(1, -1)

    x_df = pd.DataFrame(x, columns=[p.name for p in params])
    f_df = pd.DataFrame(f, columns=surrogate.objective_names)
    df = pd.concat([x_df, f_df], axis=1)

    # Same z-score-normalized Euclidean-distance column
    # Minimization._build_results_df computes (see that method's docstring
    # for why it's z-score, not raw-unit, normalized) — required for
    # make_plots' plot_pareto_parallel_coordinates/plot_pareto_scatter_zscore,
    # which color by this column and KeyError without it (confirmed the hard
    # way on a real Euler run: optimize_surrogate.py wrote
    # surrogate_pareto_results.csv successfully, then crashed in make_plots).
    std = f_df.std().replace(0.0, 1.0)
    z = (f_df - f_df.mean()) / std
    df["euclidean"] = (z**2).sum(axis=1).pow(0.5)
    return df


class SurrogateValidationError(Exception):
    """Raised by ``validate_surrogate_pareto`` listing every tolerance violation found."""


def validate_surrogate_pareto(
    base_workflow: Workflow,
    params: list[ParamSpec],
    objectives: list[ObjectiveSpec],
    surrogate_df: pd.DataFrame,
    n_workers: int,
    results_dir: Path,
    tolerance: float = 0.001,
    quiet: bool = False,
) -> pd.DataFrame:
    """Re-run the REAL simulation on every row of ``surrogate_df`` (not a sample).

    Builds a predicted-vs-actual comparison DataFrame, then raises
    ``SurrogateValidationError`` (listing every violating (design,
    objective) pair, not just the first) if any objective's relative error
    exceeds ``tolerance`` (default 0.1%) for any design — this function's
    return value is still the full comparison DataFrame, so results aren't
    lost when the error is raised (the caller should save it before/around
    the call, e.g. via a ``try``/``finally``, or inspect the exception's
    ``comparison`` attribute).
    """
    param_names = [p.name for p in params]
    objective_names = [o.name for o in objectives]
    x = surrogate_df[param_names].to_numpy(dtype=float)

    actual_df = run_lhs_sweep(base_workflow, params, objectives, x, n_workers, results_dir, quiet=quiet)

    comparison = surrogate_df[param_names].copy()
    violations: list[str] = []
    for name in objective_names:
        predicted = surrogate_df[name].to_numpy(dtype=float)
        actual = actual_df[name].to_numpy(dtype=float)
        comparison[f"predicted_{name}"] = predicted
        comparison[f"actual_{name}"] = actual
        denom = np.where(actual == 0.0, np.nan, actual)
        rel_error = np.abs(actual - predicted) / np.abs(denom)
        comparison[f"rel_error_{name}"] = rel_error
        for row_idx, err in enumerate(rel_error):
            if pd.notna(err) and err > tolerance:
                violations.append(
                    f"design {row_idx}: {name} predicted={predicted[row_idx]!r} "
                    f"actual={actual[row_idx]!r} rel_error={err:.4%} (tolerance={tolerance:.4%})",
                )
    comparison["real_success"] = actual_df["success"]

    if violations:
        exc = SurrogateValidationError(
            f"{len(violations)} design/objective pair(s) exceeded {tolerance:.4%} tolerance:\n"
            + "\n".join(violations),
        )
        exc.comparison = comparison  # type: ignore[attr-defined]
        raise exc
    return comparison


def corrected_pareto_front(
    comparison: pd.DataFrame,
    param_names: list[str],
    objective_names: list[str],
) -> pd.DataFrame:
    """The genuinely trustworthy result: real-feasible designs, REAL simulated objective values.

    ``comparison`` is ``validate_surrogate_pareto``'s return value (or a
    ``SurrogateValidationError``'s ``.comparison`` attribute — this is
    meant to be called EITHER way, tolerance violations don't make the
    underlying real-sim reruns any less real).

    Two corrections happen here, not just one:

    1. Filters to ``real_success`` rows — the surrogate's raw pareto front
       includes designs the classifier/regressors predicted were good but
       the real simulation actually rejects; those have no real objective
       values to report at all.
    2. Re-derives non-dominated status from the ACTUAL (not predicted) objective
       values. A design that looked non-dominated under the surrogate's
       predictions is not guaranteed to still be non-dominated once its
       real values are known — e.g. two designs the surrogate ranked as
       a genuine tradeoff might, in reality, have one strictly beat the
       other on every objective. Re-running non-dominated sorting (pymoo's
       own ``NonDominatedSorting``, same convention as everywhere else in
       this codebase — minimize every objective) is what makes this the
       actual corrected front, not just a filtered copy of the surrogate's.

    Returns a DataFrame in the same column shape as ``Minimization``'s own
    results (param columns + objective columns, using the PLAIN objective
    names — not ``actual_<name>`` — plus ``euclidean``), so it's directly
    plottable with any app's existing ``make_plots()``.
    """
    real = comparison[comparison["real_success"]].copy()
    result = real[param_names].copy()
    for name in objective_names:
        result[name] = real[f"actual_{name}"].to_numpy(dtype=float)
    result = result.reset_index(drop=True)

    if len(result) == 0:
        result["euclidean"] = pd.Series(dtype=float)
        return result

    f = result[objective_names].to_numpy(dtype=float)
    front_idx = NonDominatedSorting().do(f, only_non_dominated_front=True)
    result = result.iloc[front_idx].reset_index(drop=True)

    f_df = result[objective_names]
    std = f_df.std().replace(0.0, 1.0)
    z = (f_df - f_df.mean()) / std
    result["euclidean"] = (z**2).sum(axis=1).pow(0.5)
    return result
