"""Surrogate-model-assisted NSGA2 for tango's ``opt_*`` pymoo apps.

Deliberately independent of ``tango.pymoo_api`` INTERNALS — this module
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
3. ``train_surrogate`` — one regressor per objective (default:
   ``MLPRegressor``, swappable via ``regressor_factory`` -- see
   ``REGRESSOR_FACTORIES``), fit on the successful rows from step 2.
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
import math
import multiprocessing
import tempfile
import time
from collections.abc import Callable
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
from scipy.spatial import cKDTree
from scipy.stats import qmc
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score, recall_score
from sklearn.model_selection import KFold, StratifiedKFold, cross_val_predict
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from tango.pymoo_api import INFEASIBLE_DESIGN_EXCEPTIONS, ParetoProgressOutput
from tango.workflows.workflow import Workflow

if TYPE_CHECKING:
    import numpy.typing as npt

    from tango.pymoo_api import ObjectiveSpec, ParamSpec, PymooConfig

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

    Mirrors ``pymoo_api.Minimization``'s ``INFEASIBLE_DESIGN_EXCEPTIONS`` pattern (a
    specific, anticipated "this design doesn't work" signal, not a crash) —
    ``_SurrogateProblem._evaluate`` catches exactly this and turns it into a
    real pymoo constraint violation (``G > 0``), the same way
    ``Minimization._evaluate_one`` turns a real ``INFEASIBLE_DESIGN_EXCEPTIONS`` into one.
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
    except INFEASIBLE_DESIGN_EXCEPTIONS as exc:
        row["error_type"] = type(exc).__name__
        row["error_message"] = str(exc)
        return row
    for o in objectives:
        row[o.name] = o.evaluate(wf)
    row["success"] = True
    return row


def _cached_row_is_valid(result_file: Path, params: list[ParamSpec], x_row: list[float]) -> bool:
    """True only if ``result_file`` exists AND its stored params match ``x_row``.

    A cached JSON file existing at ``{row_idx}.json`` is NOT by itself proof
    that it's safe to reuse: ``run_lhs_sweep`` is also called (via
    ``validate_surrogate_pareto``) against a FIXED ``results_dir`` that gets
    reused across entirely separate pipeline runs, each with its own
    surrogate-produced pareto front — a different set of designs, but the
    SAME row indices (0, 1, 2, ...). Trusting file existence alone silently
    reuses a totally different, unrelated design's real-sim result under a
    row index that now belongs to a different design point (confirmed the
    hard way: comparing two `validate_surrogate.py` runs' cached files showed
    row 0's cached params didn't match row 0's current surrogate-predicted
    design at all). Comparing every stored param value against ``x_row``
    (not just checking the file exists) is what makes this genuinely safe to
    reuse across BOTH call sites: the LHS design matrix case, where ``x_row``
    never changes between runs (so every cached row always matches and gets
    skipped, same behavior as before), and the pareto-front-validation case,
    where a stale row now gets correctly detected and recomputed instead of
    silently reused.
    """
    if not result_file.exists():
        return False
    try:
        cached = json.loads(result_file.read_text())
    except json.JSONDecodeError:
        return False
    return all(
        math.isclose(cached[p.name], v, rel_tol=1e-9, abs_tol=1e-12)
        for p, v in zip(params, x_row, strict=True)
    )


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
    if _cached_row_is_valid(result_file, params, x):
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
    already-written row whose cached design matches ``x`` is skipped, so a
    killed run just needs to be restarted with the same ``results_dir`` --
    see ``_cached_row_is_valid`` for why "already-written" alone isn't a
    sufficient resume condition). This is a real, possibly-long, Euler-scale
    job (unlike the surrogate-driven GA below, which is cheap enough to just
    rerun from scratch if killed).
    """
    base_cfg = base_workflow.to_dict()
    n_samples = x.shape[0]
    results_dir.mkdir(exist_ok=True, parents=True)

    completed = {
        i for i in range(n_samples) if _cached_row_is_valid(results_dir / f"{i:06d}.json", params, list(x[i]))
    }
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
                    print(
                        f"LHS sweep progress: {len(completed) + done}/{n_samples} ({done}/{len(pending)} this run)",
                    )

    rows = [json.loads(f.read_text()) for f in sorted(results_dir.glob("*.json"))]
    return pd.DataFrame(rows).sort_values("row_idx").reset_index(drop=True)


