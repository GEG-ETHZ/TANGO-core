"""Stage 5: re-run the REAL simulation on every surrogate pareto design and compare.

Raises (non-zero exit) if any objective is off by more than ``--tolerance``
(default 0.1%) for any design — ``surrogate_validation.csv`` (the full
predicted-vs-actual comparison) and ``corrected_pareto_results.csv`` (the
genuinely trustworthy result: real-feasible designs only, REAL simulated
objective values, non-dominated status re-derived from those real values — see
``surrogate_api.corrected_pareto_front``'s docstring) are BOTH written
first regardless, so a tolerance failure still leaves both on disk.

Usage: uv run python validate_surrogate.py
"""

from __future__ import annotations

import os

# Same thread-oversubscription fix as sweep_lhs.py -- this stage's
# validate_surrogate_pareto() re-runs the real simulation via the SAME
# multiprocessing.Pool-per-worker-process pattern (surrogate_api.run_lhs_sweep),
# so it needs the identical cap: without it, each worker process independently
# lets numpy/OpenBLAS spin up its own thread pool sized to every available
# core, oversubscribing badly with n_workers workers running concurrently
# (confirmed the hard way locally: a handful of designs took 10+ minutes of
# wall-clock with 4 workers each pegged near 400% CPU on an 8-core machine).
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
from common import DEFAULT_OUTPUT_DIR, PARAMS_FILE, build_baseline, make_plots, objective_specs, param_specs
from common import DISPLAY_RENAME as _DISPLAY_RENAME

from tango.pymoo_api import load_params
from tango.surrogate_api import (
    SurrogateValidationError,
    corrected_pareto_front,
    validate_surrogate_pareto,
)
from tango.utils import print_dt


def build_parser() -> argparse.ArgumentParser:
    """CLI for the validation tolerance/worker count."""
    params = load_params(PARAMS_FILE)
    parser = argparse.ArgumentParser(
        description="Re-run the real simulation on every surrogate pareto design and compare.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--tolerance", type=float, default=params.get("validation_tolerance", 0.001))
    parser.add_argument("--n-workers", type=int, default=params.get("n_validate_workers", 4))
    parser.add_argument("--save-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-plot", action="store_true")
    return parser


def _write_corrected_front(
    comparison: pd.DataFrame,
    param_names: list[str],
    objective_names: list[str],
    save_dir: Path,
    make_plot: bool,
) -> None:
    """Filter to real-feasible designs, re-derive non-dominated status, write + (optionally) plot.

    ``corrected_pareto_results.csv`` lives directly under ``save_dir`` (like
    ``surrogate_pareto_results.csv``), but its PLOTS go in a ``corrected/``
    subdirectory -- ``make_plots`` hardcodes filenames like
    ``pareto_scatter.png`` directly under whatever ``save_dir`` it's given,
    which would silently overwrite ``optimize_surrogate``'s own plots of
    the same names (and confuse DVC about which stage actually owns them)
    if reused unchanged here.
    """
    corrected = corrected_pareto_front(comparison, param_names, objective_names)
    corrected.to_csv(save_dir / "corrected_pareto_results.csv", index=False)
    n_candidates = int(comparison["real_success"].sum())
    print(
        f"Wrote {save_dir / 'corrected_pareto_results.csv'}: {len(corrected)} genuinely pareto-optimal "
        f"designs (from {n_candidates}/{len(comparison)} real-feasible candidates)",
    )
    if make_plot and len(corrected) > 0:
        plot_dir = save_dir / "corrected"
        plot_dir.mkdir(parents=True, exist_ok=True)
        objective_cols = [_DISPLAY_RENAME.get(name, name) for name in objective_names]
        make_plots(corrected, plot_dir, param_names, objective_cols)


def main(args: argparse.Namespace) -> None:
    """Validate the surrogate pareto front against the real simulation."""
    print("validate_surrogate.py starting at")
    print_dt()
    start = time.monotonic()

    params = param_specs()
    objectives = objective_specs()
    param_names = [p.name for p in params]
    objective_names = [o.name for o in objectives]
    surrogate_df = pd.read_csv(args.save_dir / "surrogate_pareto_results.csv")
    base_wf, _wf_manual = build_baseline()

    out_path = args.save_dir / "surrogate_validation.csv"
    try:
        comparison = validate_surrogate_pareto(
            base_wf,
            params,
            objectives,
            surrogate_df,
            n_workers=args.n_workers,
            results_dir=args.save_dir / "validate_results",
            tolerance=args.tolerance,
        )
    except SurrogateValidationError as exc:
        comparison = exc.comparison  # type: ignore[attr-defined]
        comparison.to_csv(out_path, index=False)
        _write_corrected_front(comparison, param_names, objective_names, args.save_dir, not args.no_plot)
        elapsed = time.monotonic() - start
        print(f"Wrote {out_path} (with violations)")
        print(f"validate_surrogate.py finished in {elapsed:.1f}s")
        print(str(exc), file=sys.stderr)
        raise

    comparison.to_csv(out_path, index=False)
    _write_corrected_front(comparison, param_names, objective_names, args.save_dir, not args.no_plot)
    elapsed = time.monotonic() - start
    print(f"Wrote {out_path} — every design within {args.tolerance:.4%} tolerance")
    print(f"validate_surrogate.py finished in {elapsed:.1f}s")


if __name__ == "__main__":
    main(build_parser().parse_args())
