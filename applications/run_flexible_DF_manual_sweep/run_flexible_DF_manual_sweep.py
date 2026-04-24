"""LHS Parameter Sweep for flexible_DF_manual.yml

Latin Hypercube Sampling sweep with parallel execution and checkpoint/resume.

Usage:
    python run_flexible_DF_manual_sweep.py --n-samples 100 --n-workers 8
    python run_flexible_DF_manual_sweep.py --regenerate --n-samples 1000

Parameter bounds are defined per-parameter in PARAMETER_BOUNDS dict.
"""

import argparse
import json
import multiprocessing
import traceback
from pathlib import Path

import polars as pl
import yaml
from scipy.stats import qmc  # type: ignore[import-untyped]

import tango
from tango.runner import Runner
from tango.utils import print_datetime

# Parameter bounds: (min_scale, max_scale) relative to base YAML values
# Bounds are derived from:
#   - Validation limits (e.g., well_length max 15km, diameter max 5m)
#   - Physics constraints (e.g., CoolProp valid ranges for pressures)
#   - Sensitivity considerations (some params can vary widely, others are sensitive)
PARAMETER_BOUNDS: dict[str, tuple[float, float]] = {
    # --- Material properties (relatively flexible) ---
    "props.brine_density": (0.9, 1.1),  # scale factor, ±10%
    "props.rock_density": (0.8, 1.2),  # scale factor, ±20%
    "props.rock_cp": (0.5, 2.0),  # scale factor, wide range ok
    "props.rock_k": (0.5, 2.0),  # scale factor, wide range ok
    "props.thermal_gradient": (0.7, 1.5),  # scale factor, ±30-50%
    # --- Surface parameters ---
    "surface.surface_temperature": (0.9, 1.1),  # scale factor, ±10% (base ~288K)
    "surface.surface_pressure": (0.9, 1.1),  # scale factor, ±10% (base 100kPa)
    "surface.pipe_diameter": (0.5, 2.0),  # scale factor, max 5m validation limit
    "surface.approach_temperature": (0.5, 2.0),  # scale factor, 3.5-14K range
    "surface.target_extraction_pressure": (
        0.7,
        1.5,
    ),  # scale factor, CoolProp sensitive
    # --- Reservoir parameters ---
    "reservoir.reservoir_depth": (0.5, 1.5),  # scale factor, 2.5-7.5km range
    "reservoir.thickness": (0.5, 2.0),  # scale factor, 150-600m range
    "reservoir.permeability": (
        0.1,
        10.0,
    ),  # scale factor, wide range (log-scale in reality)
    "reservoir.porosity": (0.5, 2.0),  # scale factor, 5-20% range
    "reservoir.hydro_static_pressure": (0.8, 1.2),  # scale factor, ±20%
    "reservoir.over_pressure_percentage": (0.5, 2.0),  # scale factor, 5-20% range
    # --- Well parameters (constrained by 15km max validation limit) ---
    # Base: inj=5km, prod=4km, pump=1km → total prod=5km
    # At 3x: 15km each → hits validation limit
    "injection_well.well_length": (
        0.5,
        2.5,
    ),  # scale factor, max ~12.5km (under 15km limit)
    "injection_well.diameter": (0.5, 2.0),  # scale factor, max ~0.8m (under 5m limit)
    "production_well.well_length": (0.5, 2.5),  # scale factor, max ~10km
    "production_well.diameter": (0.5, 2.0),  # scale factor
    "production_well_pump.well_length": (0.5, 2.5),  # scale factor, max ~2.5km
    "production_well_pump.diameter": (0.5, 2.0),  # scale factor
    # --- Schedule parameters ---
    "schedule.mass_flow_rate": (0.5, 2.0),  # scale factor, 25-100 kg/s
    "schedule.well_spacing": (0.5, 2.0),  # scale factor, 350-1400m
    "schedule.num_pp": (1.0, 3.0),  # scale factor, 1-3 patterns (integer)
    "schedule.mass_rate.value": (0.5, 2.0),  # scale factor, matches mass_flow_rate
    # --- Economic parameters (flexible) ---
    "economic.discount_rate": (0.5, 2.0),  # scale factor, 4.75-19%
    # --- Power plant components (pressure-sensitive, CoolProp constraints) ---
    "valve1.p_out": (0.5, 2.0),  # scale factor, 0.5-2 bar (base 1 bar)
    "turbine1.efficiency": (0.7, 1.0),  # scale factor, 70-100% (capped at 1.0)
    "turbine1.p_out": (0.5, 3.0),  # scale factor, 0.025-0.15 bar
    "condenser1.p_out": (0.5, 3.0),  # scale factor, 0.025-0.15 bar
    "condenser1.vapor_mass_fraction_out": (1.0, 1.0),  # fixed at 0 (no variation)
    "valve2.p_out": (0.5, 2.0),  # scale factor, 0.25-1 bar (base 0.5 bar)
    "turbine2.efficiency": (0.7, 1.0),  # scale factor, 70-100%
    "turbine2.p_out": (0.5, 3.0),  # scale factor, 0.025-0.15 bar
    "condenser2.vapor_mass_fraction_out": (1.0, 1.0),  # fixed at 0 (no variation)
    "pump1.efficiency": (0.7, 1.0),  # scale factor, 70-100%
    "pump2.efficiency": (0.7, 1.0),  # scale factor, 70-100%
}

