"""Design matrix generation stage for the tango_next double-flash LHS sweep pipeline.

tango_next port of ``applications/run_flexible_DF_manual_sweep/generate.py``.
This stage's logic is entirely generic — parameter names/bounds come from
``common.py``, LHS sampling via ``scipy.stats.qmc.LatinHypercube`` is
unchanged — only the import now points at this directory's local
``common.py`` (21 tango_next parameters instead of old tango's 23; see
``common.py``'s docstring for the two dropped parameters), and the
``tango.utils.print_datetime`` calls are dropped since ``tango_next`` has no
equivalent helper (plain prints, matching the AGS/EGS tango_next ports).
"""

import argparse
import shutil
from pathlib import Path

import polars as pl
from common import (
    DEFAULT_N_SAMPLES,
    DEFAULT_SEED,
    DEFAULT_SWEEP_DIR,
    PARAMETER_BOUNDS,
    PARAMETERS,
    load_params,
)
from scipy.stats import qmc  # type: ignore[import-untyped]


def generate_design_matrix(n_samples: int, seed: int, output_file: Path) -> pl.DataFrame:
    """Generate LHS design matrix with per-parameter bounds and save to parquet."""
    output_file.parent.mkdir(exist_ok=True, parents=True)

    sampler = qmc.LatinHypercube(d=len(PARAMETERS), seed=seed)
    samples = sampler.random(n=n_samples)

    data: dict[str, list[float]] = {}
    for i, param in enumerate(PARAMETERS):
        min_scale, max_scale = PARAMETER_BOUNDS[param]
        data[param] = (samples[:, i] * (max_scale - min_scale) + min_scale).tolist()
    data["row_idx"] = list(range(n_samples))

    df = pl.DataFrame(data)
    df.write_parquet(output_file)
    print(f"Generated design matrix: {output_file} ({n_samples} samples)")
    return df


def main(
    n_samples: int = DEFAULT_N_SAMPLES,
    seed: int = DEFAULT_SEED,
    regenerate: bool = False,
    quiet: bool = False,
    sweep_dir: Path | None = None,
) -> None:
    """Generate the LHS design matrix, skipping if it already exists."""
    sweep_dir = sweep_dir if sweep_dir is not None else DEFAULT_SWEEP_DIR
    design_matrix_file = sweep_dir / "design_matrix.parquet"
    results_dir = sweep_dir / "results"

    if not quiet:
        print(f"Parameters: {len(PARAMETERS)} (per-parameter bounds)")
        print(f"Samples: {n_samples}, seed: {seed}")

    if regenerate or not design_matrix_file.exists():
        if regenerate and results_dir.exists():
            shutil.rmtree(results_dir)
            if not quiet:
                print(f"Cleared old results: {results_dir}")
        generate_design_matrix(n_samples=n_samples, seed=seed, output_file=design_matrix_file)
    elif not quiet:
        print(f"Design matrix exists: {design_matrix_file}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the design matrix generator."""
    params = load_params()
    parser = argparse.ArgumentParser(
        description="Generate LHS design matrix for the tango_next double-flash sweep",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--n-samples",
        type=int,
        default=params.get("n_samples", DEFAULT_N_SAMPLES),
        help="Number of LHS samples to generate",
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
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress progress output")
    parser.add_argument(
        "--sweep-dir",
        type=Path,
        default=None,
        help=f"Directory for sweep outputs (default: {DEFAULT_SWEEP_DIR})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(
        n_samples=args.n_samples,
        seed=args.seed,
        regenerate=args.regenerate,
        quiet=args.quiet,
        sweep_dir=args.sweep_dir,
    )
