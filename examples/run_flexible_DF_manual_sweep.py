"""LHS Parameter Sweep for flexible_DF_manual.yml

Latin Hypercube Sampling sweep with parallel execution and checkpoint/resume.

Usage:
    python run_flexible_DF_manual_sweep.py --n-samples 100 --n-workers 8
    python run_flexible_DF_manual_sweep.py --scale-min 0.5 --scale-max 2.0
"""

import argparse
import json
import multiprocessing
import traceback
from pathlib import Path

import polars as pl
from scipy.stats import qmc

from tango.runner import Runner
from tango.utils import print_datetime

# Parameter definitions
PARAMETERS = [
    # props
    "props.brine_density",
    "props.rock_density",
    "props.rock_cp",
    "props.rock_k",
    "props.thermal_gradient",
    # surface
    "surface.surface_temperature",
    "surface.surface_pressure",
    "surface.pipe_diameter",
    "surface.approach_temperature",
    "surface.target_extraction_pressure",
    # reservoir
    "reservoir.reservoir_depth",
    "reservoir.thickness",
    "reservoir.permeability",
    "reservoir.porosity",
    "reservoir.hydro_static_pressure",
    "reservoir.over_pressure_percentage",
    # injection_well
    "injection_well.well_length",
    "injection_well.diameter",
    # production_well
    "production_well.well_length",
    "production_well.diameter",
    # production_well_pump
    "production_well_pump.well_length",
    "production_well_pump.diameter",
    # schedule
    "schedule.mass_flow_rate",
    "schedule.well_spacing",
    "schedule.num_pp",
    "schedule.mass_rate.value",
    # economic
    "economic.discount_rate",
    # Double-Flash power plant
    "valve1.p_out",
    "turbine1.efficiency",
    "turbine1.p_out",
    "condenser1.p_out",
    "condenser1.vapor_mass_fraction_out",
    "valve2.p_out",
    "turbine2.efficiency",
    "turbine2.p_out",
    "condenser2.vapor_mass_fraction_out",
    "pump1.efficiency",
    "pump2.efficiency",
]

# Defaults
DEFAULT_SCALE_MIN = 0.2
DEFAULT_SCALE_MAX = 10.0
DEFAULT_N_SAMPLES = 100
DEFAULT_N_WORKERS = 8
DEFAULT_SEED = 42
DEFAULT_LOG_LEVEL = "NONE"

# Paths
DEFAULT_SWEEP_DIR = Path(__file__).parent / "run_flexible_DF_manual_sweep"
INPUT_FILE = Path(__file__).parent / "flexible_DF_manual.yml"


def get_nested_value(d: dict, path: str):
    """Get value from nested dict using dot-separated path."""
    keys = path.split(".")
    for key in keys:
        d = d[key]
    return d


def set_nested_value(d: dict, path: str, value):
    """Set value in nested dict using dot-separated path."""
    keys = path.split(".")
    for key in keys[:-1]:
        d = d[key]
    d[keys[-1]] = value


def generate_design_matrix(
    n_samples: int,
    seed: int,
    scale_min: float,
    scale_max: float,
    output_file: Path,
) -> pl.DataFrame:
    """Generate LHS design matrix and save to parquet."""
    output_file.parent.mkdir(exist_ok=True, parents=True)

    # Create .gitignore to exclude sweep outputs from version control
    gitignore_file = output_file.parent / ".gitignore"
    if not gitignore_file.exists():
        with open(gitignore_file, "w") as f:
            f.write("*\n")

    # Generate LHS samples (0-1 range)
    sampler = qmc.LatinHypercube(d=len(PARAMETERS), seed=seed)
    samples = sampler.random(n=n_samples)

    # Scale to [scale_min, scale_max]
    scale_factors = qmc.scale(samples, scale_min, scale_max)

    # Create DataFrame with parameter columns
    data = {param: scale_factors[:, i] for i, param in enumerate(PARAMETERS)}
    data["row_idx"] = list(range(n_samples))

    df = pl.DataFrame(data)
    df.write_parquet(output_file)
    print_datetime()
    print(f"Generated design matrix: {output_file} ({n_samples} samples)")
    print_datetime()
    return df


def run_single_simulation(args: tuple) -> None:
    """Run a single simulation for the given row index.

    Args is a tuple of (row_idx, design_matrix_file, results_dir, log_level, verbose).
    """
    row_idx, design_matrix_file, results_dir, log_level, verbose = args
    result_file = results_dir / f"{row_idx:06d}.json"

    # Skip if already completed by row index
    if result_file.exists():
        return

    # Load design matrix row
    df = pl.read_parquet(design_matrix_file)
    row = df.filter(pl.col("row_idx") == row_idx).to_dicts()[0]

    # Create runner
    runner = Runner(
        input_file=INPUT_FILE,
        no_save=True,
        log_level=log_level,
    )

    result = {
        "row_idx": row_idx,
        "specs_hash": None,
        "LCOE": None,
        "error": None,
    }

    try:
        # Apply scale factors to parameters
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

        # Run simulation
        runner.start()
        result["LCOE"] = runner.tango.workflow.economic._results["LCOE"]

    except Exception as e:
        result["error"] = {
            "type": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc(),
        }

    # Save result
    results_dir.mkdir(exist_ok=True, parents=True)
    with open(result_file, "w") as f:
        json.dump(result, f, indent=2)


