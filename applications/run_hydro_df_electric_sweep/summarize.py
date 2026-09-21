"""Result aggregation stage for the tango double-flash sensitivity sweep pipeline.

Reports both ``LCOE_USD_per_kWh`` and ``net_power_W`` distribution stats
(mean/std/p25/p50/p75/p95) — ``LCOE_USD_per_kWh`` is read from each design
point's ``DoubletEconomicComponent`` state (see ``sweep.py``'s module
docstring).

Also writes ``sensitivity_table.csv``: one row per design point (baseline +
each parameter's low/high), so it's easy to see at a glance whether a given
parameter actually moves ``LCOE_USD_per_kWh``/``net_power_W`` away from the
baseline row — this sweep's actual goal (see ``generate.py``'s module
docstring), not a full distribution over a huge combined design space.
"""

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


def _distribution_stats(series: pl.Series, prefix: str) -> dict:
    """Mean/std/p25/p50/p75/p95 of a numeric series, keyed by ``{prefix}_*``.

    ``std()`` of a single sample is null (undefined), not 0 — guarded
    separately rather than letting ``float(None)`` raise.
    """
    n = len(series)
    return {
        f"{prefix}_mean": float(series.mean()),  # type: ignore[arg-type]
        f"{prefix}_std": float(series.std()) if n > 1 else None,  # type: ignore[arg-type]
        f"{prefix}_p25": float(series.quantile(0.25)),  # type: ignore[arg-type]
        f"{prefix}_p50": float(series.quantile(0.50)),  # type: ignore[arg-type]
        f"{prefix}_p75": float(series.quantile(0.75)),  # type: ignore[arg-type]
        f"{prefix}_p95": float(series.quantile(0.95)),  # type: ignore[arg-type]
    }


def write_summary(results_df: pl.DataFrame, output_file: Path) -> None:
    """Write LCOE_USD_per_kWh + net_power_W summary statistics to YAML for DVC metrics tracking."""
    successful = results_df.filter(pl.col("error").is_null())
    n_success = len(successful)
    summary: dict = {
        "n_samples": len(results_df),
        "n_success": n_success,
        "n_failed": len(results_df) - n_success,
    }
    if n_success > 0:
        summary.update(_distribution_stats(successful["LCOE_USD_per_kWh"], "LCOE_USD_per_kWh"))
        summary.update(_distribution_stats(successful["net_power_W"], "net_power_W"))
    output_file.parent.mkdir(exist_ok=True, parents=True)
    with open(output_file, "w") as f:
        yaml.dump(summary, f, default_flow_style=False, sort_keys=False)


def build_sensitivity_table(results_df: pl.DataFrame) -> pl.DataFrame:
    """One row per design point, sorted so each parameter's low/high pair sits
    together — the baseline row, then every (swept_param, level) pair, for
    reading off each parameter's effect on ``LCOE_USD_per_kWh``/
    ``net_power_W`` relative to baseline at a glance. Failed design points
    keep their ``error`` message instead of null outputs, so a parameter
    that makes the model infeasible at its low or high bound is visible
    here too, not silently dropped.
    """
    cols = ["row_idx", "swept_param", "level", "LCOE_USD_per_kWh", "net_power_W", "T_prod_K", "error"]
    return results_df.select(cols).sort(
        pl.col("swept_param") != "baseline",  # baseline row first
        "swept_param",
        pl.col("level") != "baseline",  # then low/high in a stable order
        "level",
    )


def main(
    quiet: bool = False,
    sweep_dir: Path | None = None,
) -> None:
    """Aggregate sweep results and write parquet + YAML summary + sensitivity-table CSV."""
    sweep_dir = sweep_dir if sweep_dir is not None else DEFAULT_SWEEP_DIR
    results_dir = sweep_dir / "results"
    results_file = sweep_dir / "results.parquet"
    summary_file = sweep_dir / "summary.yaml"
    sensitivity_file = sweep_dir / "sensitivity_table.csv"

    results_df = aggregate_results(results_dir)
    results_df.write_parquet(results_file)
    if not quiet:
        print(f"Results saved: {results_file}")
    write_summary(results_df, summary_file)
    build_sensitivity_table(results_df).write_csv(sensitivity_file)
    if not quiet:
        n_success = results_df.filter(pl.col("error").is_null()).height
        n_failed = results_df.filter(pl.col("error").is_not_null()).height
        print(f"Summary: {n_success} succeeded, {n_failed} failed → {summary_file}")
        print(f"Sensitivity table: {sensitivity_file}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the sweep summarizer."""
    parser = argparse.ArgumentParser(
        description="Aggregate sweep results for the tango double-flash sweep",
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