@dataclass
class SurrogateModel:
    """One swappable per-objective regressor, a feasibility classifier, plus CV diagnostics.

    ``models`` holds whatever ``regressor_factory`` (see ``train_surrogate``)
    produced — any scikit-learn-compatible regressor (``.fit``/``.predict``)
    works, not just one hardcoded type. The default factory,
    ``mlp_regressor_factory``, was chosen over ``RandomForestRegressor``
    (this module's original choice) because a random forest's predictions
    are piecewise-constant (flat within each leaf's training-data region) —
    NSGA2 searching against that surface repeatedly collapses onto whichever
    plateau looks best and stalls there, since every nearby point predicts
    the identical objective value and there is no local gradient to climb.
    An MLP predicts a smooth, differentiable surface instead, which keeps a
    gradient-free search like NSGA2 actually able to distinguish nearby
    designs. ``gaussian_process_regressor_factory`` predicts an equally
    smooth surface and was this module's default until 2026-09-01, but a
    real Euler run showed it losing to the MLP on both speed (its O(n^3) fit
    cost, repeated across CV folds and hyperparameter-optimizer restarts,
    gets expensive past a few thousand feasible rows) and on accuracy where
    it actually matters (NSGA2 exploited a region where its predictions were
    off by up to 35%, vs. the MLP's max 4.3% in the same region) — see
    ``mlp_regressor_factory``'s and ``gaussian_process_regressor_factory``'s
    own docstrings for the full comparison. ``random_forest_regressor_factory``
    (this module's original choice) is still available for an apples-to-apples
    comparison -- see each factory's own docstring, all registered in
    ``REGRESSOR_FACTORIES``. Inputs are always standardized through
    ``x_scaler`` (fit on the same rows as the regressors) before every
    predict call — harmless for a scale-invariant regressor like a random
    forest, but required for one like a GP that fits a per-dimension length
    scale, so it's applied unconditionally rather than per-factory. Targets
    are likewise standardized per objective through ``y_scalers`` (one
    ``StandardScaler`` per objective, inverse-transformed back to real units
    on the way out) — confirmed necessary the hard way: ``negative_mean_power_W``
    (scale ~1e6) trained an ``MLPRegressor`` to a cross-validated R² of
    -0.33 (worse than predicting the mean) when fit on raw, unscaled
    targets, because its default weight init/learning rate/L2 regularization
    all implicitly assume roughly unit-scale targets. ``GaussianProcessRegressor``'s
    own ``normalize_y=True`` had been masking that this codebase never
    standardized *outputs* at all, only inputs — applying ``y_scalers``
    unconditionally (like ``x_scaler``) rather than requiring every future
    ``regressor_factory`` to remember its own normalization is what actually
    fixes this, not a GP-specific workaround.

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
    work — see that method's docstring. The classifier stays a
    ``RandomForestClassifier`` regardless of ``regressor_factory`` — only
    the objective regressors are swappable.
    """

    param_names: list[str]
    objective_names: list[str]
    models: dict[str, Any]
    x_scaler: StandardScaler
    y_scalers: dict[str, StandardScaler]
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
        x_scaled = self.x_scaler.transform(x)
        cols = []
        for name in self.objective_names:
            y_scaled = self.models[name].predict(x_scaled)
            cols.append(self.y_scalers[name].inverse_transform(y_scaled.reshape(-1, 1)).ravel())
        return np.column_stack(cols)

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
        x_scaled = self.x_scaler.transform(x_arr)
        return [
            float(
                self.y_scalers[name].inverse_transform(self.models[name].predict(x_scaled).reshape(-1, 1))[
                    0,
                    0,
                ],
            )
            for name in self.objective_names
        ]


