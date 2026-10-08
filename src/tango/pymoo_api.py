r"""Multi-objective optimization API for tango, built on pymoo.

Adapted to tango's actual seams:

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
  else raises.** ``_evaluate_one`` catches exactly ``INFEASIBLE_DESIGN_EXCEPTIONS``
  (``CoolPropError``, ``FrackingViolationError``, ``ConvergenceError``,
  ``InvalidPowerStateError``, ``CoolingLimitError``) —
  the ``tango`` errors that genuinely mean "this sampled design is
  infeasible," not "something is broken." A bare ``except Exception``
  would also swallow ``ConfigError`` (almost always a bug in a
  ``ParamSpec.apply``, not an infeasible design) and the
  ``LockedStateError`` family (internal contract violations), silently
  poisoning results across a long unattended search instead of crashing
  loudly where the bug actually is.

``InjectionPolicy`` restriction: only ``MANUAL`` and ``MANUAL_FRACKING_CHECK``
are accepted (see ``Minimization.__init__``). ``AUTO_BOTH`` raises
``NotImplementedError`` from ``SystemBCIteration.run_timestep`` outright (see
``InjectionPolicy.AUTO_BOTH``'s own docstring — not under active
development). ``AUTO_PRESSURE``/``AUTO_FLOW`` ARE implemented,
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
import shutil
import sys
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
from matplotlib.colors import Normalize
from matplotlib.ticker import MaxNLocator
from pymoo.algorithms.base.genetic import GeneticAlgorithm
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.duplicate import DuplicateElimination
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

from tango.core.errors import (
    ConvergenceError,
    CoolingLimitError,
    CoolPropError,
    FrackingViolationError,
    InvalidPowerStateError,
)
from tango.core.policies import InjectionPolicy
from tango.utils import print_dt
from tango.workflows.workflow import Workflow

# The only tango-specific exceptions actually reachable under
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
# design instead of excluding it), CoolingLimitError (a cooler or condenser
# below the site's cooling limit). Also what tango.surrogate_api counts as an
# infeasible sample, so the two can't drift apart. Deliberately NOT ConfigError (raised
# almost entirely during config loading/parsing — hitting it from a
# ParamSpec-mutated config points at a bug in a ParamSpec.apply, not an
# infeasible design) or the LockedStateError family (internal get/set-
# ordering contract violations, i.e. real bugs in tango's state
# management) -- those, and any bare Python exception, should crash the
# whole run rather than silently poison results across an unattended
# search.
INFEASIBLE_DESIGN_EXCEPTIONS: tuple[type[Exception], ...] = (
    CoolingLimitError,
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
_DEFAULT_PERIOD = 50
"""DMOT's own ``period`` default -- the number of consecutive generations
ftol/xtol/cvtol must each stay satisfied for before that alone ends the
run (pymoo's ``RobustTermination`` window, shared across all three by
DMOT's own constructor)."""

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


class ParamToleranceDuplicateElimination(DuplicateElimination):
    """Two designs are duplicates if EVERY param is within ``tol_frac`` of the other's, per-param.

    Unlike pymoo's own ``DefaultDuplicateElimination`` (one combined
    Euclidean distance against a single absolute ``epsilon``, which
    silently conflates parameters of wildly different scales/units — e.g.
    ``mass_rate_kg_per_s`` O(10-200) vs ``injection_pressure_Pa``
    O(1e6-1e7), where an epsilon large enough to catch near-duplicate
    pressures would swamp mass_rate entirely, and vice versa), this checks
    each parameter independently against its OWN ``bounds`` range —
    matches ``surrogate_api._cached_row_is_valid``'s per-param
    ``math.isclose`` convention elsewhere in this codebase, rather than one
    unitless combined distance.

    Used as ``NSGA2(..., eliminate_duplicates=ParamToleranceDuplicateElimination(params, tol_frac))``
    — pymoo's ``Mating.do()`` calls this BEFORE evaluating offspring, so a
    near-duplicate design is never actually real-simulated at all, not
    just filtered out afterward. Only catches duplicates within the
    current offspring batch and against the current population
    (``algorithm.pop``) — NOT against the full multi-generation trajectory
    history, since pymoo's mating only ever compares against what's live
    right now. A design from 3 generations ago that's since been selected
    out of the population can still be near-duplicated by a later
    generation; a supplementary whole-history dedup pass would be needed
    to close that gap (not built — see REDESIGN_TODO.md's Q2).
    """

    def __init__(self, params: list[ParamSpec], tol_frac: float) -> None:
        """``tol_frac`` of each param's own ``bounds`` range is that param's tolerance."""
        super().__init__()
        self.scale = np.array([p.bounds[1] - p.bounds[0] for p in params])
        self.tol_frac = tol_frac

    def _do(self, pop: Any, other: Any, is_duplicate: npt.NDArray[np.bool_]) -> npt.NDArray[np.bool_]:
        x = pop.get("X")
        y = x if other is None else other.get("X")
        close = (np.abs(x[:, None, :] - y[None, :, :]) <= self.tol_frac * self.scale[None, None, :]).all(
            axis=2,
        )
        if other is None:
            # Only flag against EARLIER individuals (mirrors
            # DefaultDuplicateElimination's own triu masking) -- otherwise
            # every member of a duplicate pair/group gets flagged instead
            # of just the later occurrence(s).
            close[np.triu_indices(len(x))] = False
        is_duplicate[np.any(close, axis=1)] = True
        return is_duplicate


@dataclass
class PymooConfig:
    """Pymoo hyperparameters for ``Minimization.run()``.

    Defaults chosen to match pymoo's own ``DefaultMultiObjectiveTermination()``
    defaults (``ftol``/``xtol``) and ``NSGA2()``'s own default population
    size, so "the defaults" here actually mean pymoo's own defaults, not
    arbitrary tango-specific numbers.
    """

    n_max_gen: int = 200
    """Maximum generations — hard cap even if ftol/xtol convergence is never reached."""
    ftol: float = _DEFAULT_FTOL
    """Objective-space convergence tolerance."""
    xtol: float = _DEFAULT_XTOL
    """Design-space (parameter) convergence tolerance."""
    termination_period: int = _DEFAULT_PERIOD
    """Generations ftol/xtol/cvtol must each stay satisfied for,
    consecutively, before that alone ends the run (pymoo's
    ``RobustTermination`` window, passed straight through to
    ``DefaultMultiObjectiveTermination``'s own ``period`` arg — a single
    converged-looking generation isn't enough; convergence must be
    sustained). Larger = more confidence a plateau is real, at the cost of
    running that many more generations past wherever it actually started."""
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
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=(
            f"{description} Every flag below defaults to whatever "
            "params.yaml/PymooConfig sets (see each flag's own help text for "
            "its current default); passing that flag explicitly on the "
            "command line overrides params.yaml for this run only -- "
            "params.yaml itself is never modified."
        ),
    )

    n_max_gen_default = params.get("n_max_gen", default_pymoo_config.n_max_gen)
    pop_size_default = params.get("pop_size", default_pymoo_config.pop_size)
    ftol_default = params.get("ftol", default_pymoo_config.ftol)
    xtol_default = params.get("xtol", default_pymoo_config.xtol)
    termination_period_default = params.get("termination_period", default_pymoo_config.termination_period)
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
    parser.add_argument(
        "--termination-period",
        type=int,
        default=termination_period_default,
        help=(
            "Generations ftol/xtol/cvtol must each stay satisfied for, consecutively, before that "
            f"alone ends the run. Defaults to {termination_period_default} (params.yaml/PymooConfig) "
            "-- pymoo's own DefaultMultiObjectiveTermination default. Lowering this makes "
            "convergence-based early stopping trigger sooner off a shorter observed plateau, at the "
            "cost of less confidence that plateau is real rather than a temporary lull."
        ),
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
            "Python logging level for tango's own loggers (workflow "
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
    plot_group = parser.add_mutually_exclusive_group()
    plot_group.add_argument(
        "--plot-only",
        action="store_true",
        help=(
            "Skip the baseline/optimization entirely and only (re)generate "
            "plots from an existing --save-dir/pareto_results.csv. Lets a "
            "DVC 'plot' stage depend on plotting code alone (a plot-only "
            "code change reruns just this, not a full NSGA2 search) — the "
            "companion 'optimize' stage uses --no-plot below."
        ),
    )
    plot_group.add_argument(
        "--no-plot",
        action="store_true",
        help=(
            "Run the baseline/optimization as normal but skip plotting "
            "afterward. For a DVC 'optimize' stage whose outs are only "
            "pareto_results.csv/pareto_configs — a separate 'plot' stage "
            "(--plot-only) owns the plot files, so this stage shouldn't "
            "also produce (and immediately make stale) copies of them."
        ),
    )
    return parser


_COLUMN_PREFIXES = ("par:", "obj:", "rep:")


def strip_column_prefixes(df: pd.DataFrame) -> pd.DataFrame:
    """Undo ``Minimization._write_pareto``'s ``par:``/``obj:``/``rep:`` CSV column prefixes.

    For a script's ``--plot-only`` path, which re-reads a previously-saved
    ``pareto_results.csv`` from disk: that file has the prefixed names
    (see ``Minimization._column_rename``), but every plotting function
    (``DISPLAY_RENAME``/``COLUMN_LABELS`` dicts, ``prepare_plot_df``, etc.)
    still works in terms of bare names, matching what a freshly-``run()``
    ``Minimization`` returns in memory. Round-tripping through this
    function keeps that one consumer consistent with the other, rather
    than requiring plotting code to know about the on-disk-only prefix.
    """
    rename = {c: c.split(":", 1)[1] for c in df.columns if c.startswith(_COLUMN_PREFIXES)}
    return df.rename(columns=rename)


def prepare_plot_df(df: pd.DataFrame, display_rename: dict[str, str]) -> pd.DataFrame:
    """Undo pymoo's negated-objective minimization convention, for plotting only.

    A maximization objective (e.g. mean power/thermal power) is expressed to
    NSGA2 as ``negative_mean_*_W`` so minimizing it maximizes the real
    quantity — but a human reading a plot cares about power PRODUCED, not
    the sign flip NSGA2 needed. This renames columns per ``display_rename``
    (e.g. ``{"negative_mean_power_W": "mean_power_W"}``) and negates any
    renamed column whose ORIGINAL name started with ``"negative_"`` back to
    its natural sign — inferred from the name, not a separately-maintained
    list, so a script can't add/rename an objective without the negation
    rule automatically following it.

    ``df``/the saved CSV (``pareto_results.csv``) keep the objective's own
    (negated) sign always — only the returned copy is flipped. Use this
    (not a hand-rolled ``df.rename(...)`` + manual ``-df[col]`` line) for
    ANY plot built from pareto results, including one-off replotting from a
    previously-saved CSV — a hand-rolled version is exactly what silently
    reintroduced a raw ``negative_mean_thermal_power_W`` axis into
    ``opt_AGS_direct_heat``'s parallel-coordinates plot once, when a fix
    unrelated to this renaming/sign convention regenerated the plot
    straight from the CSV and skipped it.
    """
    plot_df = df.rename(columns=display_rename)
    for original_name, display_name in display_rename.items():
        if original_name.startswith("negative_") and display_name in plot_df.columns:
            plot_df[display_name] = -plot_df[display_name]
    return plot_df


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
    ``applications/opt_hydro_df_electric/opt_hydro_df_electric.py``),
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


