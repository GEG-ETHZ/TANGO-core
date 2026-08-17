r"""Multi-objective optimization API for tango_next, built on pymoo.

Adapted to tango_next's actual seams:

- **Parameters mutate config dicts, not live objects.** ``Workflow.to_dict()``'s
  own class docstring already shows this exact pattern (``cfg =
  base_wf.to_dict(); cfg[...] = ...; Workflow(cfg).run()``) — a fresh
  ``Workflow`` is built and run from a mutated copy of the base config on
  every evaluation, rather than trying to mutate a live, already-solved
  ``Workflow`` in place.
- **Constraint violations are real pymoo constraints, not objective-space
  penalties.** A common alternative pattern falls back to a fixed huge
  objective value (e.g. ``1.02e12``) on simulation failure — that value has
  to be large enough to dominate every real objective, which makes it
  scale-dependent and easy to get wrong. Here, a failed evaluation
  instead sets a real ``out["G"]`` constraint violation (``> 0``); pymoo's
  own constraint-domination ranking (feasible always beats infeasible,
  regardless of ``F``) means the objective fallback value's magnitude is
  irrelevant, so it can just be ``0.0`` rather than a magic huge number.
- **Only specific, known-physical failure modes become a CV — everything
  else raises.** ``_evaluate_one`` catches exactly ``_CV_EXCEPTIONS``
  (``CoolPropError``, ``FrackingViolationError``, ``ConvergenceError``) —
  the ``tango_next`` errors that genuinely mean "this sampled design is
  infeasible," not "something is broken." A bare ``except Exception``
  would also swallow ``ConfigError`` (almost always a bug in a
  ``ParamSpec.apply``, not an infeasible design) and the
  ``LockedStateError`` family (internal contract violations), silently
  poisoning results across a long unattended search instead of crashing
  loudly where the bug actually is.

``InjectionPolicy`` restriction: only ``MANUAL`` and ``MANUAL_FRACKING_CHECK``
are accepted (see ``Minimization.__init__``). ``AUTO_BOTH`` raises
``NotImplementedError`` from ``SystemBCIteration.run_timestep`` outright (see
``InjectionPolicy.AUTO_BOTH``'s own docstring — old-tango-parity-only, not
under active development). ``AUTO_PRESSURE``/``AUTO_FLOW`` ARE implemented,
but deliberately NOT accepted here: each drives its own inner Newton/Picard
loop that actively overwrites a field (``components.<surface>.injection_pressure``
for ``AUTO_PRESSURE``, ``sim_config.mass_rate`` for ``AUTO_FLOW``) every
timestep — exactly the kind of field an app script's own ``ParamSpec`` might
hand to pymoo as a decision variable. Accepting either would mean pymoo's
outer search and ``SystemBCIteration``'s own inner solver fighting over the
same parameter, with whichever one writes last silently winning — not a
"maybe investigate this," a real correctness hazard any future policy widening
must design
around (e.g. rejecting the combination of a policy that owns a field and a
``ParamSpec`` that also targets it), not just re-check informally.
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import logging
import multiprocessing
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
import pandas as pd
import yaml
from matplotlib.ticker import MaxNLocator
from pymoo.algorithms.base.genetic import GeneticAlgorithm
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.initialization import Initialization
from pymoo.core.problem import ElementwiseProblem, LoopedElementwiseEvaluation, StarmapParallelization
from pymoo.core.result import Result
from pymoo.core.sampling import Sampling
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.operators.sampling.lhs import LHS
from pymoo.termination.default import DefaultMultiObjectiveTermination as DMOT
from pymoo.util.display.column import Column
from pymoo.util.display.output import Output

from tango_next.core.errors import (
    ConvergenceError,
    CoolPropError,
    FrackingViolationError,
    InvalidPowerStateError,
)
from tango_next.core.policies import InjectionPolicy
from tango_next.utils import print_dt
from tango_next.workflows.workflow import Workflow

# The only tango_next-specific exceptions actually reachable under
# MANUAL/MANUAL_FRACKING_CHECK as of 2026-08-13 (see _evaluate_one) that represent a
# genuine "this sampled design is physically/numerically infeasible"
# outcome, as opposed to a real bug: CoolPropError (fluid-property lookup
# fails for this design's T/P), FrackingViolationError (design exceeds a
# real hydraulic-fracking threshold), ConvergenceError (injection-T guess
# doesn't settle within budget), InvalidPowerStateError (a pump or the
# surface plant reports physically-impossible negative power near a
# design's feasibility boundary — see core/errors.py's docstring; without
# this CV, that negative value would get averaged into
# DoubletEconomicComponent.net_power_W and could flip a subtraction into an
# addition, silently producing a deceptively low LCOE for an infeasible
# design instead of excluding it). Deliberately NOT ConfigError (raised
# almost entirely during config loading/parsing — hitting it from a
# ParamSpec-mutated config points at a bug in a ParamSpec.apply, not an
# infeasible design) or the LockedStateError family (internal get/set-
# ordering contract violations, i.e. real bugs in tango_next's state
# management) -- those, and any bare Python exception, should crash the
# whole run rather than silently poison results across an unattended
# search.
_CV_EXCEPTIONS: tuple[type[Exception], ...] = (
    CoolPropError,
    FrackingViolationError,
    ConvergenceError,
    InvalidPowerStateError,
)

logger = logging.getLogger(__name__)

ALLOWED_POLICIES: tuple[InjectionPolicy, ...] = (
    InjectionPolicy.MANUAL,
    InjectionPolicy.MANUAL_FRACKING_CHECK,
)

DEFAULT_SAVE_DIR = Path("outputs/pymoo")

# pymoo's own DefaultMultiObjectiveTermination() constructor defaults
# (verified: DMOT().x.termination.tol == 0.0005, DMOT().f.termination.tol
# == 0.005) — used here as this module's own defaults rather than
# hardcoding unrelated numbers, so "sensible default" actually means
# "matches what pymoo itself considers a sensible default."
_DEFAULT_XTOL = 0.0005
_DEFAULT_FTOL = 0.005

# A failed evaluation's objective fallback — the magnitude genuinely does
# not matter, unlike a scale-dependent huge-penalty-constant approach.
# Thoroughly checked, not just asserted from reading pymoo's source: ran
# the actual RankAndCrowding survival operator NSGA2 uses (not a
# hypothetical) against a synthetic population with this fallback set to
# 0.0, 1e12, and -1e12 in turn -- identical rank/CV/survival outcome every
# time, including the -1e12 case, which would trivially "win" a naive
# F-comparison if F's magnitude were actually being used. Confirms
# Dominator.get_relation decides purely from CV when CV differs between
# individuals, never inspecting F at all in that case (2026-08-12).
_CV_OBJECTIVE_FALLBACK = 0.0
_FEASIBLE_G = -1.0
_INFEASIBLE_G = 1.0


@dataclass
class PymooConfig:
    """Pymoo hyperparameters for ``Minimization.run()``.

    Defaults chosen to match pymoo's own ``DefaultMultiObjectiveTermination()``
    defaults (``ftol``/``xtol``) and ``NSGA2()``'s own default population
    size, so "the defaults" here actually mean pymoo's own defaults, not
    arbitrary tango_next-specific numbers.
    """

    n_max_gen: int = 200
    """Maximum generations — hard cap even if ftol/xtol convergence is never reached."""
    ftol: float = _DEFAULT_FTOL
    """Objective-space convergence tolerance."""
    xtol: float = _DEFAULT_XTOL
    """Design-space (parameter) convergence tolerance."""
    pop_size: int = 40
    """Population size per generation."""
    n_processes: int = 1
    """Number of worker processes for parallel evaluation. ``1`` = serial
    (``LoopedElementwiseEvaluation``); ``>1`` spins up a ``multiprocessing.Pool``
    and uses pymoo's ``StarmapParallelization``."""
    seed: int | None = 1
    """Random seed passed to ``pymoo.optimize.minimize`` — fixes it for
    reproducibility by default (matches pymoo's own convention of a fixed
    default rather than a random one); pass ``None`` for a non-reproducible
    (system-entropy-seeded) run instead."""
    crossover_prob: float | None = None
    """Probability two parents actually recombine (pymoo's default
    crossover operator, ``SBX``, calls this ``prob`` — default ``0.9`` if
    left ``None`` here). Only applied when ``Minimization`` builds the
    DEFAULT algorithm itself (no explicit ``algorithm=`` passed) — same
    rule as ``pop_size`` above: a caller-supplied ``algorithm`` already
    has its own operators configured and this is ignored, not merged in."""
    mutation_prob: float | None = None
    """Probability each variable gets mutated (pymoo's default mutation
    operator, ``PM``, calls this ``prob`` — default ``1/n_var`` if left
    ``None`` here). Same ``algorithm=`` caveat as ``crossover_prob`` above."""