# n_dims -> a fresh, UNFITTED sklearn-style regressor (bare `.fit`/`.predict`).
# `train_surrogate` calls this twice per objective (once for the CV model,
# once for the final model refit on all feasible rows) -- a factory, not a
# shared instance, because several regressor types (e.g. a GP's kernel)
# mutate their own hyperparameters in place during `.fit`, so reusing one
# instance would leak the CV fold's fitted state into the final model's
# starting point. `n_dims` is threaded through even though most regressor
# types ignore it, because a GP's kernel needs to know the input
# dimensionality up front to size its per-dimension length-scale vector.
RegressorFactory = Callable[[int], Any]


def gaussian_process_regressor_factory(
    n_restarts_optimizer: int = 5,
    seed: int | None = 1,
) -> RegressorFactory:
    """Alternative ``regressor_factory``: a smooth, differentiable surface.

    Was this module's default until 2026-09-01 (replacing
    ``RandomForestRegressor`` as the default in the first place -- see
    ``SurrogateModel``'s docstring for why piecewise-constant predictions are
    a problem). Demoted to an alternative after a real Euler run (5000 LHS
    samples) showed ``mlp_regressor_factory`` beats it on THIS problem, not
    just on speed: this GP's cross-validated R^2 looked excellent (LCOE
    0.9985), but NSGA2 still exploited a region where its actual predictions
    were off by up to 35%, leaving only 3/43 predicted-pareto designs
    genuinely non-dominated after real-sim correction -- vs. the MLP's
    12/45. Still useful as the smooth-surface reference case, e.g. if a
    future problem's regressor comparison should be re-run from scratch.

    Kernel is ``ConstantKernel * RBF + WhiteKernel``, with a per-dimension
    (not scalar) ``length_scale`` so the GP can learn that some standardized
    parameters matter more than others (ARD).

    Args:
        n_restarts_optimizer: Number of restarts of the kernel hyperparameter
            optimizer, each from a different random starting point, on top of
            the one from the kernel's own initial values -- guards against
            landing in a bad local optimum. Higher is slower (each restart is
            a full O(n^3) refit) but more reliable.
        seed: Random seed for the optimizer's restart points.

    """

    def factory(n_dims: int) -> GaussianProcessRegressor:
        kernel = ConstantKernel(1.0, (1e-3, 1e3)) * RBF(
            length_scale=np.ones(n_dims),
            length_scale_bounds=(1e-2, 1e2),
        ) + WhiteKernel(noise_level=1e-3, noise_level_bounds=(1e-10, 1e1))
        return GaussianProcessRegressor(
            kernel=kernel,
            normalize_y=True,
            n_restarts_optimizer=n_restarts_optimizer,
            random_state=seed,
        )

    return factory


def random_forest_regressor_factory(
    n_estimators: int = 300,
    seed: int | None = 1,
) -> RegressorFactory:
    """Alternative ``regressor_factory``: this module's original choice.

    Piecewise-constant predictions can stall a surrogate-driven NSGA2 search
    on plateaus (see ``SurrogateModel``'s docstring) -- kept here for an
    apples-to-apples comparison against the default (``mlp_regressor_factory``),
    not recommended as the default itself.

    Args:
        n_estimators: Number of trees in the forest.
        seed: Random seed for tree bootstrapping/feature selection.

    """

    def factory(n_dims: int) -> RandomForestRegressor:  # noqa: ARG001 -- n_dims unused, RF doesn't need it
        return RandomForestRegressor(n_estimators=n_estimators, random_state=seed, n_jobs=-1)

    return factory