# Derived: list of parameter names for iteration
PARAMETERS = list(PARAMETER_BOUNDS.keys())

# Defaults (overridden by params.yaml if present)
DEFAULT_N_SAMPLES = 100
DEFAULT_N_WORKERS = 8
DEFAULT_SEED = 42
DEFAULT_LOG_LEVEL = "NONE"

# Paths
DEFAULT_SWEEP_DIR = Path(__file__).parent / "outputs"
PARAMS_FILE = Path(__file__).parent / "params.yaml"
INPUT_FILE = Path(tango.__file__).parents[2] / "examples/flexible_DF_manual.yml"


def load_params() -> dict:
    """Load parameters from params.yaml if it exists alongside the script."""
    if PARAMS_FILE.exists():
        return yaml.safe_load(PARAMS_FILE.read_text()) or {}
    return {}


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
    output_file: Path,
) -> pl.DataFrame:
    """Generate LHS design matrix with per-parameter bounds and save to parquet."""
    output_file.parent.mkdir(exist_ok=True, parents=True)

    # Generate LHS samples (0-1 range)
    sampler = qmc.LatinHypercube(d=len(PARAMETERS), seed=seed)
    samples = sampler.random(n=n_samples)

    # Scale each parameter to its specific [min, max] bounds
    data: dict[str, list[float]] = {}
    for i, param in enumerate(PARAMETERS):
        min_scale, max_scale = PARAMETER_BOUNDS[param]
        # Scale from [0,1] to [min_scale, max_scale]
        data[param] = (samples[:, i] * (max_scale - min_scale) + min_scale).tolist()
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
        print(
            f"Sweep status: {len(completed)}/{n_samples} completed, {len(pending)} pending",
            flush=True,
        )

    if not pending:
        if not quiet:
            print("All simulations complete!")
        return

    # Prepare args for each worker (includes log_level and quiet)
    worker_args = [(idx, design_matrix_file, results_dir, log_level, quiet) for idx in pending]

    # Progress interval defaults to n_workers if not specified
    interval = progress_interval if progress_interval is not None else n_workers

    # Run in parallel with progress tracking
    # Use 'spawn' context for HPC compatibility (fork can cause issues on SLURM)
    if not quiet:
        print(f"Starting pool with {n_workers} workers (spawn context)...", flush=True)
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(n_workers) as pool:
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