def load_params(params_file: Path) -> dict[str, Any]:
    """Load optimization hyperparameters from a ``params.yaml`` file, if present.

    Same pattern across every ``opt_*`` app script: DVC's ``dvc.yaml``
    declares which of these keys it tracks for staleness, but the calling
    script is what actually reads the values — DVC doesn't inject them
    into the command line.
    """
    if params_file.exists():
        return yaml.safe_load(params_file.read_text()) or {}
    return {}


def build_pymoo_parser(
    description: str,
    default_output_dir: Path,
    params: dict[str, Any] | None = None,
) -> argparse.ArgumentParser:
    """Build the shared CLI for ``opt_*`` pymoo-optimization app scripts.

    Every ``opt_*`` script needs the exact same mechanical plumbing:
    exposing ``PymooConfig``'s own fields as CLI flags (an explicit CLI
    flag overrides ``params``, which overrides ``PymooConfig``'s own
    default — one source of truth for "the default"), plus a handful of
    generic execution-control flags (``--quiet``, ``--log-level``,
    ``--save-dir``, ``--clean``, ``--seed-from``). None of that is
    domain-specific — unlike ``ParamSpec``/``ObjectiveSpec`` (see their
    own docstrings), which DO stay in the calling script because they
    encode assumptions about a specific physical system. This function is
    the shared, non-domain-specific half of an ``opt_*`` script's CLI;
    each script calls it, then can ``.add_argument(...)`` on the returned
    parser for anything script-specific it ever needs.

    No ``--skip-minimize``-style flag threading a previous-results cache:
    ``Minimization`` already manages its own worker pool internally via
    ``PymooConfig.n_processes``, and there's no cached-results-loading
    feature to expose a flag for.

    Args:
        description: This script's own one-line description (shown in
            ``--help``).
        default_output_dir: Default ``--save-dir`` value.
        params: Already-loaded ``params.yaml`` dict (see ``load_params``).

    """
    params = params or {}
    default_pymoo_config = PymooConfig()
    parser = argparse.ArgumentParser(description=description)

    n_max_gen_default = params.get("n_max_gen", default_pymoo_config.n_max_gen)
    pop_size_default = params.get("pop_size", default_pymoo_config.pop_size)
    ftol_default = params.get("ftol", default_pymoo_config.ftol)
    xtol_default = params.get("xtol", default_pymoo_config.xtol)
    seed_default = params.get("seed", default_pymoo_config.seed)
    parser.add_argument(
        "--n-max-gen",
        type=int,
        default=n_max_gen_default,
        help=f"Max generations (hard cap). Defaults to {n_max_gen_default} (params.yaml/PymooConfig).",
    )
    parser.add_argument(
        "--pop-size",
        type=int,
        default=pop_size_default,
        help=f"Population size per generation. Defaults to {pop_size_default} (params.yaml/PymooConfig).",
    )
    parser.add_argument(
        "--ftol",
        type=float,
        default=ftol_default,
        help=f"Objective-space convergence tolerance. Defaults to {ftol_default} (params.yaml/PymooConfig).",
    )
    parser.add_argument(
        "--xtol",
        type=float,
        default=xtol_default,
        help=f"Design-space convergence tolerance. Defaults to {xtol_default} (params.yaml/PymooConfig).",
    )
    crossover_prob_default = params.get("crossover_prob", default_pymoo_config.crossover_prob)
    mutation_prob_default = params.get("mutation_prob", default_pymoo_config.mutation_prob)
    parser.add_argument(
        "--crossover-prob",
        type=float,
        default=crossover_prob_default,
        help=(
            f"Probability two parents recombine (pymoo SBX's own prob). Defaults to "
            f"{crossover_prob_default} (params.yaml/PymooConfig; None -> pymoo's own default)."
        ),
    )
    parser.add_argument(
        "--mutation-prob",
        type=float,
        default=mutation_prob_default,
        help=(
            f"Probability each variable mutates (pymoo PM's own prob). Defaults to "
            f"{mutation_prob_default} (params.yaml/PymooConfig; None -> pymoo's own 1/n_var default)."
        ),
    )
    n_processes_default = params.get("n_processes", default_pymoo_config.n_processes)
    parser.add_argument(
        "-p",
        "--n-processes",
        type=int,
        default=n_processes_default,
        help=f"Worker processes for parallel evaluation (1 = serial). Defaults to {n_processes_default} (params.yaml/PymooConfig).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=seed_default,
        help=f"Random seed for reproducibility. Defaults to {seed_default} (params.yaml/PymooConfig). Ignored if --no-seed is given.",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Pass seed=None instead (non-reproducible run) — overrides --seed.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help=(
            "Suppress pymoo's per-generation progress table (printed by default — "
            "useful for seeing a long unattended run, e.g. a SLURM job, is actually "
            "progressing rather than stalled)."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help=(
            "Python logging level for tango_next's own loggers (workflow "
            "loading, per-timestep orchestrator state) — independent of "
            "--quiet, which only controls pymoo's own progress table. "
            "Defaults to WARNING. INFO/DEBUG print on EVERY evaluation "
            "across the whole run, not just once."
        ),
    )
    parser.add_argument(
        "--save-dir",
        type=Path,
        default=default_output_dir,
        help=f"Where to write results/plots. Defaults to {default_output_dir}.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help=(
            "Delete --save-dir entirely before running. Without this, a run "
            "producing FEWER pareto designs than a previous run leaves the "
            "previous run's extra pareto_configs/design_NNN.yml files behind "
            "(Minimization._save() only overwrites indices that exist in the "
            "CURRENT result, it doesn't clear stale ones) — easy to mistake "
            "for part of the current result."
        ),
    )
    parser.add_argument(
        "--seed-from",
        type=Path,
        default=None,
        help=(
            "Path to a previous run's pareto_results.csv (or "
            "pareto_results_partial.csv from an interrupted run) to "
            "warm-start the initial population from, instead of pymoo's "
            "default random/LHS init. NOT a true resume (fresh RNG state, "
            "restarts at generation 1) -- see Minimization's seed_from "
            "docstring for the full tradeoff. Remaining population slots "
            "beyond what the file provides are filled via LHS."
        ),
    )
    return parser