def mlp_regressor_factory(
    hidden_layer_sizes: tuple[int, ...] = (16, 16),
    alpha: float = 1e-3,
    max_iter: int = 2000,
    seed: int | None = 1,
) -> RegressorFactory:
    """Default ``regressor_factory`` (since 2026-09-01): smooth, but fits by gradient descent.

    An MLP (multi-layer perceptron) is a small feedforward neural network --
    one or more "hidden" layers of neurons, each a weighted sum of the
    previous layer's outputs passed through a nonlinearity, sandwiched
    between the input (the design parameters) and output (one objective).
    Like a GP it predicts a smooth, differentiable surface, but it fits by
    gradient descent rather than an O(n^3) matrix decomposition (see
    ``gaussian_process_regressor_factory``'s docstring for why that gets
    expensive), so it scales far better as ``n_lhs_samples`` grows.
    Confirmed empirically, not just theoretically: on a real Euler run
    (5000 LHS samples) this trained in ~15s (vs. the GP's ~36 min) AND held
    up far better at the pareto edge (LCOE relative error: median 1.4%, max
    4.3%, vs. the GP's median ~9.8%/max 35%), leaving 12/45 predicted-pareto
    designs genuinely non-dominated after real-sim correction vs. the GP's
    3/43 -- see ``gaussian_process_regressor_factory``'s docstring for that
    comparison's other side.

    The tradeoff is needing more manual care to land on a genuinely smooth
    (not overfit/jagged) fit: ``alpha`` (L2 regularization) and
    ``hidden_layer_sizes`` are the two knobs worth tuning first if
    predictions look wrong. ``hidden_layer_sizes`` in particular trades off
    against how much training data ``train_surrogate`` actually has to fit
    it with -- the default here is deliberately small (two 16-neuron
    layers, a few hundred learnable weights total) rather than something
    like ``(64, 64)`` (tens of thousands of weights), because a few thousand
    feasible LHS rows over a handful of design parameters is nowhere near
    enough data to fit a network that large without overfitting; raise it
    only if ``n_lhs_samples`` grows substantially or the response surface
    turns out to need more capacity than this captures. Also has no native
    per-prediction uncertainty, unlike the GP -- irrelevant here since
    ``SurrogateModel``'s separate ``RandomForestClassifier`` already handles
    feasibility gating regardless of which regressor_factory trains the
    objectives.

    Args:
        hidden_layer_sizes: Number of neurons in each hidden layer, e.g.
            ``(16, 16)`` for two 16-neuron layers.
        alpha: L2 regularization strength -- raise it if the fit looks
            jagged/overfit, lower it if predictions look too flat to track
            genuine features of the response surface.
        max_iter: Maximum optimizer iterations; raise it if sklearn warns the
            fit didn't converge.
        seed: Random seed for weight initialization and training.
    """

    def factory(n_dims: int) -> MLPRegressor:  # noqa: ARG001 -- n_dims unused, MLPRegressor infers input width from X at fit time
        return MLPRegressor(
            hidden_layer_sizes=hidden_layer_sizes,
            alpha=alpha,
            max_iter=max_iter,
            random_state=seed,
        )

    return factory


# Name -> factory-of-factories, so a caller (e.g. an app's train_surrogate.py
# CLI/params.yaml) can select a regressor by a plain string instead of
# importing the factory function directly.
REGRESSOR_FACTORIES: dict[str, Callable[..., RegressorFactory]] = {
    "gaussian_process": gaussian_process_regressor_factory,
    "random_forest": random_forest_regressor_factory,
    "mlp": mlp_regressor_factory,
}


