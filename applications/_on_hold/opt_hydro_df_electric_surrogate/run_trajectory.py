# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Stage 1: run the REAL simulation via a short real NSGA2 search, retaining
EVERY evaluated individual (not just the final front) as surrogate training
data.

Replaces the old ``generate_lhs.py``/``sweep_lhs.py`` (space-filling Latin
Hypercube sample, uniform over the whole design space) with training data
drawn from the real optimizer's own search trajectory instead: generation 0
(NSGA2's random init) gives LHS-like broad coverage for free, and later
generations naturally concentrate near the real Pareto front — the region
that actually matters for the surrogate to get right — without a separate,
manual refinement round. See ``REDESIGN_TODO.md`` for the full design
discussion.

Duplicate elimination happens at TWO layers: ``ParamToleranceDuplicateElimination``
(pre-eval, wired into the NSGA2 ``algorithm`` below) catches near-duplicates
within the current generation's offspring/population before they're ever
real-simulated; ``surrogate_api.dedup_training_rows`` (post-hoc, run once
after the whole trajectory completes) additionally catches near-duplicates
ACROSS generations that the first layer can't see (pymoo's own mating only
ever compares against what's currently live, not the full history).

Deliberately few generations (``trajectory_n_gen``, small) at a large
population (``trajectory_pop_size``) — the goal here is BREADTH of real-sim
coverage near the front, not convergence depth (that's what the
surrogate-driven ``optimize_surrogate.py`` run, cheap because it's not
real-sim'd, is for). ``ftol``/``xtol`` are fixed at 0.0 so
``trajectory_n_gen`` is a hard generation count, not a convergence-dependent
upper bound — pymoo's ``DefaultMultiObjectiveTermination`` would otherwise
stop early if it detects convergence before ``trajectory_n_gen`` generations
complete.

Usage: uv run python run_trajectory.py
"""

from __future__ import annotations

import os

# Same thread-oversubscription fix as sweep_lhs.py had -- Minimization.run()
# still evaluates the real simulation (Workflow -> TESPy/CoolProp) via a
# multiprocessing.Pool-per-worker-process when n_processes > 1, so each
# worker independently letting numpy/OpenBLAS spin up its own thread pool
# oversubscribes just as badly.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import argparse
import time
from pathlib import Path

import pandas as pd
from common import DEFAULT_OUTPUT_DIR, PARAMS_FILE, base_config, objective_specs, param_specs
from pymoo.algorithms.moo.nsga2 import NSGA2

from tango_core.pymoo_api import Minimization, ParamToleranceDuplicateElimination, PymooConfig, load_params
from tango_core.surrogate_api import dedup_training_rows
from tango_core.utils import print_dt


def build_parser() -> argparse.ArgumentParser:
    """CLI for the trajectory-generating real NSGA2 run."""
    params = load_params(PARAMS_FILE)
    parser = argparse.ArgumentParser(
        description="Run a short real NSGA2 search, retaining every evaluated individual as training data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--pop-size", type=int, default=params.get("trajectory_pop_size", 1000))
    parser.add_argument("--n-gen", type=int, default=params.get("trajectory_n_gen", 5))
    parser.add_argument("--seed", type=int, default=params.get("trajectory_seed", 1))
    parser.add_argument(
        "--dedup-tol-frac",
        type=float,
        default=params.get("trajectory_dedup_tol_frac", 0.001),
        help="Two designs are treated as duplicates (never real-sim'd) if EVERY param is within "
        "this fraction of the other's -- see ParamToleranceDuplicateElimination.",
    )
    parser.add_argument("--n-workers", type=int, default=params.get("n_train_workers", 4))
    parser.add_argument("--save-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress pymoo's per-generation progress table.",
    )
    return parser


def main(args: argparse.Namespace) -> None:
    """Run the real-NSGA2 trajectory and write ``outputs/lhs_training_data.csv``."""
    print("run_trajectory.py starting at")
    print_dt()
    start = time.monotonic()

    params = param_specs()
    objectives = objective_specs()

    algorithm = NSGA2(
        pop_size=args.pop_size,
        eliminate_duplicates=ParamToleranceDuplicateElimination(params, tol_frac=args.dedup_tol_frac),
    )
    pymoo_config = PymooConfig(
        n_max_gen=args.n_gen,
        pop_size=args.pop_size,
        ftol=0.0,
        xtol=0.0,
        n_processes=args.n_workers,
        seed=args.seed,
    )
    print(
        f"Trajectory NSGA2: pop_size={args.pop_size}, n_gen={args.n_gen}, "
        f"dedup_tol_frac={args.dedup_tol_frac} -- every evaluated individual retained as training data",
    )

    args.save_dir.mkdir(parents=True, exist_ok=True)
    training_path = args.save_dir / "lhs_training_data.csv"
    training_path.unlink(missing_ok=True)  # this run's own trajectory, not appended to a stale prior one

    m = Minimization(
        base_cfg=base_config(),
        params=params,
        objectives=objectives,
        pymoo_config=pymoo_config,
        algorithm=algorithm,
        verbose=not args.quiet,
        save_results=False,  # this stage cares about the FULL trajectory, not the running front
        capture_trajectory_path=training_path,
    )
    res, pareto_df = m.run()

    raw_df = pd.read_csv(training_path)
    param_names = [p.name for p in params]
    objective_names = [o.name for o in objectives]
    deduped_df = dedup_training_rows(raw_df, param_names, objective_names, tol_frac=args.dedup_tol_frac)
    n_dropped = len(raw_df) - len(deduped_df)
    deduped_df.to_csv(training_path, index=False)
    elapsed = time.monotonic() - start

    print(
        f"Wrote {len(deduped_df)} trajectory rows to {training_path} "
        f"(dropped {n_dropped} near-duplicate of {len(raw_df)} raw evaluations, tol_frac={args.dedup_tol_frac})",
    )
    print(
        f"Real trajectory's own final pareto front: {len(pareto_df)} designs ({m.n_failures} evaluations failed)",
    )
    pareto_df.to_csv(args.save_dir / "trajectory_pareto_results.csv", index=False)
    print(f"run_trajectory.py finished in {elapsed:.1f}s")


if __name__ == "__main__":
    main(build_parser().parse_args())
