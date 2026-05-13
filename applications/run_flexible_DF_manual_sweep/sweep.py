"""Simulation sweep stage for the DF manual sweep pipeline."""

import argparse
import json
import multiprocessing
import tempfile
import traceback
from pathlib import Path

import polars as pl
from common import (
    DEFAULT_LOG_LEVEL,
    DEFAULT_N_WORKERS,
    DEFAULT_SWEEP_DIR,
    INPUT_FILE,
    PARAMETERS,
    get_nested_value,
    load_params,
    set_nested_value,
)

from tango.runner import Runner
from tango.utils import print_datetime


def run_single_simulation(args: tuple) -> None:
    """Run a single simulation for the given row index.

    Args is a tuple of (row_idx, design_matrix_file, results_dir, log_level, verbose).
    """
    row_idx, design_matrix_file, results_dir, log_level, verbose = args
    result_file = results_dir / f"{row_idx:06d}.json"

    if result_file.exists():
        return

    df = pl.read_parquet(design_matrix_file)
    row = df.filter(pl.col("row_idx") == row_idx).to_dicts()[0]

    runner = Runner(input_file=INPUT_FILE, no_save=True, log_level=log_level)

    result = {
        "row_idx": row_idx,
        "specs_hash": None,
        "LCOE": None,
        "error": None,
    }

    try:
        for param in PARAMETERS:
            original_value = get_nested_value(runner.tango.specs, param)
            scale_factor = row[param]
            new_value = original_value * scale_factor
            set_nested_value(runner.tango.specs, param, new_value)

        # Sync injection well length
        prod_len = get_nested_value(runner.tango.specs, "production_well.well_length")
        pump_len = get_nested_value(runner.tango.specs, "production_well_pump.well_length")
        set_nested_value(runner.tango.specs, "injection_well.well_length", prod_len + pump_len)

        # Sync _seq params
        seq_mappings = [
            ("injection_well.well_length_seq", "injection_well.well_length"),
            ("injection_well.well_diameter_seq", "injection_well.diameter"),
            ("production_well.well_length_seq", "production_well.well_length"),
            ("production_well.well_diameter_seq", "production_well.diameter"),
        ]
        for seq_path, scalar_path in seq_mappings:
            scalar_val = get_nested_value(runner.tango.specs, scalar_path)
            set_nested_value(runner.tango.specs, seq_path, [scalar_val])

        runner.update_parameters()

        # Get specs hash (stored for future ArangoDB integration)
        result["specs_hash"] = runner.tango.get_hash_from_specs()

        runner.start()
        result["LCOE"] = runner.tango.workflow.economic._results["LCOE"]

    except Exception as e:
        result["error"] = {
            "type": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc(),
        }

    # Save result atomically so a mid-write crash doesn't leave a corrupt file
    # that the resume logic would mistake for a completed run. dir=results_dir
    # keeps the tmp file on the same filesystem, which is required for rename
    # to be atomic on POSIX.
    results_dir.mkdir(exist_ok=True, parents=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=results_dir, delete=False, suffix=".tmp") as f:
        json.dump(result, f, indent=2)
        tmp_path = Path(f.name)
    tmp_path.rename(result_file)


def run_sweep(
    design_matrix_file: Path,
    results_dir: Path,
    n_workers: int,
    log_level: str = DEFAULT_LOG_LEVEL,
    quiet: bool = False,
    progress_interval: int | None = None,
) -> None:
    """Run the parameter sweep in parallel."""
    df = pl.read_parquet(design_matrix_file)
    n_samples = len(df)

    results_dir.mkdir(exist_ok=True, parents=True)
    completed = {int(f.stem) for f in results_dir.glob("*.json")}
    pending = [i for i in range(n_samples) if i not in completed]

    if not quiet:
        print(
            f"Sweep status: {len(completed)}/{n_samples} completed, {len(pending)} pending",
            flush=True,
        )

    if not pending:
        if not quiet:
            print("All simulations complete!")
        return

    worker_args = [(idx, design_matrix_file, results_dir, log_level, quiet) for idx in pending]
    interval = progress_interval if progress_interval is not None else n_workers

    # Use 'spawn' context for HPC compatibility (fork can cause issues on SLURM)
    if not quiet:
        print(f"Starting pool with {n_workers} workers (spawn context)...", flush=True)
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(n_workers) as pool:
        completed_count = 0
        total = len(pending)
        for _ in pool.imap_unordered(run_single_simulation, worker_args):
            completed_count += 1
            if not quiet and completed_count % interval == 0:
                print_datetime()
                print(f"Progress: {completed_count}/{total} completed")

        if not quiet and completed_count % interval != 0:
            print_datetime()
            print(f"Progress: {completed_count}/{total} completed")

    if not quiet:
        print("Sweep complete!")


def main(
    n_workers: int = DEFAULT_N_WORKERS,
    log_level: str = DEFAULT_LOG_LEVEL,
    quiet: bool = False,
    progress_interval: int | None = None,
    sweep_dir: Path | None = None,
) -> None:
    sweep_dir = sweep_dir if sweep_dir is not None else DEFAULT_SWEEP_DIR
    design_matrix_file = sweep_dir / "design_matrix.parquet"
    results_dir = sweep_dir / "results"

    if not quiet:
        print(f"Workers: {n_workers}")
    run_sweep(design_matrix_file, results_dir, n_workers, log_level, quiet, progress_interval)


def parse_args() -> argparse.Namespace:
    params = load_params()
    parser = argparse.ArgumentParser(
        description="Run simulation sweep for TANGO parameter sweep",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--n-workers",
        type=int,
        default=params.get("n_workers", DEFAULT_N_WORKERS),
        help="Number of parallel workers",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=params.get("log_level", DEFAULT_LOG_LEVEL),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "NONE"],
        help="Log level for TANGO simulations",
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress progress output")
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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.quiet and args.progress_interval is not None:
        raise ValueError("--quiet and --progress-interval are mutually exclusive")
    main(
        n_workers=args.n_workers,
        log_level=args.log_level,
        quiet=args.quiet,
        progress_interval=args.progress_interval,
        sweep_dir=args.sweep_dir,
    )