def plot_objective_vs_param_scatter(
    df: pd.DataFrame,
    param_cols: list[str],
    objective_cols: list[str],
    out_path: Path,
    title: str = "Pareto front — objectives vs. parameters",
) -> None:
    """Grid of 2D scatter plots: one subplot per (objective, parameter) pair.

    Complements the parallel-coordinates/objective-space plots every
    ``opt_*`` script already builds — those show the pareto front as a
    whole, but don't make it easy to read off "how does this ONE
    parameter move THIS ONE objective" at a glance, especially once a
    front has 3+ decision variables. One row per objective, one column
    per parameter, so a scan down any column shows that parameter's
    effect on every objective, and a scan across any row shows every
    parameter's effect on that objective. Deliberately generic (plain
    column-name lists, no assumption about how many params/objectives
    or what they're called) — same reasoning as ``build_pymoo_parser``,
    not ``ParamSpec``/``ObjectiveSpec``: this is mechanical plotting
    plumbing, not a domain-specific choice, so it belongs here rather
    than duplicated in every ``opt_*`` script.
    """
    n_rows = len(objective_cols)
    n_cols = len(param_cols)
    fig, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=(3.6 * n_cols, 3.2 * n_rows),
        squeeze=False,
    )
    for i, obj_col in enumerate(objective_cols):
        for j, param_col in enumerate(param_cols):
            ax = axes[i][j]
            ax.scatter(df[param_col], df[obj_col], s=25, color="tab:blue", alpha=0.7, zorder=3)
            ax.grid(visible=True, alpha=0.3)
            # A pareto front commonly bunches a parameter into a narrow band
            # (e.g. a converged-to-one-value decision variable) -- the
            # default tick count/rotation then overlaps into an unreadable
            # smear of overlapping labels. Capping to 4 ticks and rotating
            # gives each label room regardless of how narrow the column's
            # actual data range is.
            ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
            for label in ax.get_xticklabels():
                label.set_rotation(30)
                label.set_ha("right")
            if i == n_rows - 1:
                ax.set_xlabel(param_col)
            if j == 0:
                ax.set_ylabel(obj_col)

    fig.suptitle(title, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_param_pair_vs_objective_scatter(
    df: pd.DataFrame,
    param_cols: list[str],
    objective_cols: list[str],
    out_path: Path,
    title: str = "Pareto front — objective vs. parameter pairs",
) -> None:
    """Grid of 2D parameter-pair scatter plots, each point colored by an objective.

    ``plot_objective_vs_param_scatter`` only shows one parameter's MARGINAL
    effect on an objective at a time — it can't reveal an interaction, e.g.
    "high LCOE only when mass rate AND injection pressure are BOTH high,"
    where neither parameter alone would show the pattern in its own
    marginal plot. Here, each subplot's (x, y) axes are a PAIR of
    parameters and the point COLOR is one objective's value — a visual
    cross-correlation view an ordinary 1D scatter can't provide. One row
    per parameter pair (every 2-combination of ``param_cols``, via
    ``itertools.combinations`` — order-independent, no duplicate/reversed
    pairs), one column per objective.

    With only 2 parameters there is exactly one pair (one row); with N
    parameters there are N*(N-1)/2 pairs/rows, growing quickly — fine for
    the 3-4 parameter searches this module's ``opt_*`` callers currently
    run, but a caller with a much larger parameter count should expect a
    correspondingly tall figure.

    Same generic, column-name-list design as
    ``plot_objective_vs_param_scatter`` (see that function's docstring for
    why this lives here rather than duplicated per ``opt_*`` script).
    """
    pairs = list(itertools.combinations(param_cols, 2))
    n_rows = len(pairs)
    n_cols = len(objective_cols)
    fig, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=(4.2 * n_cols, 3.6 * n_rows),
        squeeze=False,
    )
    for i, (param_x, param_y) in enumerate(pairs):
        for j, obj_col in enumerate(objective_cols):
            ax = axes[i][j]
            sc = ax.scatter(
                df[param_x],
                df[param_y],
                c=df[obj_col],
                cmap="viridis",
                s=35,
                zorder=3,
            )
            fig.colorbar(sc, ax=ax, label=obj_col, pad=0.02)
            ax.grid(visible=True, alpha=0.3)
            ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
            for label in ax.get_xticklabels():
                label.set_rotation(30)
                label.set_ha("right")
            ax.set_xlabel(param_x)
            ax.set_ylabel(param_y)
            if i == 0:
                ax.set_title(obj_col)

    fig.suptitle(title, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


@dataclass
class ParamSpec:
    """One decision variable pymoo can tweak.

    ``pymoo_api.py`` is deliberately generic — it has NO built-in
    ``ParamSpec`` instances of its own, and none should be added here.
    Every concrete param (mass flow rate, injection pressure, a reservoir's
    own inlet/outlet-mismatch handling, whatever a future coupled model
    needs) belongs in the calling app script (e.g.
    ``applications/tango_next/opt_hydro_df_electric/opt_hydro_df_electric.py``),
    not in this module — this module doesn't need to, and must not, know
    what fields any particular system exposes. Duplicating a param's
    definition across multiple app scripts that happen to need the same
    one is expected and fine; it is NOT evidence that param belongs here
    instead.

    Args:
        name: Column name in the results dataframe.
        apply: ``(config_dict, value) -> config_dict`` — mutates (and
            returns) a copy of the base config with this parameter set to
            ``value``. Must be a module-level, picklable callable (a
            closure defined inside a factory function can't be pickled —
            ``pickle``/``multiprocessing`` serialize callables by module +
            qualified name and can't re-import a runtime-only local
            closure. That only breaks in the ``n_processes > 1`` path
            (``multiprocessing.Pool.starmap`` requires every argument,
            including this callable, to pickle) — confirmed empirically
            the first time ``n_processes=2`` was actually exercised, back
            when this pattern still lived in this module: it raised
            ``AttributeError: Can't pickle local object
            '<factory>.<locals>.apply'``. A module-level dataclass with
            ``__call__`` pickles fine, by class reference + simple field
            values — use that shape, not a closure.)
        bounds: ``(lower, upper)`` bound pymoo searches within.

    """

    name: str
    apply: Callable[[dict[str, Any], float], dict[str, Any]]
    bounds: tuple[float, float]


@dataclass
class ObjectiveSpec:
    """One objective pymoo minimizes.

    Same rule as ``ParamSpec`` above: no built-in ``ObjectiveSpec``
    instances live in this module — every concrete objective (LCOE, mean
    electric power, mean thermal power, whatever a future system's own
    economics/output looks like) belongs in the calling app script.

    Args:
        name: Column name in the results dataframe.
        evaluate: ``(solved_workflow) -> float`` — pymoo minimizes this
            value, so a "maximize energy" goal must be expressed as its
            negative. Same module-level-callable/picklability requirement
            as ``ParamSpec.apply`` above.

    """

    name: str
    evaluate: Callable[[Workflow], float]


# ---------------------------------------------------------------------------
# Live progress output (verbose=True)
# ---------------------------------------------------------------------------


class ParetoProgressOutput(Output):
    """Per-generation progress table for ``Minimization.run()`` (``verbose=True``).

    Two design choices worth calling out explicitly:

    1. **Scale mixing.** Summing RAW, unnormalized objective values before
       taking a norm is only meaningful if every objective is on a
       comparable scale. Not true here (LCOE ~0.1-1,
       ``negative_mean_power_W`` ~1e6-1e7): the larger-magnitude objective would
       completely dominate, making the metric say almost nothing about the
       smaller one. Z-score normalizing each objective column (subtract
       its mean, divide by its std, both computed fresh from the CURRENT
       front every generation) puts them on equal footing before summing.
    2. **Consistent solution set.** ``n_nds`` and ``euclid_min`` both report
       on ``algorithm.opt`` (the non-dominated front), not a mix of
       ``algorithm.opt`` for one column and ``algorithm.pop`` (the WHOLE
       population, including dominated individuals) for the other — two
       columns should describe the same set, not different ones.

    This only changes what prints during a run (nothing here touches the
    saved results dataframe, which already reports on the final pareto
    front only, not the full population).
    """

    def __init__(self) -> None:
        """Set up the extra progress columns."""
        super().__init__()
        self.t_start = time.perf_counter()
        self.n_nds = Column("n_nds", width=8)
        self.t_s = Column("t [s]", width=10)
        self.euclid_min = Column("euclid_min (z)", width=16)
        self.columns += [self.n_nds, self.t_s, self.euclid_min]

    def update(self, algorithm: GeneticAlgorithm) -> None:
        """Refresh each column from the current generation's non-dominated front."""
        super().update(algorithm)
        opt_f = algorithm.opt.get("F")
        self.n_nds.set(len(algorithm.opt))
        self.t_s.set(f"{time.perf_counter() - self.t_start:.3g}")
        if opt_f is None or len(opt_f) == 0:
            self.euclid_min.set("n/a")
            return
        opt_f = np.asarray(opt_f, dtype=float)
        std = opt_f.std(axis=0)
        std = np.where(std > 0, std, 1.0)  # constant column -> no scaling, avoid /0
        z = (opt_f - opt_f.mean(axis=0)) / std
        euclid = np.sqrt((z**2).sum(axis=1)).min()
        self.euclid_min.set(f"{euclid:.3g}")


# ---------------------------------------------------------------------------
# Minimization
# ---------------------------------------------------------------------------


@dataclass
class Minimization:
    """Multi-objective optimization over a tango_next ``Workflow``, via pymoo.

    Usage — ``ParamSpec``/``ObjectiveSpec`` factories are defined by the
    CALLING SCRIPT, not by this module (see their own docstrings for why)::

        # Defined in the calling app script, e.g.
        # applications/tango_next/opt_hydro_df_electric/opt_hydro_df_electric.py —
        # NOT in pymoo_api.py itself.
        wf = Workflow.from_file("examples/tango_next/hydro_df_electric.yml")
        m = Minimization(
            base_workflow=wf,
            params=[
                mass_rate_param(bounds=(10.0, 100.0)),
                injection_pressure_param(bounds=(1e6, 10e6)),
            ],
            objectives=[lcoe_objective(), negative_mean_power_objective()],
        )
        res, df = m.run()

    Args:
        base_workflow: Template ``Workflow`` — its config (via ``to_dict()``)
            is the starting point every evaluation mutates a copy of. Never
            mutated or re-run itself.
        params: Decision variables — see ``ParamSpec``'s own docstring for
            why the concrete factories live in the calling script, not here.
        objectives: Objectives to minimize — see ``ObjectiveSpec``'s own
            docstring, same reasoning as ``params`` above.
        pymoo_config: Hyperparameters — see ``PymooConfig``. Defaults to
            ``PymooConfig()`` if omitted.
        algorithm: Any pymoo ``GeneticAlgorithm`` instance — defaults to
            ``NSGA2(pop_size=pymoo_config.pop_size)``, but any other
            algorithm (NSGA3, etc.) can be passed instead; this class
            never hardcodes NSGA2-specific behavior elsewhere.
        verbose: Print pymoo's per-generation progress table.
        save_results: Write the results dataframe (CSV) and, if
            ``save_pareto_configs``, every pareto-front design's config
            (YAML) to ``save_dir``. Default ``True``.
        save_pareto_configs: Save each pareto-front design's CONFIG DICT
            (not a solved live ``Workflow``) as its own YAML file —
            trivially re-run via ``Workflow.from_file(path).run()``, and
            avoids pickling live TESPy/CoolProp state that a solved object
            would carry. Default ``True``.
        save_dir: Where to save results — default ``outputs/pymoo/``.
        seed_from: Path to a previous run's ``pareto_results.csv`` (or
            ``pareto_results_partial.csv`` — same schema) to WARM-START
            the initial population from, instead of pymoo's default
            random/LHS init. A cheap alternative to true checkpoint/resume
            (which would need to pickle the whole ``Algorithm`` — including
            a live ``multiprocessing.Pool`` when ``n_processes > 1``, which
            can't be pickled at all): this only reuses the numeric param
            columns already sitting in a saved CSV, so it works
            unconditionally regardless of ``n_processes``. NOT a true
            resume — the new run starts at generation 1 with a fresh RNG
            state, just seeded with better-than-random starting points.
            The non-dominated designs from ``seed_from`` are combined with
            ``pad_sampling``-generated designs to fill out the rest of
            ``algorithm.pop_size`` (if ``seed_from`` has MORE designs than
            ``pop_size``, only the first ``pop_size`` are used). Default
            ``None`` (no seeding, pymoo's normal init).
        pad_sampling: pymoo ``Sampling`` used to fill out the population
            beyond what ``seed_from`` provides. Default ``LHS()`` — better
            design-space coverage than plain random sampling for the
            "fill in the rest" role. Only used if ``seed_from`` is given.
        log_failures: Append one JSON line per constraint-violating
            evaluation (see ``_CV_EXCEPTIONS``) to ``save_dir /
            "failures.jsonl"`` — the mutated parameter values plus the
            exception type/message. No objective values are logged for a
            failure: a design either fully evaluates (all objectives
            computed) or raises before any of them are — there's no partial
            objective to save. Off by default (extra I/O on every
            failure); turn on when characterizing WHERE/WHY a search is
            failing (e.g. mapping which parameter region a given
            ``InvalidPowerStateError``/``CoolPropError`` clusters in)
            instead of re-deriving it from ad hoc scratch scripts each time.

    Raises:
        ValueError: If ``base_workflow``'s own ``sim_config.injection_mode``
            is not one of the two allowed policies (see module docstring).

    """

    base_workflow: Workflow
    params: list[ParamSpec]
    objectives: list[ObjectiveSpec]
    pymoo_config: PymooConfig | None = None
    algorithm: GeneticAlgorithm | None = None
    verbose: bool = False
    save_results: bool = True
    save_pareto_configs: bool = True
    save_dir: Path | str = DEFAULT_SAVE_DIR
    seed_from: Path | str | None = None
    pad_sampling: Sampling | None = None
    log_failures: bool = False

    # Derived/internal state, not constructor args -- set in __post_init__.
    base_cfg: dict[str, Any] = field(init=False, repr=False)
    policy: InjectionPolicy = field(init=False)
    n_failures: int = field(init=False, default=0)
    """Count of evaluations that raised (CV, not crash) — inspect after ``run()``."""

    def __post_init__(self) -> None:
        """Validate ``policy``, resolve ``base_cfg``/``algorithm``/``pad_sampling`` defaults.

        NOTE for readers cross-checking against method bodies below: mypy
        does NOT treat these resolved-in-place values (``pymoo_config``,
        ``algorithm``, ``save_dir``, ``pad_sampling`` — every field here
        whose declared type admits ``None``/``str`` but is always resolved
        to a concrete value by the time ``__post_init__`` returns) as
        narrowed everywhere else in the class the way a plain `__init__`'s
        inferred-per-assignment attribute types would be — a dataclass
        field's declared type is fixed from its class-level annotation, full
        stop (confirmed empirically: even re-annotating the assignment
        target here doesn't change what mypy sees in OTHER methods).
        ``_elementwise_runner``/``run``/``_save_intermediate``/
        ``_write_pareto`` each carry a short ``assert``/``isinstance`` at
        the top to re-narrow -- see their docstrings/comments, not repeated
        here.
        """
        self.base_cfg = self.base_workflow.to_dict()
        # No policy= override -- always the base config's OWN choice.
        # Confirmed the hard way: an earlier override param let a caller
        # (opt_hydro_df_electric.py) never pass it at all, silently forcing
        # MANUAL and skipping hydro_df_electric.yml's own
        # manual-fracking-check setting entirely, with no error to catch it.
        # An unsupported policy (AUTO_*) is a real setup error -- raise
        # rather than silently coercing it to something else.
        policy = InjectionPolicy(self.base_cfg["sim_config"]["injection_mode"])
        if policy not in ALLOWED_POLICIES:
            raise ValueError(
                f"Minimization only supports {[p.value for p in ALLOWED_POLICIES]!r}, got {policy.value!r} — "
                "AUTO_BOTH raises NotImplementedError in SystemBCIteration outright (old-tango-parity-only, "
                "not under active development); AUTO_PRESSURE/AUTO_FLOW ARE implemented but not accepted "
                "here either (see module docstring).",
            )
        self.policy = policy
        self.params = list(self.params)
        self.objectives = list(self.objectives)
        self.pymoo_config = self.pymoo_config or PymooConfig()
        if self.algorithm is None:
            # Only pass crossover/mutation to NSGA2 if actually overridden --
            # NSGA2's own kwarg defaults are already fully-configured SBX()/
            # PM() instances, not None, so passing crossover=None here would
            # override them with a real None instead of falling back.
            default_algo_kwargs: dict[str, Any] = {}
            if self.pymoo_config.crossover_prob is not None:
                default_algo_kwargs["crossover"] = SBX(prob=self.pymoo_config.crossover_prob)
            if self.pymoo_config.mutation_prob is not None:
                default_algo_kwargs["mutation"] = PM(prob=self.pymoo_config.mutation_prob)
            self.algorithm = NSGA2(pop_size=self.pymoo_config.pop_size, **default_algo_kwargs)
        self.save_dir = Path(self.save_dir)
        self.seed_from = Path(self.seed_from) if self.seed_from is not None else None
        self.pad_sampling = self.pad_sampling if self.pad_sampling is not None else LHS()

    def _load_seed_x(self, path: Path) -> npt.NDArray[np.float64]:
        """Read a previous run's results CSV, return its param columns as an ``(n, n_var)`` array.

        Column order matches ``self.params`` — the CSV must have been
        written by THIS same ``Minimization`` setup (same params, same
        names), which is the only case that makes sense to seed from
        anyway.
        """
        seed_df = pd.read_csv(path)
        cols = [p.name for p in self.params]
        missing = [c for c in cols if c not in seed_df.columns]
        if missing:
            raise ValueError(
                f"seed_from={path} is missing column(s) {missing!r} — does it come from a "
                "Minimization run with the same params (same names, same order)?",
            )
        return seed_df[cols].to_numpy(dtype=float)

    def _build_config(self, x: list[float]) -> dict[str, Any]:
        """Apply every ``ParamSpec`` to a fresh copy of ``base_cfg``."""
        cfg = copy.deepcopy(self.base_cfg)
        for spec, value in zip(self.params, x, strict=True):
            cfg = spec.apply(cfg, value)
        return cfg

    def _log_failure(self, x: list[float], exc: Exception) -> None:
        """Append one JSON line to ``save_dir / "failures.jsonl"`` — see ``log_failures`` docstring."""
        assert isinstance(self.save_dir, Path)  # __post_init__ always resolves this
        self.save_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "params": {p.name: value for p, value in zip(self.params, x, strict=True)},
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
        with (self.save_dir / "failures.jsonl").open("a") as f:
            f.write(json.dumps(record) + "\n")

    def _evaluate_one(self, x: list[float]) -> tuple[list[float], list[float]]:
        """Build, run, and score one design — CV on _CV_EXCEPTIONS, raise on anything else."""
        cfg = self._build_config(x)
        try:
            wf = Workflow(cfg)
            wf.run()
        except _CV_EXCEPTIONS as exc:
            self.n_failures += 1
            if self.verbose:
                logger.info("Evaluation failed (treated as constraint violation): %s", exc)
            if self.log_failures:
                self._log_failure(x, exc)
            return [_CV_OBJECTIVE_FALLBACK] * len(self.objectives), [_INFEASIBLE_G]
        return [spec.evaluate(wf) for spec in self.objectives], [_FEASIBLE_G]

    def _elementwise_runner(self) -> LoopedElementwiseEvaluation | StarmapParallelization:
        assert self.pymoo_config is not None  # __post_init__ always resolves this — see its docstring
        if self.pymoo_config.n_processes <= 1:
            return LoopedElementwiseEvaluation()
        pool = multiprocessing.Pool(self.pymoo_config.n_processes)
        return StarmapParallelization(pool.starmap)

    def run(self) -> tuple[Result, pd.DataFrame]:
        """Run the optimization and return pymoo's raw ``Result`` plus a results dataframe.

        Runs generation-by-generation (``algorithm.setup()`` + a
        ``while algorithm.has_next(): algorithm.next()`` loop) instead of
        pymoo's ``minimize()`` convenience wrapper — behaviorally identical
        (that's literally what ``minimize()`` does internally), but this
        gives a hook between generations to save the CURRENT non-dominated
        front after every one (``_save_intermediate``, if ``save_results``)
        — if the run gets killed (SLURM time limit, ^C, crash) partway
        through, whatever the front looked like as of the LAST completed
        generation is already on disk, not lost.

        Returns:
            ``(res, df)`` — ``res`` is pymoo's own ``Result`` (``res.X``/
            ``res.F`` are the pareto-front decision variables/objectives);
            ``df`` has one row per pareto-front design, one column per
            param, one column per objective, plus ``euclidean`` (see
            ``_build_results_df``).

        """
        # __post_init__ always resolves these (see its docstring) — asserts
        # narrow mypy's view back down from the constructor-facing
        # Optional/str types to what they're actually guaranteed to be here.
        assert self.pymoo_config is not None
        assert self.algorithm is not None
        assert self.pad_sampling is not None
        assert isinstance(self.save_dir, Path)

        problem = _Problem(self)
        termination = DMOT(
            xtol=self.pymoo_config.xtol,
            ftol=self.pymoo_config.ftol,
            n_max_gen=self.pymoo_config.n_max_gen,
        )
        logger.info(
            "Minimization: %d params, %d objectives, pop_size=%d, policy=%s",
            len(self.params),
            len(self.objectives),
            self.pymoo_config.pop_size,
            self.policy.value,
        )
        print("Minimization.run() starting at")
        print_dt()

        # copy_algorithm=True is minimize()'s own default -- avoids mutating
        # self.algorithm in place, so the same Minimization instance could
        # in principle be .run() more than once without carrying state over.
        algorithm = copy.deepcopy(self.algorithm)
        if self.seed_from is not None:
            # __post_init__ always normalizes a given str to a Path (or
            # leaves it None) -- `is not None` alone only narrows away the
            # None branch, not the constructor-facing str possibility.
            assert isinstance(self.seed_from, Path)
            seed_x = self._load_seed_x(self.seed_from)
            pop_size = algorithm.pop_size
            if len(seed_x) > pop_size:
                logger.info(
                    "seed_from=%s has %d designs, more than pop_size=%d -- using the first %d.",
                    self.seed_from,
                    len(seed_x),
                    pop_size,
                    pop_size,
                )
                seed_x = seed_x[:pop_size]
            n_pad = pop_size - len(seed_x)
            if n_pad > 0:
                pad_pop = self.pad_sampling(problem, n_pad)
                seed_x = np.vstack([seed_x, pad_pop.get("X")])
            logger.info(
                "Warm-starting from %s: %d seeded design(s) + %d %s-padded design(s) = pop_size=%d.",
                self.seed_from,
                pop_size - n_pad,
                n_pad,
                type(self.pad_sampling).__name__,
                pop_size,
            )
            # Mirrors GeneticAlgorithm.__init__'s own construction of
            # self.initialization from `sampling` -- swapping in our seeded
            # ndarray while preserving whatever repair/eliminate_duplicates
            # this algorithm was already configured with.
            algorithm.initialization = Initialization(
                seed_x,
                repair=algorithm.repair,
                eliminate_duplicates=algorithm.eliminate_duplicates,
            )
        algorithm.setup(
            problem,
            termination=termination,
            seed=self.pymoo_config.seed,
            verbose=self.verbose,
            save_history=False,
            output=ParetoProgressOutput(),
        )
        while algorithm.has_next():
            algorithm.next()
            if self.save_results:
                self._save_intermediate(algorithm)
        res = algorithm.result()

        df = self._build_results_df(res.X, res.F, n_gen=algorithm.n_gen)
        if self.n_failures:
            logger.info(
                "Minimization: %d evaluations were constraint violations (failed to solve).",
                self.n_failures,
            )
        if self.save_results:
            self._write_pareto(
                res.X,
                df,
                self.save_dir / "pareto_results.csv",
                self.save_dir / "pareto_configs" if self.save_pareto_configs else None,
            )
        return res, df

    def _save_intermediate(self, algorithm: GeneticAlgorithm) -> None:
        """Write the CURRENT (possibly not yet converged) non-dominated front.

        Called after every generation — see ``run()``'s docstring for why.
        Deliberately separate filenames from the final save
        (``pareto_results_partial.csv``/``pareto_configs_partial/``) so a
        completed run's real output is never ambiguous with a leftover
        partial one from an interrupted run.
        """
        assert isinstance(self.save_dir, Path)  # __post_init__ always resolves this
        opt = algorithm.opt
        x = None if opt is None or len(opt) == 0 else opt.get("X")
        f = None if opt is None or len(opt) == 0 else opt.get("F")
        df = self._build_results_df(x, f, n_gen=algorithm.n_gen)
        self._write_pareto(
            x,
            df,
            self.save_dir / "pareto_results_partial.csv",
            self.save_dir / "pareto_configs_partial" if self.save_pareto_configs else None,
        )

    def _build_results_df(
        self,
        x: npt.NDArray[np.float64] | None,
        f: npt.NDArray[np.float64] | None,
        n_gen: int | None = None,
    ) -> pd.DataFrame:
        """Pareto-front results (params ``x`` + objectives ``f``) as a dataframe.

        Adds a ``euclidean`` aggregate column and (if ``n_gen`` given) an
        ``n_gen`` provenance column — useful on the intermediate saves
        (``_save_intermediate``) to see at a glance which generation a
        partial front is from; harmless on the final save too.

        ``euclidean`` is a Z-SCORE-NORMALIZED Euclidean distance
        (``sqrt(Σ z_i²)``, ``z_i = (objective_i - mean) / std`` across the
        pareto front) — deliberately NOT a sum of RAW objective values,
        which would be dominated by whichever objective happens to have the
        largest units (e.g. here, ``negative_mean_power_W`` ~1e6-1e7 vs.
        LCOE ~0.1-1 — the raw version would make LCOE contribute nothing).
        Normalization is computed fresh from this call's own pareto front
        and used ONLY inline, in the expression below — every column saved
        to ``df``/the CSV stays in its original, un-normalized units, so
        a different normalization can always be recomputed later from the
        raw data without having lost anything.
        """
        if x is None or f is None:
            return pd.DataFrame(columns=[p.name for p in self.params] + [o.name for o in self.objectives])

        x = x if x.ndim == 2 else x.reshape(1, -1)
        f = f if f.ndim == 2 else f.reshape(1, -1)

        x_df = pd.DataFrame(x, columns=[p.name for p in self.params])
        f_df = pd.DataFrame(f, columns=[o.name for o in self.objectives])
        df = pd.concat([x_df, f_df], axis=1)
        std = f_df.std().replace(0.0, 1.0)  # constant column -> no scaling, avoid /0
        z = (f_df - f_df.mean()) / std
        df["euclidean"] = (z**2).sum(axis=1).pow(0.5)
        if n_gen is not None:
            df["n_gen"] = n_gen
        return df

    def _write_pareto(
        self,
        x: npt.NDArray[np.float64] | None,
        df: pd.DataFrame,
        csv_path: Path,
        configs_dir: Path | None,
    ) -> None:
        """Write ``df`` to ``csv_path`` and, if ``configs_dir`` given, one YAML per row of ``x``."""
        assert isinstance(self.save_dir, Path)  # __post_init__ always resolves this
        self.save_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_path, index=False)
        logger.info("Wrote %s", csv_path)

        if configs_dir is None or x is None:
            return
        configs_dir.mkdir(exist_ok=True)
        x = x if x.ndim == 2 else x.reshape(1, -1)
        for i, row in enumerate(x):
            cfg = self._build_config(list(row))
            (configs_dir / f"design_{i:03d}.yml").write_text(yaml.safe_dump(cfg, sort_keys=False))
        logger.info("Wrote %d pareto-design configs to %s", len(x), configs_dir)


class _Problem(ElementwiseProblem):
    """pymoo ``ElementwiseProblem`` wrapping one ``Minimization``.

    Private: users construct ``Minimization``, not this class directly.
    """

    def __init__(self, mgr: Minimization) -> None:
        """Wrap ``mgr``, deriving pymoo's required n_var/n_obj/bounds from it."""
        self.mgr = mgr
        super().__init__(
            n_var=len(mgr.params),
            n_obj=len(mgr.objectives),
            n_ieq_constr=1,
            xl=[p.bounds[0] for p in mgr.params],
            xu=[p.bounds[1] for p in mgr.params],
            elementwise_runner=mgr._elementwise_runner(),  # noqa: SLF001
        )

    def _evaluate(self, x: list[float], out: dict[str, Any], *args: Any, **kwargs: Any) -> None:
        f, g = self.mgr._evaluate_one(list(x))  # noqa: SLF001
        out["F"] = f
        out["G"] = g
