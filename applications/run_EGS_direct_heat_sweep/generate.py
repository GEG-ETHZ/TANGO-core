"""Design-matrix generation stage: full-factorial grid over depth x mass-flow.

tango port of ``applications/run_EGS_direct_heat_sweep/generate.py`` —
logic is unchanged, only the ``common`` import now points at this
directory's local ``common.py``. Only two axes (no loop-length/diameter,
unlike the AGS direct-heat sweep) since EGS has no horizontal loop.
"""

import argparse
from pathlib import Path

import polars as pl
from common import (
    DEFAULT_SWEEP_DIR,
    MASS_FLOW_RATES_KG_S,
    WELL_DEPTHS_M,
)


def generate_design_matrix(output_file: Path, quiet: bool = False, smoke: bool = False) -> pl.DataFrame:
    """Generate a full-factorial (depth x mass-flow) design matrix.

    ``smoke=True`` restricts both axes to just their min and max value (a
    2x2 = 4-design corner subset) instead of the full 10x10 = 100-design
    grid — for a fast "does the pipeline still run end to end" check, not
    for real sweep results.
    """
    output_file.parent.mkdir(exist_ok=True, parents=True)

    depths = [WELL_DEPTHS_M[0], WELL_DEPTHS_M[-1]] if smoke else WELL_DEPTHS_M
    mdots = [MASS_FLOW_RATES_KG_S[0], MASS_FLOW_RATES_KG_S[-1]] if smoke else MASS_FLOW_RATES_KG_S

    rows = []
    row_idx = 0
    for depth in depths:
        for mdot in mdots:
            rows.append({"row_idx": row_idx, "well_depth_m": depth, "mass_flow_kg_per_s": mdot})
            row_idx += 1

    df = pl.DataFrame(rows)
    df.write_parquet(output_file)
    if not quiet:
        print(
            f"Generated design matrix: {len(df)} designs ({len(depths)} depths x "
            f"{len(mdots)} flow rates) -> {output_file}",
        )
    return df


def main(
    regenerate: bool = False,
    quiet: bool = False,
    sweep_dir: Path | None = None,
    smoke: bool = False,
) -> None:
    """Generate design matrix, skipping if it already exists unless regenerate=True.

    ``smoke=True`` always regenerates (the tiny matrix is cheap to rebuild
    and must never be confused with a cached full-grid matrix from a real
    sweep) — see ``generate_design_matrix``.
    """
    sweep_dir = sweep_dir or DEFAULT_SWEEP_DIR
    design_matrix_file = sweep_dir / "design_matrix.parquet"

    if smoke or regenerate or not design_matrix_file.exists():
        generate_design_matrix(output_file=design_matrix_file, quiet=quiet, smoke=smoke)
    elif not quiet:
        print(f"Design matrix exists: {design_matrix_file}")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description="Generate depth x mass-flow design matrix for tango Triemli EGS sweep",
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
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Generate a tiny 4-design corner subset instead of the full 100-design grid",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(regenerate=args.regenerate, quiet=args.quiet, sweep_dir=args.sweep_dir, smoke=args.smoke)
