"""Result aggregation stage for the tango_next double-flash LHS sweep pipeline.

tango_next port of ``applications/run_flexible_DF_manual_sweep/summarize.py``.
Structure is unchanged except for what gets summarized: ``LCOE`` is always
``None`` here (no ``EconomicComponent`` wired up yet — see ``sweep.py``'s
module docstring), so instead of LCOE distribution stats this reports
``net_power_W`` distribution stats (mean/std/p25/p50/p75/p95), using the
exact same structure/quantiles old tango used for LCOE. ``LCOE`` is kept in
the summary explicitly as ``null`` with a comment, not silently dropped.
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


def write_summary(results_df: pl.DataFrame, output_file: Path) -> None:
    """Write net_power_W summary statistics to YAML for DVC metrics tracking.

    LCOE is always null in this port (pending tango_next's economic
    component — see sweep.py's module docstring) so it is reported as
    ``null`` here rather than silently omitted, and net_power_W distribution
    stats are reported in its place using the same stat set old tango used
    for LCOE.
    """
    net_power = results_df.filter(pl.col("error").is_null())["net_power_W"]
    n_success = len(net_power)
    summary: dict = {
        "n_samples": len(results_df),
        "n_success": n_success,
        "n_failed": len(results_df) - n_success,
        # Always null — no EconomicComponent wired up yet in tango_next
        # (Phase 1 placeholder); see sweep.py's module docstring. Kept here
        # explicitly rather than omitted so a reader doesn't mistake its
        # absence for an oversight.
        "LCOE": None,
    }
    if n_success > 0:
        summary.update(
            {
                "net_power_W_mean": float(net_power.mean()),  # type: ignore[arg-type]
                # std() of a single sample is null (undefined), not 0 — guard
                # separately rather than letting float(None) raise.
                "net_power_W_std": float(net_power.std()) if n_success > 1 else None,  # type: ignore[arg-type]
                "net_power_W_p25": float(net_power.quantile(0.25)),  # type: ignore[arg-type]
                "net_power_W_p50": float(net_power.quantile(0.50)),  # type: ignore[arg-type]
                "net_power_W_p75": float(net_power.quantile(0.75)),  # type: ignore[arg-type]
                "net_power_W_p95": float(net_power.quantile(0.95)),  # type: ignore[arg-type]
            },
        )
    output_file.parent.mkdir(exist_ok=True, parents=True)
    with open(output_file, "w") as f:
        yaml.dump(summary, f, default_flow_style=False, sort_keys=False)


def main(
    quiet: bool = False,
    sweep_dir: Path | None = None,
) -> None:
    """Aggregate sweep results and write parquet + YAML summary files."""
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
        n_success = results_df.filter(pl.col("error").is_null()).height
        n_failed = results_df.filter(pl.col("error").is_not_null()).height
        print(f"Summary: {n_success} succeeded, {n_failed} failed → {summary_file}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the sweep summarizer."""
    parser = argparse.ArgumentParser(
        description="Aggregate sweep results for the tango_next double-flash sweep",
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
