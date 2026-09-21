"""Look up a design's row_idx and full result given approximate input parameters.

tango port of ``applications/run_AGS_direct_heat_sweep/find_design.py`` —
identical logic; this doesn't touch tango/tango or economics at all, it's
a pure nearest-neighbor lookup over the four sweep axes against the
aggregated results parquet.

Plotly's Parcoords trace has no hover tooltips (confirmed: no hoverinfo/
hovertemplate on the trace or its dimensions), so the interactive parallel-
coordinates plots can't show you a design's identity directly. Workaround:
drag narrow filter ranges on the plot's four input axes (well depth, mass
flow, loop length, loop diameter) until only the line(s) you care about
remain, read approximate values off the axes, then pass them here to get the
row_idx and result JSON path for the closest-matching design(s).

Matching is nearest-neighbor, not exact: distance is normalized per-axis by
that axis's actual range in the results, then combined across whichever
axes you provide (axes you omit don't constrain the match at all).

Usage
-----
    python find_design.py --well-depth-m 8000 --mass-flow-kg-s 30 \
        --loop-length-m 3500 --loop-diameter-m 0.75

    # Fewer axes, or a higher --top-n, widen the candidate set:
    python find_design.py --well-depth-m 8000 --top-n 10
"""

from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl
from common import DEFAULT_SWEEP_DIR

_DEFAULT_TOP_N = 5


def find_design(
    df: pl.DataFrame,
    well_depth_m: float | None = None,
    mass_flow_kg_per_s: float | None = None,
    loop_length_m: float | None = None,
    loop_diameter_m: float | None = None,
    top_n: int = _DEFAULT_TOP_N,
) -> pl.DataFrame:
    """Return the top_n designs nearest the given (possibly partial) parameter values.

    Distance is normalized per axis by that axis's actual range in `df`
    (max - min), so axes with very different units/scales (well_depth_m in
    thousands vs. loop_diameter_m in tenths) don't dominate the match just
    because of scale. Returns df with an added "_match_distance" column
    (0 = exact match), sorted ascending, truncated to top_n.
    """
    provided = {
        "well_depth_m": well_depth_m,
        "mass_flow_kg_per_s": mass_flow_kg_per_s,
        "loop_length_m": loop_length_m,
        "loop_diameter_m": loop_diameter_m,
    }
    provided = {col: value for col, value in provided.items() if value is not None}
    if not provided:
        msg = "Provide at least one parameter value to match against."
        raise ValueError(msg)

    dist_sq = pl.lit(0.0)
    for col, value in provided.items():
        col_min, col_max = df[col].min(), df[col].max()
        span = (col_max - col_min) or 1.0
        dist_sq = dist_sq + ((pl.col(col) - value) / span) ** 2

    return df.with_columns(dist_sq.sqrt().alias("_match_distance")).sort("_match_distance").head(top_n)


def main() -> None:
    """Parse CLI args, look up nearest-matching design(s), print results and JSON paths."""
    parser = argparse.ArgumentParser(
        description=(
            "Find the nearest-matching design(s) for approximate input parameters "
            "(read off the parallel-coordinates plot's axes after drag-filtering to isolate them)"
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--well-depth-m", type=float, default=None)
    parser.add_argument("--mass-flow-kg-s", type=float, default=None)
    parser.add_argument("--loop-length-m", type=float, default=None)
    parser.add_argument("--loop-diameter-m", type=float, default=None)
    parser.add_argument("--top-n", type=int, default=_DEFAULT_TOP_N, help="Number of nearest matches to show")
    parser.add_argument("--sweep-dir", type=Path, default=None)
    args = parser.parse_args()

    if all(
        v is None
        for v in [args.well_depth_m, args.mass_flow_kg_per_s, args.loop_length_m, args.loop_diameter_m]
    ):
        parser.error(
            "Provide at least one of --well-depth-m/--mass-flow-kg-s/--loop-length-m/--loop-diameter-m",
        )

    sweep_dir = args.sweep_dir or DEFAULT_SWEEP_DIR
    df = pl.read_parquet(sweep_dir / "results.parquet")

    matches = find_design(
        df,
        well_depth_m=args.well_depth_m,
        mass_flow_kg_per_s=args.mass_flow_kg_per_s,
        loop_length_m=args.loop_length_m,
        loop_diameter_m=args.loop_diameter_m,
        top_n=args.top_n,
    )

    display_cols = [
        "row_idx",
        "_match_distance",
        "well_depth_m",
        "mass_flow_kg_per_s",
        "loop_length_m",
        "loop_diameter_m",
        "T_prod_C",
        "thermal_power_kW",
        "error",
    ]
    with pl.Config(tbl_cols=len(display_cols), tbl_rows=50, float_precision=3):
        print(matches.select(display_cols))

    print()
    for row in matches.to_dicts():
        json_path = sweep_dir / "results" / f"{row['row_idx']:06d}.json"
        print(f"row_idx={row['row_idx']} (distance={row['_match_distance']:.4f}): {json_path}")


if __name__ == "__main__":
    main()
