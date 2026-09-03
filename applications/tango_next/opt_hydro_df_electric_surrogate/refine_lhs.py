"""One-off manual refinement round: a second, smaller LHS batch concentrated
around the current corrected (real-feasible, real-valued) Pareto front,
real-simulated and appended to ``outputs/lhs_training_data.csv``.

This is deliberately NOT wired into ``dvc.yaml``'s automatic DAG. Doing so
would create a cycle: this script reads ``outputs/corrected_pareto_results.csv``,
which is ``validate_surrogate``'s output, but its own output
(``outputs/lhs_training_data.csv``) is ``train_surrogate``'s *input* --
several stages upstream of ``validate_surrogate``. It's meant to be run BY
HAND, once, after inspecting a completed pipeline run's corrected Pareto
front -- see the 5-step accuracy plan (2026-09-01) this implements step 4
of: "one manual refinement round, not full active learning."

Usage (after a normal ``dvc repro`` has produced a ``corrected_pareto_results.csv``):
    uv run python refine_lhs.py
    uv run dvc commit applications/tango_next/opt_hydro_df_electric_surrogate/dvc.yaml:lhs_sweep
    uv run dvc repro

The ``dvc commit`` step is required: this script appends directly to
``lhs_training_data.csv``, which is ``lhs_sweep``'s DVC-tracked output --
without telling DVC to trust the new content, the next ``dvc repro`` would
see the output's hash no longer matches ``dvc.lock`` and silently
regenerate it from ``lhs_design_matrix.csv`` alone, discarding the
refinement rows this script just added.
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

import numpy as np
import pandas as pd
from common import DEFAULT_OUTPUT_DIR, PARAMS_FILE, build_baseline, objective_specs, param_specs
from scipy.stats import qmc

from tango_next.pymoo_api import load_params
from tango_next.surrogate_api import run_lhs_sweep
from tango_next.utils import print_dt


def build_parser() -> argparse.ArgumentParser:
    """CLI for the refinement batch size/seed/padding and worker count."""
    params = load_params(PARAMS_FILE)
    parser = argparse.ArgumentParser(
        description="Draw + real-sim a second LHS batch concentrated around the corrected Pareto front.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--n-samples", type=int, default=params.get("n_refine_samples", 1000))
    parser.add_argument("--seed", type=int, default=params.get("refine_seed", 2))
    parser.add_argument(
        "--pad-frac",
        type=float,
        default=params.get("refine_bbox_pad_frac", 0.15),
        help="Pad the Pareto-front bounding box by this fraction of its own per-param range.",
    )
    parser.add_argument(
        "--min-pad-frac",
        type=float,
        default=params.get("refine_bbox_min_pad_frac", 0.05),
        help="Floor the pad at this fraction of the GLOBAL per-param range, "
        "so a Pareto front that's tightly clustered (or a single point) on some "
        "param still gets a usable box on that axis.",
    )
    parser.add_argument("--n-workers", type=int, default=params.get("n_train_workers", 4))
    parser.add_argument("--save-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--quiet", "-q", action="store_true")
    return parser


def _bounding_box(
    corrected_df: pd.DataFrame,
    params: list,
    pad_frac: float,
    min_pad_frac: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-param ``(lo, hi)`` box around ``corrected_df``, padded and clipped to global bounds.

    Padding is ``max(pad_frac * cluster_range, min_pad_frac * global_range)``
    on each side -- the ``min_pad_frac`` floor matters because a genuinely
    tight Pareto front (e.g. every design landing within a narrow band of
    ``mass_rate_kg_per_s``) would otherwise get an equally tight, near-zero-width
    refinement box on that axis, missing nearby designs the surrogate might
    still be getting wrong.
    """
    lo = np.array([p.bounds[0] for p in params])
    hi = np.array([p.bounds[1] for p in params])
    global_range = hi - lo

    cluster = corrected_df[[p.name for p in params]].to_numpy(dtype=float)
    cluster_lo = cluster.min(axis=0)
    cluster_hi = cluster.max(axis=0)
    cluster_range = cluster_hi - cluster_lo

    pad = np.maximum(pad_frac * cluster_range, min_pad_frac * global_range)
    box_lo = np.clip(cluster_lo - pad, lo, hi)
    box_hi = np.clip(cluster_hi + pad, lo, hi)
    return box_lo, box_hi


def main(args: argparse.Namespace) -> None:
    """Draw a Pareto-concentrated LHS batch, real-sim it, and append to ``lhs_training_data.csv``."""
    print("refine_lhs.py starting at")
    print_dt()
    start = time.monotonic()

    params = param_specs()
    objectives = objective_specs()
    param_names = [p.name for p in params]

    corrected_path = args.save_dir / "corrected_pareto_results.csv"
    corrected_df = pd.read_csv(corrected_path)
    if len(corrected_df) == 0:
        msg = f"{corrected_path} has zero rows -- nothing to concentrate the refinement batch around"
        raise ValueError(msg)

    box_lo, box_hi = _bounding_box(corrected_df, params, args.pad_frac, args.min_pad_frac)
    if not args.quiet:
        for name, lo, hi in zip(param_names, box_lo, box_hi, strict=True):
            print(f"refine_lhs: {name} refinement box = [{lo:.4g}, {hi:.4g}]")

    sampler = qmc.LatinHypercube(d=len(params), seed=args.seed)
    unit = sampler.random(n=args.n_samples)
    x = box_lo + unit * (box_hi - box_lo)

    training_path = args.save_dir / "lhs_training_data.csv"
    existing_df = pd.read_csv(training_path)
    row_offset = int(existing_df["row_idx"].max()) + 1

    base_wf, _wf_manual = build_baseline()
    refinement_df = run_lhs_sweep(
        base_wf,
        params,
        objectives,
        x,
        n_workers=args.n_workers,
        results_dir=args.save_dir / "refinement_sweep_results",
        quiet=args.quiet,
    )
    # run_lhs_sweep row_idx's every worker_args tuple by POSITION in `x`
    # (0..n_samples-1) -- shift into the shared id space so the appended
    # rows don't collide with the original LHS batch's row_idx range, and
    # the combined file stays meaningfully sorted.
    refinement_df["row_idx"] += row_offset

    combined_df = pd.concat([existing_df, refinement_df], ignore_index=True).sort_values("row_idx")
    combined_df.to_csv(training_path, index=False)

    n_feasible = int(refinement_df["success"].sum())
    elapsed = time.monotonic() - start
    print(
        f"refine_lhs: added {len(refinement_df)} rows ({n_feasible} feasible) to {training_path} "
        f"(now {len(combined_df)} rows total)",
    )
    print(f"refine_lhs.py finished in {elapsed:.1f}s")


if __name__ == "__main__":
    main(build_parser().parse_args())
