"""Design-matrix generation stage: full-factorial grid over depth × mass-flow × loop-length × loop-diameter."""

import argparse
from pathlib import Path

import polars as pl
from common import (
    DEFAULT_SWEEP_DIR,
    LOOP_DIAMETERS_M,
    LOOP_LENGTHS_M,
    MASS_FLOW_RATES_KG_S,
    WELL_DEPTHS_M,
)


def generate_design_matrix(output_file: Path, quiet: bool = False) -> pl.DataFrame:
    """Generate a full-factorial (depth × mass-flow × loop-length × loop-diameter) design matrix."""
    output_file.parent.mkdir(exist_ok=True, parents=True)

    rows = []
    row_idx = 0
    for depth in WELL_DEPTHS_M:
        for mdot in MASS_FLOW_RATES_KG_S:
            for loop_length in LOOP_LENGTHS_M:
                for loop_diameter in LOOP_DIAMETERS_M:
                    rows.append(
                        {
                            "row_idx": row_idx,
                            "well_depth_m": depth,
                            "mass_flow_kg_s": mdot,
                            "loop_length_m": loop_length,
                            "loop_diameter_m": loop_diameter,
                        },
                    )
                    row_idx += 1

    df = pl.DataFrame(rows)
    df.write_parquet(output_file)
    if not quiet:
        print(
            f"Generated design matrix: {len(df)} designs ({len(WELL_DEPTHS_M)} depths × "
            f"{len(MASS_FLOW_RATES_KG_S)} flow rates × {len(LOOP_LENGTHS_M)} loop lengths × "
            f"{len(LOOP_DIAMETERS_M)} loop diameters) → {output_file}",
        )
    return df


def main(
    regenerate: bool = False,
    quiet: bool = False,
    sweep_dir: Path | None = None,
) -> None:
    """Generate design matrix, skipping if it already exists unless regenerate=True."""
    sweep_dir = sweep_dir or DEFAULT_SWEEP_DIR
    design_matrix_file = sweep_dir / "design_matrix.parquet"

    if regenerate or not design_matrix_file.exists():
        generate_design_matrix(output_file=design_matrix_file, quiet=quiet)
    elif not quiet:
        print(f"Design matrix exists: {design_matrix_file}")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Generate depth × mass-flow × loop-length design matrix for Triemli sweep",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Regenerate design matrix even if it exists",
    )
    parser.add_argument("--quiet", "-q", action="store_true")
    parser.add_argument(
        "--sweep-dir",
        type=Path,
        default=None,
        help=f"Sweep output directory (default: {DEFAULT_SWEEP_DIR})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(regenerate=args.regenerate, quiet=args.quiet, sweep_dir=args.sweep_dir)
