r"""Multi-objective optimization API for tango_next, built on pymoo.

Modeled on ``fastsim.pymoo_api``'s ``ModelObjectives``/``CalibrationProblem``/
``run_minimize`` shape (``~/git/nrel/fastsim/python/fastsim/pymoo_api.py``),
adapted to tango_next's actual seams:

- **Parameters mutate config dicts, not live objects.** ``Workflow.to_dict()``'s
  own class docstring already shows this exact pattern (``cfg =
  base_wf.to_dict(); cfg[...] = ...; Workflow(cfg).run()``) — a fresh
  ``Workflow`` is built and run from a mutated copy of the base config on
  every evaluation, rather than trying to mutate a live, already-solved
  ``Workflow`` in place.
- **Constraint violations are real pymoo constraints, not objective-space
  penalties.** fastsim's ``ModelObjectives.get_errors`` falls back to a
  fixed huge objective value (``1.02e12``) on simulation failure — that
  value has to be large enough to dominate every real objective, which
  makes it scale-dependent and easy to get wrong. Here, a failed evaluation
  instead sets a real ``out["G"]`` constraint violation (``> 0``); pymoo's
  own constraint-domination ranking (feasible always beats infeasible,
  regardless of ``F``) means the objective fallback value's magnitude is
  irrelevant, so it can just be ``0.0`` rather than a magic huge number.

``InjectionPolicy`` restriction: only ``MANUAL`` and ``MANUAL_FRACKING_CHECK``
are accepted (see ``Minimization.__init__``). Every other policy either
isn't implemented yet (``AUTO_*`` all raise ``NotImplementedError`` from
``SystemBCIteration.run_timestep``) or doesn't make sense as an *inner* loop
underneath an *outer* pymoo search (whole-horizon objectives like this one
already are the outer loop — see ``InjectionPolicy``'s own docstring on
why ``MIN_LCOE``-style problems need a different solver shape).

**Caveat on ``MANUAL_FRACKING_CHECK``**: it is accepted here architecturally
(and the CV-on-exception path is written generically, catching whatever
``SystemBCIteration`` raises), but it currently raises
``NotImplementedError`` unconditionally in ``tango_next`` today (Phase 2
work, not yet landed) — every evaluation under this policy would register
as a constraint violation, not a mix of feasible/infeasible designs. This
is intentional forward-compatibility, not a bug: once the real fracking
check lands, this module needs no changes to start using it correctly.
"""

from __future__ import annotations

import copy
import logging
import multiprocessing
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
import yaml
from pymoo.algorithms.base.genetic import GeneticAlgorithm
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.initialization import Initialization
from pymoo.core.problem import ElementwiseProblem, LoopedElementwiseEvaluation, StarmapParallelization
from pymoo.core.result import Result
from pymoo.core.sampling import Sampling
from pymoo.operators.sampling.lhs import LHS
from pymoo.termination.default import DefaultMultiObjectiveTermination as DMOT
from pymoo.util.display.column import Column
from pymoo.util.display.output import Output

from tango_next.core.policies import InjectionPolicy
from tango_next.utils import print_dt
from tango_next.workflows.workflow import Workflow

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

