"""Stage 2: run the REAL simulation on every LHS sample, in parallel.

**Thread oversubscription fix:** each of the ``n_workers`` worker PROCESSES
(spawned by ``multiprocessing.Pool`` inside ``surrogate_api.run_lhs_sweep``)
independently lets numpy/OpenBLAS/TESPy's own numerics spin up a thread pool
sized to every available core, unaware they're one of many sibling workers —
the exact same failure mode fixed in ``run_hydro_df_electric_sweep/sweep.py``
(2026-08-17): with ``n_workers`` in the dozens, that blew through the
cluster's ``RLIMIT_NPROC`` on a real Euler run. Cap every thread-pool-owning
library to 1 thread per process *before* any of them get imported (spawned
workers re-run this module's top-level code from scratch under the 'spawn'
start method) — the outer ``Pool`` is already the parallelism.

Usage: uv run python sweep_lhs.py
"""

from __future__ import annotations

import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import argparse
import time
from pathlib import Path

import pandas as pd
from common import DEFAULT_OUTPUT_DIR, PARAMS_FILE, build_baseline, objective_specs, param_specs

from tango_next.pymoo_api import load_params
from tango_next.surrogate_api import run_lhs_sweep
from tango_next.utils import print_dt


def build_parser() -> argparse.ArgumentParser:
    """CLI for the parallel real-sim sweep over the LHS design matrix."""
    params = load_params(PARAMS_FILE)
    parser = argparse.ArgumentParser(
        description="Run the real simulation on every LHS sample, in parallel.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--n-workers", type=int, default=params.get("n_train_workers", 4))
    parser.add_argument("--save-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--quiet", "-q", action="store_true")
    return parser


def main(args: argparse.Namespace) -> None:
    """Evaluate every LHS row with the real simulation, writing ``lhs_training_data.csv``."""
    print("sweep_lhs.py starting at")
    print_dt()
    start = time.monotonic()

    design_matrix = pd.read_csv(args.save_dir / "lhs_design_matrix.csv")
    params = param_specs()
    objectives = objective_specs()
    x = design_matrix[[p.name for p in params]].to_numpy(dtype=float)

    base_wf, _wf_manual = build_baseline()
    training_df = run_lhs_sweep(
        base_wf,
        params,
        objectives,
        x,
        n_workers=args.n_workers,
        results_dir=args.save_dir / "lhs_sweep_results",
        quiet=args.quiet,
    )

    out_path = args.save_dir / "lhs_training_data.csv"
    training_df.to_csv(out_path, index=False)
    n_feasible = int(training_df["success"].sum())
    elapsed = time.monotonic() - start
    print(f"Wrote {len(training_df)} rows ({n_feasible} feasible) to {out_path}")
    print(f"sweep_lhs.py finished in {elapsed:.1f}s")


if __name__ == "__main__":
    main(build_parser().parse_args())