@dataclass
class ConstraintSpec:
    """One inequality constraint pymoo enforces, IN ADDITION TO physical feasibility.

    Same rule as ``ParamSpec``/``ObjectiveSpec`` above: no built-in
    ``ConstraintSpec`` instances live in this module — every concrete
    constraint (a minimum production temperature, a maximum pressure, etc.)
    belongs in the calling app script.

    Every ``Minimization`` already rejects a design that raises one of
    ``_cv_exceptions`` (a genuine physical-simulation failure) via a
    built-in constraint — ``ConstraintSpec`` is for a DIFFERENT kind of
    infeasibility: the simulation solved successfully, but the resulting
    design isn't acceptable on some other engineering ground (e.g. a
    district-heating design that solves fine but delivers water too cold to
    be useful). Both kinds feed the SAME pymoo constraint-domination
    ranking (feasible always beats infeasible, regardless of objective
    values) — see ``_Problem``'s ``n_ieq_constr`` and ``Minimization.
    _evaluate_one``.

    Args:
        name: Label only — constraint G values aren't retained in
            ``Minimization``'s results dataframe (only ``params``/
            ``objectives`` are), same as the built-in physical-feasibility
            constraint.
        evaluate: ``(solved_workflow) -> float``, pymoo's own inequality
            convention: ``<= 0`` is satisfied, ``> 0`` is a violation. Return
            a genuine violation MAGNITUDE where possible (e.g. ``105.0 -
            T_prod_C``, degrees below the threshold), not just a flat
            ``+1``/``-1`` sign — pymoo's constraint-domination ranking only
            needs the sign to decide feasible-vs-not, but a continuous
            magnitude gives the search itself more gradient to climb back
            toward feasibility, the same way a real objective would. Same
            module-level-callable/picklability requirement as
            ``ParamSpec.apply``/``ObjectiveSpec.evaluate`` above.
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
    """Multi-objective optimization over a tango ``Workflow``, via pymoo.

    Usage — ``ParamSpec``/``ObjectiveSpec`` factories are defined by the
    CALLING SCRIPT, not by this module (see their own docstrings for why)::

        # Defined in the calling app script, e.g.
        # applications/opt_hydro_df_electric/opt_hydro_df_electric.py —
        # NOT in pymoo_api.py itself.
        wf = Workflow.from_file("example_configs/hydro_df_electric.yml")
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
        constraints: Extra inequality constraints beyond the built-in
            physical-feasibility one — see ``ConstraintSpec``. Default
            ``()`` (no extra constraints).
        report_specs: Extra per-design read-outs, computed once for the
            final pareto front only and merged into the results dataframe
            — NOT a real objective, doesn't affect the search. See its own
            field docstring. Default ``()`` (no extra columns).
        log_failures: Append one JSON line per constraint-violating
            evaluation (see ``INFEASIBLE_DESIGN_EXCEPTIONS``) to ``save_dir /
            "failures.jsonl"`` — the mutated parameter values plus the
            exception type/message. No objective values are logged for a
            failure: a design either fully evaluates (all objectives
            computed) or raises before any of them are — there's no partial
            objective to save. Off by default (extra I/O on every
            failure); turn on when characterizing WHERE/WHY a search is
            failing (e.g. mapping which parameter region a given
            ``InvalidPowerStateError``/``CoolPropError`` clusters in)
            instead of re-deriving it from ad hoc scratch scripts each time.
        extra_cv_exceptions: Additional exception TYPES (beyond the
            built-in ``INFEASIBLE_DESIGN_EXCEPTIONS`` — ``CoolPropError``/
            ``FrackingViolationError``/``ConvergenceError``/
            ``InvalidPowerStateError``) that ``_evaluate_one`` also treats
            as a constraint violation rather than letting crash the whole
            run. EXTENDS the built-in set (merged into ``self._cv_exceptions``
            in ``__post_init__``), never replaces it — a caller widens what
            counts as "this design is infeasible," it doesn't get to narrow
            the base physical-failure modes. Meant for a caller-specific
            exception type not (yet) common enough to belong in the shared
            base tuple — e.g. a surrogate-model evaluator's own "classifier
            predicts infeasible" signal (see ``tango.surrogate_api``).
            Default ``()`` (no change from the base set).
        capture_trajectory_path: If given, append every generation's
            newly-evaluated individuals (not just the final front) to this
            CSV path as surrogate training data — see
            ``_append_trajectory``. Default ``None`` (no capture).

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
    constraints: list[ConstraintSpec] = field(default_factory=list)
    """Extra inequality constraints beyond the built-in physical-feasibility
    one — see ``ConstraintSpec``. Default ``()`` (no extra constraints,
    identical behavior to before this field existed)."""
    report_specs: list[ObjectiveSpec] = field(default_factory=list)
    """Extra per-design read-outs (SAME ``(wf) -> float`` shape as
    ``ObjectiveSpec``) computed ONCE for the FINAL pareto front only and
    merged into the results dataframe/CSV/plots — NOT fed to NSGA2 as a
    real objective, so it never affects which designs survive or the
    front's shape/dimensionality. Use this for a value worth reporting
    (e.g. OPEX) that you deliberately don't want the search itself
    optimizing for or against. See ``_add_report_columns``. Default ``()``
    (no extra columns)."""
    log_failures: bool = False
    extra_cv_exceptions: tuple[type[Exception], ...] = ()
    capture_trajectory_path: Path | str | None = None
    """If given, append EVERY generation's newly-evaluated individuals
    (params + objectives if feasible + a ``success`` bool) to this CSV
    path, one row per individual — not just the final pareto front.
    Row schema matches ``tango.surrogate_api``'s training-data
    convention exactly, so ``train_surrogate()`` can consume the result
    unmodified regardless of whether it came from an LHS sweep or a real
    optimizer's own search trajectory. See ``_append_trajectory``."""

    # Derived/internal state, not constructor args -- set in __post_init__.
    base_cfg: dict[str, Any] = field(init=False, repr=False)
    policy: InjectionPolicy = field(init=False)
    n_failures: int = field(init=False, default=0)
    """Count of evaluations that raised (CV, not crash) — inspect after ``run()``."""
    _cv_exceptions: tuple[type[Exception], ...] = field(init=False, repr=False)
    """``INFEASIBLE_DESIGN_EXCEPTIONS`` merged with ``extra_cv_exceptions`` — what ``_evaluate_one`` actually catches."""
    _trajectory_row_idx: int = field(init=False, default=0, repr=False)
    """Running counter for ``_append_trajectory``'s ``row_idx`` column, across generations."""

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
                "AUTO_BOTH raises NotImplementedError in SystemBCIteration outright (not under active "
                "development); AUTO_PRESSURE/AUTO_FLOW ARE implemented but not accepted "
                "here either (see module docstring).",
            )
        self.policy = policy
        self.params = list(self.params)
        self.objectives = list(self.objectives)
        self.constraints = list(self.constraints)
        self.report_specs = list(self.report_specs)
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
        self.capture_trajectory_path = (
            Path(self.capture_trajectory_path) if self.capture_trajectory_path is not None else None
        )
        self.seed_from = Path(self.seed_from) if self.seed_from is not None else None
        self.pad_sampling = self.pad_sampling if self.pad_sampling is not None else LHS()
        self._cv_exceptions = INFEASIBLE_DESIGN_EXCEPTIONS + tuple(self.extra_cv_exceptions)

    def _load_seed_x(self, path: Path) -> npt.NDArray[np.float64]:
        """Read a previous run's results CSV, return its param columns as an ``(n, n_var)`` array.

        Column order matches ``self.params`` — the CSV must have been
        written by THIS same ``Minimization`` setup (same params, same
        names), which is the only case that makes sense to seed from
        anyway. Reads the ``par:``-prefixed column names ``_write_pareto``
        writes (see ``_column_rename``) — a CSV from before that prefix
        existed won't be found here; regenerate it rather than seeding
        from a stale-format file.
        """
        seed_df = pd.read_csv(path)
        cols = [f"par:{p.name}" for p in self.params]
        missing = [c for c in cols if c not in seed_df.columns]
        if missing:
            raise ValueError(
                f"seed_from={path} is missing column(s) {missing!r} — does it come from a "
                "Minimization run with the same params (same names, same order)?",
            )
        return seed_df[cols].to_numpy(dtype=float)

    def _column_rename(self) -> dict[str, str]:
        """``par:``/``obj:``/``rep:`` prefix for each column ``_write_pareto`` writes to CSV.

        Cosmetic and applied ONLY at CSV-write time — ``self.params``/
        ``self.objectives``/``self.report_specs``' own ``.name`` values,
        the in-memory ``df`` this class returns from ``run()``, and every
        plotting function downstream all keep using bare (unprefixed)
        names throughout; only what lands in the CSV on disk changes.
        Columns not covered here (currently just ``euclidean``) are left
        bare — they're neither a decision variable, an active objective,
        nor a ``report_specs`` read-out, so no category prefix applies.
        """
        rename = {p.name: f"par:{p.name}" for p in self.params}
        rename.update({o.name: f"obj:{o.name}" for o in self.objectives})
        rename.update({r.name: f"rep:{r.name}" for r in self.report_specs})
        return rename

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
        """Build, run, and score one design — CV on self._cv_exceptions, raise on anything else.

        Returns ``len(self.constraints) + 1`` G values: index 0 is the
        built-in physical-feasibility constraint, the rest are
        ``self.constraints`` in order (see ``ConstraintSpec``). When the
        simulation itself raises a CV exception, every extra constraint
        reports ``float("inf")`` — NOT the flat ``_INFEASIBLE_G`` the
        built-in physical constraint uses. pymoo's own constraint-violation
        ranking sums every POSITIVE ``G`` across ALL constraints
        (``Dominator.calc_domination_matrix_loop``:
        ``CV = sum(G * (G > 0))``) — a real ``ConstraintSpec`` returns a
        genuine violation MAGNITUDE (see its own docstring), which can be
        much larger than the small flat ``_INFEASIBLE_G`` (``1.0``) used
        here. Reusing that same small flat value for a design that failed
        to even simulate would make a CRASHED design look like a SMALLER
        total violation than a design that ran successfully but is merely
        far from satisfying an extra constraint — actively rewarding
        physical failure over real, if still-infeasible, progress.
        ``float("inf")`` guarantees a physical failure is always worse
        than any finite real violation,
        regardless of that constraint's own scale — no per-constraint
        tuning needed, and safe for pymoo's ``<``-based CV comparison (no
        NaN, well-defined ordering).
        """
        cfg = self._build_config(x)
        try:
            wf = Workflow(cfg)
            wf.run()
        except self._cv_exceptions as exc:
            self.n_failures += 1
            if self.verbose:
                logger.info("Evaluation failed (treated as constraint violation): %s", exc)
            if self.log_failures:
                self._log_failure(x, exc)
            return [_CV_OBJECTIVE_FALLBACK] * len(self.objectives), [
                _INFEASIBLE_G,
                *([float("inf")] * len(self.constraints)),
            ]
        g_extra = [c.evaluate(wf) for c in self.constraints]
        return [spec.evaluate(wf) for spec in self.objectives], [_FEASIBLE_G, *g_extra]

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
        generation is already on disk, not lost. The same hook also drives
        ``_append_trajectory`` (if ``capture_trajectory_path``), appending
        every generation's newly-evaluated individuals — not just the
        front — as surrogate training data.

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
            period=self.pymoo_config.termination_period,
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
            if self.capture_trajectory_path is not None:
                self._append_trajectory(algorithm)
        res = algorithm.result()

        df = self._build_results_df(res.X, res.F)
        if self.report_specs:
            df = self._add_report_columns(df, res.X)
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
        df = self._build_results_df(x, f)
        self._write_pareto(
            x,
            df,
            self.save_dir / "pareto_results_partial.csv",
            self.save_dir / "pareto_configs_partial" if self.save_pareto_configs else None,
        )

    def _append_trajectory(self, algorithm: GeneticAlgorithm) -> None:
        """Append this generation's newly-evaluated individuals to ``capture_trajectory_path``.

        ``algorithm.off`` holds exactly the individuals evaluated by THIS
        call to ``next()`` — pymoo's own ``Algorithm.advance()`` sets
        ``self.off = infills`` unconditionally, including the very first
        (initialization) generation, so reading it once per generation,
        uniformly, captures every real evaluation exactly once — no
        special-casing generation 1, no double-counting the survivors
        carried forward in ``algorithm.pop``.

        Row schema matches ``surrogate_api``'s LHS-sweep training rows:
        one column per param, one column per objective (``NaN``, not
        absent, for an infeasible design — unlike ``evaluate_training_row``'s
        one-shot-``pd.DataFrame(rows)``-over-the-whole-list convention
        where a missing key is fine, appending one small ``DataFrame`` PER
        GENERATION means every chunk's column set/order must be identical,
        or ``to_csv(mode="a")`` silently misaligns columns instead of
        erroring — a generation where every individual happens to be
        infeasible would otherwise write a chunk with no objective columns
        at all), plus ``success`` (bool) and ``row_idx``. Appending
        (not accumulating in memory then writing once) mirrors
        ``_save_intermediate``'s own "don't lose progress if this run gets
        killed" philosophy — unlike an LHS sweep's rows, a killed NSGA2 run
        can't cheaply resume its SEARCH (would need to pickle the whole
        ``Algorithm``, including a live ``multiprocessing.Pool`` when
        ``n_processes > 1`` — see ``seed_from``'s own docstring for why
        that's not viable), but whatever generations DID complete stay on
        disk as usable training data either way.
        """
        assert isinstance(self.capture_trajectory_path, Path)  # __post_init__ always resolves this
        off = algorithm.off
        if off is None or len(off) == 0:
            return
        x = off.get("X")
        f = off.get("F")
        g = off.get("G")
        # off's own per-individual "n_gen" (set via infills.set("n_gen",
        # self.n_iter) in Algorithm.infill(), BEFORE n_iter/n_gen gets
        # incremented for the next round) -- algorithm.n_gen itself is a
        # property returning n_iter, which by the time next() RETURNS has
        # already been bumped for the round about to start, one ahead of
        # the individuals just evaluated.
        n_gen = off.get("n_gen")
        feasible = (g <= 0).all(axis=1)
        rows: list[dict[str, Any]] = []
        for i in range(len(off)):
            row: dict[str, Any] = {"row_idx": self._trajectory_row_idx}
            self._trajectory_row_idx += 1
            row.update({p.name: float(x[i, j]) for j, p in enumerate(self.params)})
            row.update(
                {
                    o.name: float(f[i, k]) if feasible[i] else float("nan")
                    for k, o in enumerate(self.objectives)
                },
            )
            row["success"] = bool(feasible[i])
            row["n_gen"] = int(n_gen[i])
            rows.append(row)
        df = pd.DataFrame(rows)
        self.capture_trajectory_path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not self.capture_trajectory_path.exists()
        df.to_csv(self.capture_trajectory_path, mode="a", header=write_header, index=False)

    def _build_results_df(
        self,
        x: npt.NDArray[np.float64] | None,
        f: npt.NDArray[np.float64] | None,
    ) -> pd.DataFrame:
        """Pareto-front results (params ``x`` + objectives ``f``) as a dataframe.

        Adds a ``euclidean`` aggregate column. Deliberately no ``n_gen``
        column — every row of one results dataframe comes from the SAME
        (final, or one intermediate) generation, so the column would be
        constant across the whole file and carry no actual information;
        ``ParetoProgressOutput``'s live
        per-generation console table (a genuinely different thing — it
        varies row-to-row over TIME, not over one saved file's rows) is
        unaffected.

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
        return df

    def _add_report_columns(self, df: pd.DataFrame, x: npt.NDArray[np.float64] | None) -> pd.DataFrame:
        """Re-solve each pareto-front design ONCE more to evaluate ``report_specs``, merge into ``df``.

        Cheap relative to the search itself: only ``len(df)`` extra real
        simulations (the FINAL front, not every generation), and never fed
        back into NSGA2. A design here already solved successfully once
        (that's how it made the front) — the SAME config re-solved
        deterministically succeeds again, so no CV handling is needed here
        the way ``_evaluate_one`` needs it.
        """
        if x is None or len(df) == 0:
            return df
        x = x if x.ndim == 2 else x.reshape(1, -1)
        report_cols: dict[str, list[float]] = {spec.name: [] for spec in self.report_specs}
        for row in x:
            wf = Workflow(self._build_config(list(row)))
            wf.run()
            for spec in self.report_specs:
                report_cols[spec.name].append(spec.evaluate(wf))
        for name, values in report_cols.items():
            df[name] = values
        return df

    def _write_pareto(
        self,
        x: npt.NDArray[np.float64] | None,
        df: pd.DataFrame,
        csv_path: Path,
        configs_dir: Path | None,
    ) -> None:
        """Write ``df`` to ``csv_path`` and, if ``configs_dir`` given, one YAML per row of ``x``.

        ``df`` itself is untouched — only the copy written to disk gets
        ``par:``/``obj:``/``rep:`` column-name prefixes (see
        ``_column_rename``), so callers keep working with bare names.
        """
        assert isinstance(self.save_dir, Path)  # __post_init__ always resolves this
        self.save_dir.mkdir(parents=True, exist_ok=True)
        df.rename(columns=self._column_rename()).to_csv(csv_path, index=False)
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
            n_ieq_constr=1 + len(mgr.constraints),
            xl=[p.bounds[0] for p in mgr.params],
            xu=[p.bounds[1] for p in mgr.params],
            elementwise_runner=mgr._elementwise_runner(),  # noqa: SLF001
        )

    def _evaluate(self, x: list[float], out: dict[str, Any], *args: Any, **kwargs: Any) -> None:
        f, g = self.mgr._evaluate_one(list(x))  # noqa: SLF001
        out["F"] = f
        out["G"] = g


# ---------------------------------------------------------------------------
# Shared opt_* app runner
# ---------------------------------------------------------------------------


@dataclass
class ObjectiveScatter:
    """Which two result columns an ``OptApp``'s objective-space scatter plots show.

    Args:
        x_col: Display column (after ``OptApp.display_rename``) on the x axis.
        x_label: x-axis label.
        y_col: Display column on the y axis.
        y_label: y-axis label, in the units after ``y_scale``.
        y_scale: Factor applied to ``y_col`` before plotting (e.g. ``1e-6``
            for W -> MW).
        color_col: Display column the points are colored by; ``None`` for a
            single color.

    """

    x_col: str
    x_label: str
    y_col: str
    y_label: str
    y_scale: float = 1.0
    color_col: str | None = None


@dataclass
class OptApp:
    """Everything that differs between ``opt_*`` app scripts; the rest is shared here.

    An app script builds one ``OptApp`` from its own ``ParamSpec``/
    ``ObjectiveSpec``/``ConstraintSpec`` factories (which stay in the app, see
    ``ParamSpec``'s docstring) and calls ``app.main()``. This class supplies the
    CLI, the forced injection policy, the baseline run, the ``Minimization``
    setup, and the plots, none of which depend on the system being optimized.

    Each param's ``apply`` must also have a ``read(config) -> float`` method
    returning the value the config currently holds, in the param's own units.
    The smoke tests use it to build narrow bounds around each config's own
    design point.

    Args:
        title: Short name used in plot titles, e.g. ``"AGS_ORC_electric"``.
        description: One-line ``--help`` description.
        config_path: The example config this app optimizes.
        app_dir: The app's directory (holds ``params.yaml`` and ``outputs/``).
        injection_mode: Injection policy forced onto the base workflow,
            whatever the config says (``manual`` or ``manual-fracking-check``;
            see ``Minimization``).
        default_bounds: Production bounds per param name.
        param_factory: ``bounds -> params``; called with ``default_bounds`` or
            an override with the same keys.
        objective_specs: Active NSGA2 objectives.
        report_specs: Reporting-only read-outs (see ``Minimization``).
        constraint_factory: ``parsed CLI args -> constraints``, so a
            constraint threshold can be a CLI flag (see ``configure_parser``).
        configure_parser: Adds app-specific CLI flags.
        display_rename: Negated-objective rename for plots (see
            ``prepare_plot_df``).
        column_labels: Full axis label per display column.
        scatter: Axes of the objective-space scatter plots.
        smoke_args: Extra CLI arguments ``--smoke`` adds, e.g. relaxing a
            constraint that a tiny population would otherwise miss entirely,
            leaving an empty Pareto front for the plots.

    """

    title: str
    description: str
    config_path: Path
    app_dir: Path
    injection_mode: InjectionPolicy
    default_bounds: dict[str, tuple[float, float]]
    param_factory: Callable[[dict[str, tuple[float, float]]], list[ParamSpec]]
    objective_specs: list[ObjectiveSpec]
    scatter: ObjectiveScatter
    report_specs: list[ObjectiveSpec] = field(default_factory=list)
    constraint_factory: Callable[[argparse.Namespace], list[ConstraintSpec]] | None = None
    configure_parser: Callable[[argparse.ArgumentParser], None] | None = None
    display_rename: dict[str, str] = field(default_factory=dict)
    column_labels: dict[str, str] = field(default_factory=dict)
    smoke_args: list[str] = field(default_factory=list)

    @property
    def params_file(self) -> Path:
        """This app's ``params.yaml``."""
        return self.app_dir / "params.yaml"

    @property
    def default_output_dir(self) -> Path:
        """This app's ``outputs/``."""
        return self.app_dir / "outputs"

    def param_specs(self, bounds: dict[str, tuple[float, float]] | None = None) -> list[ParamSpec]:
        """Decision variables with ``default_bounds``, or ``bounds`` (same keys) instead.

        Raises:
            ValueError: If ``bounds``' keys, or the factory's param names,
                don't match ``default_bounds``' keys.

        """
        b = self.default_bounds if bounds is None else bounds
        if set(b) != set(self.default_bounds):
            raise ValueError(f"bounds keys {sorted(b)} must match {sorted(self.default_bounds)}")
        specs = self.param_factory(b)
        names = [p.name for p in specs]
        if sorted(names) != sorted(self.default_bounds):
            raise ValueError(f"param names {names} must match bounds keys {sorted(self.default_bounds)}")
        return specs

    def build_parser(self) -> argparse.ArgumentParser:
        """``build_pymoo_parser`` plus ``--smoke`` and this app's own flags."""
        parser = build_pymoo_parser(
            description=self.description,
            default_output_dir=self.default_output_dir,
            params=load_params(self.params_file),
        )
        parser.add_argument(
            "--smoke",
            action="store_true",
            help=(
                "Fast end-to-end check: a 2-generation search with population 6, plus this app's own "
                f"relaxations ({' '.join(self.smoke_args) or 'none'}). Combine with --save-dir pointing at a "
                "throwaway directory."
            ),
        )
        if self.configure_parser is not None:
            self.configure_parser(parser)
        return parser

    def parse_args(self, argv: list[str] | None = None) -> argparse.Namespace:
        """Parse ``argv`` (default ``sys.argv[1:]``); ``--smoke`` appends its settings, which win."""
        parser = self.build_parser()
        argv = sys.argv[1:] if argv is None else argv
        args = parser.parse_args(argv)
        if args.smoke:
            args = parser.parse_args([*argv, "--n-max-gen", "2", "--pop-size", "6", *self.smoke_args])
        return args

    def base_config(self) -> dict[str, Any]:
        """The example config with ``injection_mode`` forced to this app's policy."""
        cfg: dict[str, Any] = yaml.safe_load(self.config_path.read_text())
        cfg["sim_config"]["injection_mode"] = self.injection_mode.value
        return cfg

    def build_baseline(self) -> tuple[Workflow, Workflow]:
        """Return ``(wf, wf_manual)``: the UNRUN template and a separately run baseline.

        ``wf`` must stay unrun: ``Minimization`` builds every evaluation's
        config from ``wf.to_dict()``, which includes each component's history,
        so a run ``wf`` would pre-populate every evaluation with the baseline's
        timesteps. ``wf_manual`` is an independent copy built through
        ``Workflow(wf.to_dict())`` (``copy.deepcopy`` doesn't survive
        ``GraphSurface``'s live TESPy network) and run only to report the
        baseline.
        """
        wf = Workflow(self.base_config())
        wf_manual = Workflow(wf.to_dict())
        wf_manual.run()
        return wf, wf_manual

    def run_optimization(
        self,
        base_wf: Workflow,
        args: argparse.Namespace,
        param_specs: list[ParamSpec] | None = None,
    ) -> tuple[Result, pd.DataFrame, Minimization]:
        """Run NSGA2 over ``param_specs`` (default: ``self.param_specs()``).

        Returns:
            ``(res, df, m)``.

        """
        m = Minimization(
            base_workflow=base_wf,
            params=self.param_specs() if param_specs is None else param_specs,
            objectives=self.objective_specs,
            constraints=self.constraint_factory(args) if self.constraint_factory is not None else [],
            report_specs=self.report_specs,
            pymoo_config=PymooConfig(
                n_max_gen=args.n_max_gen,
                pop_size=args.pop_size,
                ftol=args.ftol,
                xtol=args.xtol,
                termination_period=args.termination_period,
                n_processes=args.n_processes,
                seed=None if args.no_seed else args.seed,
                crossover_prob=args.crossover_prob,
                mutation_prob=args.mutation_prob,
            ),
            verbose=not args.quiet,
            save_dir=args.save_dir,
            seed_from=args.seed_from,
        )
        res, df = m.run()
        return res, df, m

    def pretty_label(self, column: str) -> str:
        """``column_labels[column]`` if there is one, else ``column``."""
        return self.column_labels.get(column, column)

    def make_plots(self, df: pd.DataFrame, save_dir: Path) -> None:
        """Build every plot from a pareto-front dataframe (bare column names).

        No empty-``df`` guard: an empty front means no feasible design was
        found, which should fail loudly here.
        """
        plot_df = prepare_plot_df(df, self.display_rename)
        param_cols = [p.name for p in self.param_specs()]
        objective_cols = [self.display_rename.get(o.name, o.name) for o in self.objective_specs]
        plot_pareto_parallel_coordinates(
            plot_df,
            save_dir / "pareto_parallel_coordinates.png",
            title=f"{self.title} — pareto front",
            labels=self.column_labels,
        )
        plot_pareto_parallel_coordinates_interactive(
            plot_df,
            save_dir / "pareto_parallel_coordinates.html",
            title=f"{self.title} — pareto front (interactive: drag along an axis to filter)",
            labels=self.column_labels,
        )
        plot_pareto_objective_scatter(
            plot_df,
            save_dir / "pareto_scatter.png",
            self.scatter,
            title=f"{self.title} — pareto front (objective space)",
            labels=self.column_labels,
        )
        plot_pareto_objective_scatter(
            plot_df,
            save_dir / "pareto_scatter_zscore.png",
            self.scatter,
            title=f"{self.title} — pareto front (z-score)",
            labels=self.column_labels,
            zscore=True,
        )
        plot_objective_vs_param_scatter(
            plot_df,
            param_cols=param_cols,
            objective_cols=objective_cols,
            out_path=save_dir / "pareto_scatter_by_param.png",
            title=f"{self.title} — objectives vs. parameters",
        )
        plot_param_pair_vs_objective_scatter(
            plot_df,
            param_cols=param_cols,
            objective_cols=objective_cols,
            out_path=save_dir / "pareto_scatter_param_pairs.png",
            title=f"{self.title} — objective vs. parameter pairs",
        )

    def main(self, argv: list[str] | None = None) -> None:
        """Run the baseline and the search, then plot — or one half, via ``--no-plot``/``--plot-only``.

        The split lets an app's ``dvc.yaml`` run "optimize" and "plot" as
        separate stages, so a plotting-only change reruns just the plots.
        """
        args = self.parse_args(argv)
        print(f"opt_{self.title} starting at")
        print_dt()
        logging.basicConfig(level=args.log_level)

        if args.plot_only:
            df = strip_column_prefixes(pd.read_csv(args.save_dir / "pareto_results.csv"))
        else:
            if args.clean and args.save_dir.exists():
                shutil.rmtree(args.save_dir)
            args.save_dir.mkdir(parents=True, exist_ok=True)

            wf, wf_manual = self.build_baseline()
            baseline = ", ".join(f"{o.name}={o.evaluate(wf_manual):.6g}" for o in self.objective_specs)
            print(f"Baseline (config design point): {baseline}")

            _res, df, _m = self.run_optimization(wf, args)
            print(f"Pareto front: {len(df)} designs")
            print(df)

            if args.no_plot:
                return

        self.make_plots(df, args.save_dir)


def plot_pareto_parallel_coordinates(
    df: pd.DataFrame,
    out_path: Path,
    title: str,
    labels: dict[str, str] | None = None,
    color_col: str = "euclidean",
) -> None:
    """Static parallel-coordinates plot across every pareto-front design.

    Min-max normalized axes, viridis_r coloring clipped to the 5th-95th
    percentile of ``color_col``. Prepends a ``design_number`` axis (0-based,
    matching ``pareto_configs/design_NNN.yml``) so a line can be traced back to
    its saved config. Operates on a copy of ``df``.
    """
    labels = labels or {}
    df = df.copy()
    df.insert(0, "design_number", range(len(df)))
    cols = list(df.columns)
    data = df[cols].to_numpy(dtype=float)
    mins = data.min(axis=0)
    maxs = data.max(axis=0)
    span = np.where(maxs > mins, maxs - mins, 1.0)
    normalized = (data - mins) / span

    color_values = df[color_col].to_numpy(dtype=float)
    cmap = plt.get_cmap("viridis_r")
    c_min, c_max = np.percentile(color_values, [5, 95])
    if c_max <= c_min:
        c_min, c_max = float(color_values.min()), float(color_values.max())
    c_span = c_max - c_min if c_max > c_min else 1.0
    clipped = np.clip(color_values, c_min, c_max)

    fig, ax = plt.subplots(figsize=(1.8 * len(cols), 6.5))
    x = np.arange(len(cols))
    for row, color_value in zip(normalized, clipped, strict=True):
        ax.plot(x, row, color=cmap((color_value - c_min) / c_span), alpha=0.5, linewidth=1.0)

    for i, (col_min, col_max, label) in enumerate(zip(mins, maxs, cols, strict=True)):
        ax.axvline(i, color="grey", linewidth=0.8, zorder=0)
        ax.text(
            i,
            1.04,
            f"{col_max:.3g}",
            ha="center",
            va="bottom",
            fontsize=8,
            transform=ax.get_xaxis_transform(),
        )
        ax.text(
            i,
            -0.04,
            f"{col_min:.3g}",
            ha="center",
            va="top",
            fontsize=8,
            transform=ax.get_xaxis_transform(),
        )
        ax.text(
            i,
            -0.15,
            labels.get(label, label),
            ha="right",
            va="top",
            fontsize=8,
            rotation=30,
            rotation_mode="anchor",
            transform=ax.get_xaxis_transform(),
        )

    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlim(-0.2, len(cols) - 0.8)
    ax.set_ylim(-0.45, 1.14)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=Normalize(vmin=c_min, vmax=c_max))
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, extend="both")
    cbar.set_label(f"{color_col} (5th-95th pctile; outliers clipped)")

    fig.suptitle(title, y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_pareto_parallel_coordinates_interactive(
    df: pd.DataFrame,
    out_path: Path,
    title: str,
    labels: dict[str, str] | None = None,
    color_col: str = "euclidean",
) -> bool:
    """Interactive HTML version of ``plot_pareto_parallel_coordinates`` (Plotly Parcoords).

    Returns:
        ``False`` (and writes nothing) if plotly isn't installed.

    """
    try:
        import plotly.graph_objects as go  # noqa: PLC0415
    except ImportError:
        print(f"plotly not installed — skipping {out_path.name} (install with `uv sync --group dev`)")
        return False

    labels = labels or {}
    df = df.copy()
    df.insert(0, "design_number", range(len(df)))
    cols = list(df.columns)
    color_values = df[color_col].to_numpy(dtype=float)
    c_min, c_max = np.percentile(color_values, [5, 95])
    if c_max <= c_min:
        c_min, c_max = float(color_values.min()), float(color_values.max())

    # "~s" (SI-prefix style: 1.3G, 823k) only for magnitudes >= 1: below 1,
    # d3 uses milli/micro prefixes, so 0.215 would render as "215m" and read
    # as meters on an "_m" column. Smaller columns get plain "~g" instead.
    dimensions: list[dict[str, Any]] = [
        {
            "label": labels.get(c, c),
            "values": df[c].to_numpy(),
            "tickformat": "~s" if np.max(np.abs(df[c].to_numpy())) >= 1 else "~g",
        }
        for c in cols
    ]
    fig = go.Figure(
        data=go.Parcoords(
            line={
                "color": color_values,
                "colorscale": "Viridis",
                "cmin": c_min,
                "cmax": c_max,
                "showscale": True,
                "colorbar": {"title": f"{color_col} (5-95 pctile)"},
            },
            dimensions=dimensions,
        ),
    )
    fig.update_layout(
        title=title,
        paper_bgcolor="#e8e8e8",
        plot_bgcolor="#e8e8e8",
        # Parcoords can't rotate axis labels, so widen the figure per
        # dimension instead to keep labels from overlapping.
        width=max(1200, 220 * len(cols)),
        height=700,
    )
    fig.write_html(out_path)
    return True


def _diagonal_label_offset(x: pd.Series, y: pd.Series) -> tuple[tuple[float, float], str]:
    """Point-label offset perpendicular to the data's dominant diagonal, so labels don't sit on the line."""
    if len(x) < 2:
        return (-5, 5), "right"
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.corrcoef(x, y)[0, 1]
    if np.isnan(r) or r >= 0:
        return (-5, 5), "right"
    return (5, 5), "left"


def plot_pareto_objective_scatter(
    df: pd.DataFrame,
    out_path: Path,
    scatter: ObjectiveScatter,
    title: str,
    labels: dict[str, str] | None = None,
    *,
    zscore: bool = False,
) -> None:
    """2D scatter of two result columns, each point labeled with its design number.

    Args:
        df: Pareto results, display column names.
        out_path: PNG to write.
        scatter: Axes and coloring.
        title: Plot title.
        labels: Colorbar label per display column.
        zscore: Plot each axis as a z-score instead of its scaled value.

    """
    labels = labels or {}
    x = df[scatter.x_col].astype(float)
    y = df[scatter.y_col].astype(float) * scatter.y_scale
    x_label, y_label = scatter.x_label, scatter.y_label
    if zscore:
        x = (x - x.mean()) / (x.std() or 1.0)
        y = (y - y.mean()) / (y.std() or 1.0)
        x_label, y_label = f"{x_label} (z-score)", f"{y_label} (z-score)"

    fig, ax = plt.subplots(figsize=(8, 6))
    if zscore:
        ax.axhline(0, color="grey", linewidth=0.8, zorder=1)
        ax.axvline(0, color="grey", linewidth=0.8, zorder=1)
    if scatter.color_col is None:
        ax.scatter(x, y, s=40, zorder=3)
    else:
        sc = ax.scatter(x, y, s=40, c=df[scatter.color_col].to_numpy(dtype=float), cmap="viridis", zorder=3)
        fig.colorbar(sc, ax=ax).set_label(labels.get(scatter.color_col, scatter.color_col))
    xytext, ha = _diagonal_label_offset(x, y)
    for i, (xi, yi) in enumerate(zip(x, y, strict=True)):
        ax.annotate(str(i), (xi, yi), textcoords="offset points", xytext=xytext, ha=ha, fontsize=8)

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.grid(visible=True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
