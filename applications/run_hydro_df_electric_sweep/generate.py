"""Design matrix generation stage for the tango double-flash sensitivity sweep pipeline.

One-at-a-time (OFAT) design, not LHS: for each parameter in
``PARAMETER_BOUNDS``, one row holds it at its low bound and one row holds it
at its high bound, with every OTHER parameter at baseline (scale factor
1.0) — plus one pure-baseline row (every parameter at 1.0). This directly
answers this sweep's actual goal (confirm every parameter has a real effect
on the outputs) without the combinatorial blow-up of varying all parameters
at once: an LHS draw across ~30 simultaneously-varied parameters had a near-0%
feasible-design rate in practice (most combinations pushed some part of the
plant/well/reservoir model out of its valid range at once), while a single
parameter moved in isolation from baseline is far more likely to stay
feasible AND gives a direct, attributable before/after comparison per
parameter — exactly what "does this variable matter" needs.

Parameters whose bounds are degenerate (``low == high``, i.e. "fixed, no
variation" — see ``common.py``'s ``PARAMETER_BOUNDS`` comments) are skipped
entirely: a low/high pair that's identical to baseline tests nothing.

Total design points: ``1 + 2 * (number of non-degenerate parameters)`` —
small and fixed, not a tunable sample count, so there's no ``--n-samples``/
``--seed`` here (nothing is randomly sampled).
"""

import argparse
import shutil
from pathlib import Path

import polars as pl
from common import (
    DEFAULT_SWEEP_DIR,
    PARAMETER_BOUNDS,
    PARAMETERS,
    load_params,
)


def generate_design_matrix(output_file: Path) -> pl.DataFrame:
    """Generate the one-at-a-time low/high design matrix and save to parquet.

    Each row sets exactly one parameter away from baseline (scale factor
    1.0 for every other parameter) — see module docstring. ``swept_param``/
    ``level`` columns identify which parameter and direction each row tests
    (``"baseline"``/``"low"``/``"high"``), for the per-parameter sensitivity
    comparison ``summarize.py`` builds from this design.
    """
    output_file.parent.mkdir(exist_ok=True, parents=True)

    baseline = dict.fromkeys(PARAMETERS, 1.0)
    rows: list[dict] = [{"row_idx": 0, "swept_param": "baseline", "level": "baseline", **baseline}]

    row_idx = 1
    for param in PARAMETERS:
        low_scale, high_scale = PARAMETER_BOUNDS[param]
        if low_scale == high_scale:
            continue
        for level, scale in (("low", low_scale), ("high", high_scale)):
            row = dict(baseline)
            row[param] = scale
            rows.append({"row_idx": row_idx, "swept_param": param, "level": level, **row})
            row_idx += 1

    df = pl.DataFrame(rows)
    df.write_parquet(output_file)
    print(f"Generated design matrix: {output_file} ({len(df)} rows, one-at-a-time low/high design)")
    return df


def main(
    regenerate: bool = False,
    quiet: bool = False,
    sweep_dir: Path | None = None,
) -> None:
    """Generate the one-at-a-time design matrix, skipping if it already exists."""
    sweep_dir = sweep_dir if sweep_dir is not None else DEFAULT_SWEEP_DIR
    design_matrix_file = sweep_dir / "design_matrix.parquet"
    results_dir = sweep_dir / "results"

    if not quiet:
        n_varied = sum(1 for lo, hi in PARAMETER_BOUNDS.values() if lo != hi)
        print(f"Parameters: {len(PARAMETERS)} total, {n_varied} varied (rest fixed, low == high)")
        print(f"Design points: {1 + 2 * n_varied} (1 baseline + 2 per varied parameter)")

    if regenerate or not design_matrix_file.exists():
        if regenerate and results_dir.exists():
            shutil.rmtree(results_dir)
            if not quiet:
                print(f"Cleared old results: {results_dir}")
        generate_design_matrix(output_file=design_matrix_file)
    elif not quiet:
        print(f"Design matrix exists: {design_matrix_file}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the design matrix generator."""
    load_params()  # validates params.yaml parses even though nothing here reads it
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description="Generate the one-at-a-time low/high design matrix for the tango double-flash sweep",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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
        regenerate=args.regenerate,
        quiet=args.quiet,
        sweep_dir=args.sweep_dir,
    )