# A failed evaluation's objective fallback — see module docstring for why
# the magnitude doesn't matter (pymoo's constraint-domination ranking
# always ranks a feasible design ahead of an infeasible one regardless of
# F), unlike fastsim's scale-dependent 1e12-style penalty constants.
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
    reproducibility by default (matches pymoo's/fastsim's own convention of
    a fixed default rather than a random one); pass ``None`` for a
    non-reproducible (system-entropy-seeded) run instead."""


@dataclass
class ParamSpec:
    """One decision variable pymoo can tweak.

    Args:
        name: Column name in the results dataframe.
        apply: ``(config_dict, value) -> config_dict`` — mutates (and
            returns) a copy of the base config with this parameter set to
            ``value``. Mirrors ``fastsim.pymoo_api.ModelObjectives``'s
            ``param_fns`` — see ``mass_rate_param``/``injection_pressure_param``
            below for the two built-in ones.
        bounds: ``(lower, upper)`` bound pymoo searches within.

    """

    name: str
    apply: Callable[[dict[str, Any], float], dict[str, Any]]
    bounds: tuple[float, float]


@dataclass
class ObjectiveSpec:
    """One objective pymoo minimizes.

    Args:
        name: Column name in the results dataframe.
        evaluate: ``(solved_workflow) -> float`` — pymoo minimizes this
            value, so a "maximize energy" goal must be expressed as its
            negative (see ``negative_mean_power_objective`` below).

    """

    name: str
    evaluate: Callable[[Workflow], float]


# ---------------------------------------------------------------------------
# Built-in ParamSpec / ObjectiveSpec factories
# ---------------------------------------------------------------------------


@dataclass
class _MassRateApply:
    """Picklable ``ParamSpec.apply`` for ``mass_rate_param`` — see its docstring.

    A LOCAL closure (``def apply(...): ...`` nested inside a factory
    function) can't be pickled — ``pickle``/``multiprocessing`` serialize
    callables by module + qualified name and can't re-import a
    runtime-only local closure. That only breaks in the ``n_processes > 1``
    path (``multiprocessing.Pool.starmap`` requires every argument,
    including this callable, to pickle) — confirmed empirically: it raised
    ``AttributeError: Can't pickle local object 'mass_rate_param.<locals>.apply'``
    the first time ``n_processes=2`` was actually exercised. A module-level
    dataclass with ``__call__`` pickles fine (by class reference + simple
    field values), so every ``ParamSpec``/``ObjectiveSpec`` factory below
    uses this pattern instead of a closure.
    """

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        cfg["sim_config"]["mass_rate"] = float(value)
        return cfg


def mass_rate_param(bounds: tuple[float, float]) -> ParamSpec:
    """Mass flow rate (``sim_config.mass_rate``, kg/s) as a decision variable."""
    return ParamSpec(name="mass_rate_kg_s", apply=_MassRateApply(), bounds=bounds)


@dataclass
class _InjectionPressureApply:
    """Picklable ``ParamSpec.apply`` for ``injection_pressure_param`` — see ``_MassRateApply``."""

    surface_name: str = "surface"

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        cfg["components"][self.surface_name]["injection_pressure"] = float(value)
        return cfg


def injection_pressure_param(bounds: tuple[float, float], surface_name: str = "surface") -> ParamSpec:
    """Injection wellhead pressure (``components.<surface_name>.injection_pressure``, Pa)."""
    return ParamSpec(name="injection_pressure_Pa", apply=_InjectionPressureApply(surface_name), bounds=bounds)


@dataclass
class _LcoeEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` for ``lcoe_objective`` — see ``_MassRateApply``."""

    def __call__(self, wf: Workflow) -> float:
        return float(wf.to_dict()["economic"]["state"]["LCOE"])


def lcoe_objective() -> ObjectiveSpec:
    """LCOE ($/kWh), from ``NativeEconomicComponent`` — requires an ``economic:`` block."""
    return ObjectiveSpec(name="LCOE", evaluate=_LcoeEvaluate())


