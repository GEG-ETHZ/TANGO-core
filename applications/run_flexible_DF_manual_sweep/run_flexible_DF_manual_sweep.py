"""End-to-end orchestrator for the DF manual sweep pipeline.

Runs generate → sweep → summarize in sequence. For individual stages,
call generate.py, sweep.py, or summarize.py directly (or use DVC).

Usage:
    python run_flexible_DF_manual_sweep.py --n-samples 100 --n-workers 8
    python run_flexible_DF_manual_sweep.py --regenerate --n-samples 1000

Parameter bounds are defined per-parameter in PARAMETER_BOUNDS in common.py.
"""

import argparse
import tempfile
from pathlib import Path

from common import (
    DEFAULT_LOG_LEVEL,
    DEFAULT_N_SAMPLES,
    DEFAULT_N_WORKERS,
    DEFAULT_SEED,
    DEFAULT_SWEEP_DIR,
    clean_sweep_dir,
    load_params,
)
from generate import main as generate_main
from summarize import main as summarize_main
from sweep import main as sweep_main

from tango.utils import print_dt

SMOKE_N_SAMPLES = 2


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the end-to-end sweep entry point."""
    params = load_params()
    parser = argparse.ArgumentParser(
        description="End-to-end LHS Parameter Sweep for TANGO simulations",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--n-samples",
        type=int,
        default=params.get("n_samples", DEFAULT_N_SAMPLES),
        help="Number of samples to generate (design matrix rows)",
    )
    parser.add_argument(
        "--n-workers",
        type=int,
        default=params.get("n_workers", DEFAULT_N_WORKERS),
        help="Number of parallel workers",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=params.get("seed", DEFAULT_SEED),
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Regenerate design matrix even if it exists (clears old results)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=params.get("log_level", DEFAULT_LOG_LEVEL),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "NONE"],
        help="Log level for TANGO simulations",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress output",
    )
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=None,
        help="Print progress every N completions (default: n_workers)",
    )
    parser.add_argument(
        "--sweep-dir",
        type=Path,
        default=None,
        help=f"Directory for sweep outputs (default: {DEFAULT_SWEEP_DIR})",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=(
            f"Run a tiny {SMOKE_N_SAMPLES}-sample sweep into a fresh OS tempdir "
            "instead of the full LHS sample count — for a fast 'does the "
            "pipeline still run end to end' check, not real results. Overrides "
            "--n-samples/--sweep-dir. Never touches outputs/ — a new tempdir "
            "is created every run."
        ),
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove all generated artifacts from --sweep-dir (or the default outputs/ dir) and exit",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print_dt()
    if args.quiet and args.progress_interval is not None:
        raise ValueError("--quiet and --progress-interval are mutually exclusive")
    if args.clean and args.smoke:
        raise ValueError("--clean and --smoke are mutually exclusive")

    if args.clean:
        clean_sweep_dir(args.sweep_dir or DEFAULT_SWEEP_DIR, quiet=args.quiet)
        raise SystemExit(0)

    if args.smoke:
        sweep_dir = args.sweep_dir or Path(tempfile.mkdtemp(prefix="tango_df_manual_smoke_"))
        if not args.quiet:
            print(f"Smoke run — writing to {sweep_dir}")
        n_samples = SMOKE_N_SAMPLES
    else:
        sweep_dir = args.sweep_dir if args.sweep_dir is not None else DEFAULT_SWEEP_DIR
        n_samples = args.n_samples

    generate_main(
        n_samples=n_samples,
        seed=args.seed,
        regenerate=args.regenerate,
        quiet=args.quiet,
        sweep_dir=sweep_dir,
    )
    sweep_main(
        n_workers=args.n_workers,
        log_level=args.log_level,
        quiet=args.quiet,
        progress_interval=args.progress_interval,
        sweep_dir=sweep_dir,
    )
    summarize_main(quiet=args.quiet, sweep_dir=sweep_dir)