def run_sweep(
    design_matrix_file: Path,
    results_dir: Path,
    n_workers: int,
    log_level: str = DEFAULT_LOG_LEVEL,
    quiet: bool = False,
    progress_interval: int | None = None,
) -> None:
    """Run the parameter sweep in parallel."""
    # Load design matrix
    df = pl.read_parquet(design_matrix_file)
    n_samples = len(df)

    # Find incomplete rows
    results_dir.mkdir(exist_ok=True, parents=True)
    completed = {int(f.stem) for f in results_dir.glob("*.json")}
    pending = [i for i in range(n_samples) if i not in completed]

    if not quiet:
        print(f"Sweep status: {len(completed)}/{n_samples} completed, {len(pending)} pending")

    if not pending:
        if not quiet:
            print("All simulations complete!")
        return

    # Prepare args for each worker (includes log_level and quiet)
    worker_args = [(idx, design_matrix_file, results_dir, log_level, quiet) for idx in pending]

    # Progress interval defaults to n_workers if not specified
    interval = progress_interval if progress_interval is not None else n_workers

    # Run in parallel with progress tracking
    with multiprocessing.Pool(n_workers) as pool:
        completed_count = 0
        total = len(pending)
        for _ in pool.imap_unordered(run_single_simulation, worker_args):
            completed_count += 1
            # Print progress at specified interval
            if not quiet and completed_count % interval == 0:
                print_datetime()
                print(f"Progress: {completed_count}/{total} completed")

        # Final progress if not already printed
        if not quiet and completed_count % interval != 0:
            print_datetime()
            print(f"Progress: {completed_count}/{total} completed")

    if not quiet:
        print("Sweep complete!")


def aggregate_results(results_dir: Path) -> pl.DataFrame:
    """Aggregate all result files into a single DataFrame."""
    results = []
    for f in sorted(results_dir.glob("*.json")):
        with open(f) as fp:
            results.append(json.load(fp))

    # Flatten error dict to string for storage
    for r in results:
        if r["error"] is not None:
            r["error"] = json.dumps(r["error"])

    return pl.DataFrame(results)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="LHS Parameter Sweep for TANGO simulations",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--scale-min",
        type=float,
        default=DEFAULT_SCALE_MIN,
        help="Minimum scale factor for parameters",
    )
    parser.add_argument(
        "--scale-max",
        type=float,
        default=DEFAULT_SCALE_MAX,
        help="Maximum scale factor for parameters",
    )
    parser.add_argument(
        "--n-samples",
        type=int,
        default=DEFAULT_N_SAMPLES,
        help="Number of LHS samples to generate",
    )
    parser.add_argument(
        "--n-workers",
        type=int,
        default=DEFAULT_N_WORKERS,
        help="Number of parallel workers",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Regenerate design matrix even if it exists",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=DEFAULT_LOG_LEVEL,
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
    return parser.parse_args()


def main(
    scale_min: float = DEFAULT_SCALE_MIN,
    scale_max: float = DEFAULT_SCALE_MAX,
    n_samples: int = DEFAULT_N_SAMPLES,
    n_workers: int = DEFAULT_N_WORKERS,
    seed: int = DEFAULT_SEED,
    regenerate: bool = False,
    log_level: str = DEFAULT_LOG_LEVEL,
    quiet: bool = False,
    progress_interval: int | None = None,
    sweep_dir: Path | None = None,
) -> None:
    """Run the full LHS sweep pipeline.

    Can be called programmatically or via CLI.
    """
    sweep_dir = sweep_dir if sweep_dir is not None else DEFAULT_SWEEP_DIR
    design_matrix_file = sweep_dir / "design_matrix.parquet"
    results_dir = sweep_dir / "results"

    if not quiet:
        print(f"Parameters: {len(PARAMETERS)}")
        print(f"Scale range: [{scale_min}, {scale_max}]")
        print(f"Samples: {n_samples}")
        print(f"Workers: {n_workers}")
        print(f"Seed: {seed}")

    # Task 1: Generate design matrix (and clear results if regenerating)
    if regenerate or not design_matrix_file.exists():
        # Clear old results when regenerating
        if regenerate and results_dir.exists():
            import shutil

            shutil.rmtree(results_dir)
            if not quiet:
                print(f"Cleared old results: {results_dir}")
        generate_design_matrix(
            n_samples=n_samples,
            seed=seed,
            scale_min=scale_min,
            scale_max=scale_max,
            output_file=design_matrix_file,
        )
    elif not quiet:
        print(f"Design matrix exists: {design_matrix_file}")

    # Task 2: Run simulations
    run_sweep(
        design_matrix_file, results_dir, n_workers, log_level, quiet, progress_interval,
    )

    # Aggregate results
    results_df = aggregate_results(results_dir)
    results_file = sweep_dir / "results.parquet"
    results_df.write_parquet(results_file)
    if not quiet:
        print(f"Results saved: {results_file}")

    # Summary
    n_success = results_df.filter(pl.col("LCOE").is_not_null()).height
    n_failed = results_df.filter(pl.col("error").is_not_null()).height
    if not quiet:
        print(f"\nSummary: {n_success} succeeded, {n_failed} failed")


if __name__ == "__main__":
    args = parse_args()
    if args.quiet and args.progress_interval is not None:
        raise ValueError("--quiet and --progress-interval are mutually exclusive")
    main(
        scale_min=args.scale_min,
        scale_max=args.scale_max,
        n_samples=args.n_samples,
        n_workers=args.n_workers,
        seed=args.seed,
        regenerate=args.regenerate,
        log_level=args.log_level,
        quiet=args.quiet,
        progress_interval=args.progress_interval,
        sweep_dir=args.sweep_dir,
    )
