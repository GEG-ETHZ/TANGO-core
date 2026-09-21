"""Visualization stage: per-parameter sensitivity ("tornado") charts.

Homologized with the AGS/EGS direct-heat sweeps' plot.py (same DVC stage
shape — reads outputs/results.parquet, writes into outputs/ — see those
modules for the sibling pattern), but this pipeline's actual design
doesn't fit a parallel-coordinates or 2-axis-grid plot the way a
full-factorial sweep does: only ONE parameter differs from baseline in
any given design point (see generate.py's module docstring for why), so
a parallel-coordinates plot across all ~30 scale-factor columns would be
a wall of flat lines at 1.0 with one tiny blip each — not a meaningful
picture. The natural fit for a one-at-a-time (OFAT) design is a tornado
chart: for each varied parameter, how far do its low/high bound designs
move each objective away from the baseline design, sorted by effect
size. This directly answers this sweep's actual goal (does each
parameter have a real effect) the same way ``outputs/sensitivity_table.csv``
(``summarize.py``) does in tabular form — this is the visual companion.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import polars as pl
from common import DEFAULT_SWEEP_DIR

_METRICS: list[tuple[str, str]] = [
    ("LCOE_USD_per_kWh", "LCOE [USD/kWh]"),
    ("net_power_W", "Net power [W]"),
]


def _tornado_data(df: pl.DataFrame, metric: str) -> pl.DataFrame:
    """One row per varied parameter: baseline value, low/high deltas from it.

    Only successful designs contribute (``error is None``); a parameter
    whose low or high design failed outright gets a null delta for that
    side rather than being silently dropped — a parameter that breaks the
    model at one of its bounds is itself a real, worth-seeing result (see
    ``generate.py``'s module docstring on why the old LHS design had a
    near-0% success rate).
    """
    successful = df.filter(pl.col("error").is_null())
    baseline_rows = successful.filter(pl.col("swept_param") == "baseline")
    if baseline_rows.is_empty():
        return pl.DataFrame({"swept_param": [], "baseline": [], "low_delta": [], "high_delta": []})
    baseline_value = baseline_rows[metric][0]

    rows = []
    for param in sorted(set(df["swept_param"]) - {"baseline"}):
        low = successful.filter((pl.col("swept_param") == param) & (pl.col("level") == "low"))
        high = successful.filter((pl.col("swept_param") == param) & (pl.col("level") == "high"))
        low_delta = float(low[metric][0]) - baseline_value if not low.is_empty() else None
        high_delta = float(high[metric][0]) - baseline_value if not high.is_empty() else None
        if low_delta is None and high_delta is None:
            continue  # both bounds failed for this parameter -- nothing to plot
        rows.append({"swept_param": param, "low_delta": low_delta, "high_delta": high_delta})

    tbl = pl.DataFrame(
        rows,
        schema={"swept_param": pl.Utf8, "low_delta": pl.Float64, "high_delta": pl.Float64},
    )
    max_abs = pl.max_horizontal(pl.col("low_delta").abs(), pl.col("high_delta").abs())
    return tbl.with_columns(baseline=pl.lit(baseline_value)).sort(max_abs, descending=False, nulls_last=True)


def plot_tornado(df: pl.DataFrame, out_path: Path) -> None:
    """One tornado sub-plot per metric in ``_METRICS``, stacked vertically.

    Each row is one varied parameter; bars show its low/high design's
    delta from the baseline design for that metric, sorted by effect
    size (biggest mover at the top). A parameter whose bars are both
    imperceptibly thin genuinely has little effect on that metric over
    the sampled range — that's a real, useful negative result, not a
    plotting failure.
    """
    fig, axes = plt.subplots(1, len(_METRICS), figsize=(9 * len(_METRICS), max(6, 0.35 * df.height)))
    if len(_METRICS) == 1:
        axes = [axes]

    for ax, (metric, label) in zip(axes, _METRICS, strict=True):
        tbl = _tornado_data(df, metric)
        if tbl.is_empty():
            ax.text(0.5, 0.5, "No successful baseline design", ha="center", va="center")
            ax.set_title(label)
            continue

        y = range(tbl.height)
        params = tbl["swept_param"].to_list()
        low = tbl["low_delta"].fill_null(0.0).to_list()
        high = tbl["high_delta"].fill_null(0.0).to_list()

        ax.barh(y, low, color="tab:blue", alpha=0.8, label="low bound")
        ax.barh(y, high, color="tab:orange", alpha=0.8, label="high bound")
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_yticks(list(y))
        ax.set_yticklabels(params, fontsize=8)
        ax.set_xlabel(f"Δ {label} from baseline")
        ax.set_title(label)
        ax.legend(loc="lower right", fontsize=8)
        ax.grid(visible=True, alpha=0.3, axis="x")

    fig.suptitle("hydro_df_electric one-at-a-time sensitivity sweep — per-parameter effect", y=1.0)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main(quiet: bool = False, sweep_dir: Path | None = None) -> None:
    """Load results.parquet and write the tornado chart."""
    sweep_dir = sweep_dir or DEFAULT_SWEEP_DIR
    df = pl.read_parquet(sweep_dir / "results.parquet")

    tornado_path = sweep_dir / "tornado.png"
    plot_tornado(df, tornado_path)

    if not quiet:
        print(f"Wrote {tornado_path}")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Generate the per-parameter sensitivity (tornado) chart for the tango hydro_df_electric sweep",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--quiet", "-q", action="store_true")
    parser.add_argument("--sweep-dir", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(quiet=args.quiet, sweep_dir=args.sweep_dir)