def dedup_training_rows(
    training_df: pd.DataFrame,
    param_names: list[str],
    objective_names: list[str],
    tol_frac: float = 0.001,
) -> pd.DataFrame:
    """Drop later-occurring near-duplicate rows from a training dataframe.

    Complements ``pymoo_api.ParamToleranceDuplicateElimination``, which only
    catches duplicates within ONE generation's offspring/population during a
    real-NSGA2 trajectory run (see ``run_trajectory.py``) — a design from
    generation 2 can still duplicate one from generation 5 without either
    ever being compared, since pymoo's own dedup only ever looks at what's
    currently live. This runs once, after the fact, over the WHOLE retained
    history.

    Two rows are duplicates if every value in ``param_names`` is within
    ``tol_frac`` of the other row's (as a fraction of that column's
    OBSERVED range across the WHOLE ``training_df`` — computed once, up
    front, and reused for every comparison, not per-subset: using each
    comparison group's OWN range would be self-referential for a small
    group (a 2-row group's range IS the gap between those two rows, so
    ``tol_frac * range`` is always far smaller than the actual gap unless
    it's already exactly zero — confirmed the hard way with a 2-row
    infeasible-only test case that should have been flagged and wasn't).
    Deliberately different from
    ``ParamToleranceDuplicateElimination``'s normalization against each
    param's GLOBAL ``bounds``: that pre-eval check asks "is this
    meaningfully far from other designs across the WHOLE search space,"
    this post-hoc check asks "are these two rows practically
    indistinguishable outcomes relative to how much this dataset actually
    varies" — a different question, so a different reference scale is the
    right choice, not an inconsistency to fix). Two FEASIBLE rows are ALSO
    compared on ``objective_names`` the same way — an infeasible row has no
    real objective values (see ``evaluate_training_row``), so infeasible
    rows are compared on params alone; a feasible and an infeasible row are
    never duplicates of each other regardless of how close their params
    are, since ``success`` differing already means they're not the same
    outcome.

    Uses ``scipy.spatial.cKDTree`` with Chebyshev (``p=inf``, i.e. max-over-dims)
    distance — the metric that actually matches "every dimension within
    tol_frac independently," not one combined Euclidean distance. Cheap
    regardless of scale: confirmed empirically at 50,000 rows / 5 columns,
    ~0.02s (vs. ~1.6s for a naive O(n²) broadcast comparison at just 10,000
    rows, and quadratically worse from there) — checking is not the
    consideration here, only whether removing near-duplicates changes the
    surrogate fit for the better.
    """
    df = training_df.reset_index(drop=True)
    keep = np.ones(len(df), dtype=bool)
    feasible = df["success"].to_numpy(dtype=bool)

    def _observed_range(
        cols: list[str],
        mask: npt.NDArray[np.bool_] | None = None,
    ) -> npt.NDArray[np.float64]:
        if not cols:  # objective_names may legitimately be [] -- max/min over a zero-width axis raises
            return np.empty(0, dtype=float)
        vals = df[cols].to_numpy(dtype=float) if mask is None else df.loc[mask, cols].to_numpy(dtype=float)
        col_range = vals.max(axis=0) - vals.min(axis=0)
        col_range[col_range == 0] = 1.0  # constant column -- every value is already
        # identical (diff=0), so the scale it's divided by doesn't affect the
        # outcome; this only avoids a 0/0 division.
        return col_range

    def _flag_duplicates(
        mask: npt.NDArray[np.bool_],
        cols: list[str],
        scale: npt.NDArray[np.float64],
    ) -> None:
        idx = np.flatnonzero(mask)
        if len(idx) < 2:  # noqa: PLR2004 -- nothing to compare a single row against
            return
        sub = df.loc[idx, cols].to_numpy(dtype=float)
        pairs = cKDTree(sub / scale).query_pairs(r=tol_frac, p=np.inf, output_type="ndarray")
        if len(pairs) == 0:
            return
        keep[idx[pairs[:, 1]]] = False  # scipy guarantees pairs[:, 0] < pairs[:, 1] --
        # idx is sorted ascending (np.flatnonzero), so the later COLUMN of
        # every pair is always the later-occurring row in the original data.

    # Params' scale comes from the FULL dataframe, reused identically for
    # both the feasible and infeasible comparisons below -- objectives only
    # exist for feasible rows, so their scale can only come from there.
    param_scale = _observed_range(param_names)
    combined_scale = np.concatenate([param_scale, _observed_range(objective_names, feasible)])

    _flag_duplicates(feasible, [*param_names, *objective_names], combined_scale)
    _flag_duplicates(~feasible, param_names, param_scale)

    return df[keep].reset_index(drop=True)