def write_summary(results_df: pl.DataFrame, output_file: Path) -> None:
    """Write LCOE summary statistics to YAML for DVC metrics tracking."""
    lcoe = results_df.filter(pl.col("LCOE").is_not_null())["LCOE"]
    n_success = len(lcoe)
    summary: dict = {
        "n_samples": len(results_df),
        "n_success": n_success,
        "n_failed": len(results_df) - n_success,
    }
    if n_success > 0:
        summary.update(
            {
                "lcoe_mean": float(lcoe.mean()),  # type: ignore[arg-type]
                "lcoe_std": float(lcoe.std()),  # type: ignore[arg-type]
                "lcoe_p25": float(lcoe.quantile(0.25)),  # type: ignore[arg-type]
                "lcoe_p50": float(lcoe.quantile(0.50)),  # type: ignore[arg-type]
                "lcoe_p75": float(lcoe.quantile(0.75)),  # type: ignore[arg-type]
                "lcoe_p95": float(lcoe.quantile(0.95)),  # type: ignore[arg-type]
            },
        )
    output_file.parent.mkdir(exist_ok=True, parents=True)
    with open(output_file, "w") as f:
        yaml.dump(summary, f, default_flow_style=False, sort_keys=False)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    params = load_params()
    parser = argparse.ArgumentParser(
        description="LHS Parameter Sweep for TANGO simulations",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--stage",
        type=str,
        default="all",
        choices=["generate", "sweep", "summarize", "all"],
        help="Pipeline stage to run (default: all). DVC calls individual stages.",
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
        help="Regenerate design matrix even if it exists (generate stage only)",
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
    return parser.parse_args()


def main(
    stage: str = "all",
    n_samples: int = DEFAULT_N_SAMPLES,
    n_workers: int = DEFAULT_N_WORKERS,
    seed: int = DEFAULT_SEED,
    regenerate: bool = False,
    log_level: str = DEFAULT_LOG_LEVEL,
    quiet: bool = False,
    progress_interval: int | None = None,
    sweep_dir: Path | None = None,
) -> None:
    """Run the sweep pipeline, or a single stage when called by DVC.

    Stages: generate → sweep → summarize. Use stage="all" to run end-to-end
    (default, for manual use). DVC calls each stage independently.
    """
    sweep_dir = sweep_dir if sweep_dir is not None else DEFAULT_SWEEP_DIR
    design_matrix_file = sweep_dir / "design_matrix.parquet"
    results_dir = sweep_dir / "results"
    results_file = sweep_dir / "results.parquet"
    summary_file = sweep_dir / "summary.yaml"

    if stage in ("generate", "all"):
        if not quiet:
            print(f"Parameters: {len(PARAMETERS)} (per-parameter bounds)")
            print(f"Samples: {n_samples}, seed: {seed}")
        if regenerate or not design_matrix_file.exists():
            if regenerate and results_dir.exists():
                import shutil

                shutil.rmtree(results_dir)
                if not quiet:
                    print(f"Cleared old results: {results_dir}")
            generate_design_matrix(n_samples=n_samples, seed=seed, output_file=design_matrix_file)
        elif not quiet:
            print(f"Design matrix exists: {design_matrix_file}")
        if stage == "generate":
            return

    if stage in ("sweep", "all"):
        if not quiet:
            print(f"Workers: {n_workers}")
        run_sweep(design_matrix_file, results_dir, n_workers, log_level, quiet, progress_interval)
        if stage == "sweep":
            return

    if stage in ("summarize", "all"):
        results_df = aggregate_results(results_dir)
        results_df.write_parquet(results_file)
        if not quiet:
            print(f"Results saved: {results_file}")
        write_summary(results_df, summary_file)
        if not quiet:
            n_success = results_df.filter(pl.col("LCOE").is_not_null()).height
            n_failed = results_df.filter(pl.col("error").is_not_null()).height
            print(f"Summary: {n_success} succeeded, {n_failed} failed → {summary_file}")


if __name__ == "__main__":
    args = parse_args()
    if args.quiet and args.progress_interval is not None:
        raise ValueError("--quiet and --progress-interval are mutually exclusive")
    main(
        stage=args.stage,
        n_samples=args.n_samples,
        n_workers=args.n_workers,
        seed=args.seed,
        regenerate=args.regenerate,
        log_level=args.log_level,
        quiet=args.quiet,
        progress_interval=args.progress_interval,
        sweep_dir=args.sweep_dir,
    )