@dataclass
class _NegativeMeanPowerEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` for ``negative_mean_power_objective`` — see ``_MassRateApply``."""

    surface_name: str = "surface"

    def __call__(self, wf: Workflow) -> float:
        surface = wf._orchestrator.components[self.surface_name]  # noqa: SLF001
        history = getattr(surface, "history", None)
        net_power_w_history: list[float] = getattr(history, "net_power_W", [])
        mean_w = sum(net_power_w_history) / len(net_power_w_history) if net_power_w_history else 0.0
        return -mean_w


def negative_mean_power_objective(surface_name: str = "surface") -> ObjectiveSpec:
    """``-`` mean net electric power over the run (W) — minimizing this maximizes power.

    Mean, not total energy: a human reading the results has direct
    intuition for "1.3 MW average" but none for "1.1e15 J total" — and
    since every timestep has the SAME duration in tango_next today
    (``dt_years`` is a single scalar for the whole run), the mean of
    ``history.net_power_W`` and the time-integrated total energy differ
    only by that one shared, constant scale factor (``dt_years *
    YEAR_TO_SECOND``) — the mean carries exactly the same optimization
    signal, it's just a friendlier unit to look at.
    """
    return ObjectiveSpec(name="negative_mean_power_W", evaluate=_NegativeMeanPowerEvaluate(surface_name))


# ---------------------------------------------------------------------------
# Live progress output (verbose=True)
# ---------------------------------------------------------------------------


class ParetoProgressOutput(Output):
    """Per-generation progress table for ``Minimization.run()`` (``verbose=True``).

    Loosely modeled on ``fastsim.pymoo_api``'s ``CustomOutput`` (nested
    inside ``run_minimize``) — fixes two real issues found there, not
    copied as-is:

    1. **Scale mixing.** fastsim's ``euclid_min`` sums RAW, unnormalized
       objective values before taking the norm — only meaningful if every
       objective is on a comparable scale. Not true here (LCOE ~0.1-1,
       ``negative_mean_power_W`` ~1e6-1e7): the larger-magnitude objective would
       completely dominate, making the metric say almost nothing about the
       smaller one. Z-score normalizing each objective column (subtract
       its mean, divide by its std, both computed fresh from the CURRENT
       front every generation) puts them on equal footing before summing.
    2. **Inconsistent solution set.** fastsim's ``n_nds`` column reports on
       ``algorithm.opt`` (the non-dominated front) while its adjacent
       ``euclid_min`` column computes over ``algorithm.pop`` (the WHOLE
       population, including dominated individuals) — two columns
       describing different sets. Both columns here use ``algorithm.opt``.

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


class Minimization:
    """Multi-objective optimization over a tango_next ``Workflow``, via pymoo.

    Usage::

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
        params: Decision variables (see ``ParamSpec``, and the
            ``*_param`` factories above for the two built-in ones).
        objectives: Objectives to minimize (see ``ObjectiveSpec``, and the
            ``*_objective`` factories above).
        policy: Injection control policy — restricted to ``MANUAL``/
            ``MANUAL_FRACKING_CHECK`` (see module docstring for why).
            Overwrites ``sim_config.injection_mode`` on every evaluation's
            config, so the base config's own value doesn't matter.
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

    Raises:
        ValueError: If ``policy`` is not one of the two allowed policies.

    """

    def __init__(
        self,
        base_workflow: Workflow,
        params: list[ParamSpec],
        objectives: list[ObjectiveSpec],
        policy: InjectionPolicy = InjectionPolicy.MANUAL,
        pymoo_config: PymooConfig | None = None,
        algorithm: GeneticAlgorithm | None = None,
        verbose: bool = False,
        save_results: bool = True,
        save_pareto_configs: bool = True,
        save_dir: Path | str = DEFAULT_SAVE_DIR,
        seed_from: Path | str | None = None,
        pad_sampling: Sampling | None = None,
    ) -> None:
        """See class docstring for argument details."""
        if policy not in ALLOWED_POLICIES:
            raise ValueError(
                f"Minimization only supports {[p.value for p in ALLOWED_POLICIES]!r}, got {policy.value!r} — "
                "AUTO_* policies raise NotImplementedError in SystemBCIteration today (Phase 2 work), and "
                "whole-horizon objectives like this one ARE the outer loop, not something to nest under one.",
            )
        self.base_cfg: dict[str, Any] = base_workflow.to_dict()
        self.base_cfg["sim_config"]["injection_mode"] = policy.value
        self.params = list(params)
        self.objectives = list(objectives)
        self.policy = policy
        self.pymoo_config = pymoo_config or PymooConfig()
        self.algorithm = algorithm or NSGA2(pop_size=self.pymoo_config.pop_size)
        self.verbose = verbose
        self.save_results = save_results
        self.save_pareto_configs = save_pareto_configs
        self.save_dir = Path(save_dir)
        self.seed_from = Path(seed_from) if seed_from is not None else None
        self.pad_sampling: Sampling = pad_sampling if pad_sampling is not None else LHS()
        self.n_failures = 0
        """Count of evaluations that raised (CV, not crash) — inspect after ``run()``."""

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

    def _evaluate_one(self, x: list[float]) -> tuple[list[float], list[float]]:
        """Build, run, and score one design — CV on any exception (see module docstring)."""
        cfg = self._build_config(x)
        try:
            wf = Workflow(cfg)
            wf.run()
        except Exception as exc:  # noqa: BLE001 — any simulation failure is a real CV, not a crash
            self.n_failures += 1
            if self.verbose:
                logger.info("Evaluation failed (treated as constraint violation): %s", exc)
            return [_CV_OBJECTIVE_FALLBACK] * len(self.objectives), [_INFEASIBLE_G]
        return [spec.evaluate(wf) for spec in self.objectives], [_FEASIBLE_G]

    def _elementwise_runner(self) -> LoopedElementwiseEvaluation | StarmapParallelization:
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
        pareto front) — NOT ``fastsim.pymoo_api.run_minimize``'s
        ``res_df["euclidean"]`` construction, which sums RAW objective
        values and is therefore dominated by whichever objective happens
        to have the largest units (e.g. here, ``negative_mean_power_W`` ~1e6-1e7 vs.
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

    Private: users construct ``Minimization``, not this class directly —
    mirrors ``fastsim.pymoo_api.CalibrationProblem`` wrapping ``ModelObjectives``.
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