def train_surrogate(
    training_df: pd.DataFrame,
    param_names: list[str],
    objective_names: list[str],
    regressor_factory: RegressorFactory | None = None,
    classifier_n_estimators: int = 300,
    cv_folds: int = 5,
    seed: int | None = 1,
    classifier_threshold: float = 0.5,
    quiet: bool = False,
) -> SurrogateModel:
    """Fit one per-objective regressor (default: ``MLPRegressor``), plus a feasibility ``RandomForestClassifier``.

    ``regressor_factory`` defaults to ``mlp_regressor_factory()``
    (seeded with this call's own ``seed``) when omitted -- pass e.g.
    ``gaussian_process_regressor_factory()``, or ``REGRESSOR_FACTORIES["gaussian_process"]()``,
    to swap it. See ``SurrogateModel``'s docstring for the tradeoff.

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

    Unless ``quiet``, prints one line per objective (CV, then final fit) and
    one for the classifier, each with elapsed seconds -- a ``GaussianProcessRegressor``
    fit in particular is silent and can run for minutes on a few thousand
    feasible rows (cross-validated AND refit, per objective, each with
    several hyperparameter-optimizer restarts), so without this a slow but
    healthy fit is indistinguishable from a hang in a SLURM job's log.
    """
    if regressor_factory is None:
        regressor_factory = mlp_regressor_factory(seed=seed)

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
    x_scaler = StandardScaler().fit(x)
    x_scaled = x_scaler.transform(x)
    models: dict[str, Any] = {}
    y_scalers: dict[str, StandardScaler] = {}
    cv_r2: dict[str, float] = {}
    cv_mae: dict[str, float] = {}
    kfold = KFold(n_splits=cv_folds, shuffle=True, random_state=seed)
    for name in objective_names:
        y = feasible[name].to_numpy(dtype=float)
        y_scaler = StandardScaler().fit(y.reshape(-1, 1))
        y_scaled = y_scaler.transform(y.reshape(-1, 1)).ravel()
        y_scalers[name] = y_scaler

        start = time.perf_counter()
        if not quiet:
            print(f"train_surrogate: cross-validating regressor for {name!r} ({len(feasible)} rows)...")
        cv_model = regressor_factory(x.shape[1])
        y_pred_scaled = cross_val_predict(cv_model, x_scaled, y_scaled, cv=kfold)
        y_pred = y_scaler.inverse_transform(y_pred_scaled.reshape(-1, 1)).ravel()
        cv_r2[name] = r2_score(y, y_pred)
        cv_mae[name] = mean_absolute_error(y, y_pred)
        if not quiet:
            print(
                f"train_surrogate: {name!r} CV done in {time.perf_counter() - start:.1f}s (r2={cv_r2[name]:.4f})",
            )

        start = time.perf_counter()
        model = regressor_factory(x.shape[1])
        model.fit(x_scaled, y_scaled)
        models[name] = model
        if not quiet:
            print(f"train_surrogate: {name!r} final fit done in {time.perf_counter() - start:.1f}s")

    x_all = training_df[param_names].to_numpy(dtype=float)
    y_feasible_all = training_df["success"].to_numpy(dtype=bool)
    if len(np.unique(y_feasible_all)) < 2:  # noqa: PLR2004
        msg = "training_df has only one class (all feasible or all infeasible) -- can't train a classifier"
        raise ValueError(msg)

    start = time.perf_counter()
    if not quiet:
        print(f"train_surrogate: cross-validating feasibility classifier ({len(training_df)} rows)...")
    stratified_kfold = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=seed)
    cv_classifier = RandomForestClassifier(n_estimators=classifier_n_estimators, random_state=seed, n_jobs=-1)
    y_feasible_pred = cross_val_predict(cv_classifier, x_all, y_feasible_all, cv=stratified_kfold)
    classifier_cv_accuracy = accuracy_score(y_feasible_all, y_feasible_pred)
    classifier_cv_recall_infeasible = recall_score(y_feasible_all, y_feasible_pred, pos_label=False)
    if not quiet:
        print(f"train_surrogate: classifier CV done in {time.perf_counter() - start:.1f}s")

    classifier = RandomForestClassifier(n_estimators=classifier_n_estimators, random_state=seed, n_jobs=-1)
    classifier.fit(x_all, y_feasible_all)

    return SurrogateModel(
        param_names=param_names,
        objective_names=objective_names,
        x_scaler=x_scaler,
        models=models,
        y_scalers=y_scalers,
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
