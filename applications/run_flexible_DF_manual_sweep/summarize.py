"""Result aggregation stage for the DF manual sweep pipeline."""

import argparse
import json
from pathlib import Path

import polars as pl
import yaml
from common import DEFAULT_SWEEP_DIR


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


def main(
    quiet: bool = False,
    sweep_dir: Path | None = None,
) -> None:
    sweep_dir = sweep_dir if sweep_dir is not None else DEFAULT_SWEEP_DIR
    results_dir = sweep_dir / "results"
    results_file = sweep_dir / "results.parquet"
    summary_file = sweep_dir / "summary.yaml"

    results_df = aggregate_results(results_dir)
    results_df.write_parquet(results_file)
    if not quiet:
        print(f"Results saved: {results_file}")
    write_summary(results_df, summary_file)
    if not quiet:
        n_success = results_df.filter(pl.col("LCOE").is_not_null()).height
        n_failed = results_df.filter(pl.col("error").is_not_null()).height
        print(f"Summary: {n_success} succeeded, {n_failed} failed → {summary_file}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate sweep results for TANGO parameter sweep",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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
    main(quiet=args.quiet, sweep_dir=args.sweep_dir)
