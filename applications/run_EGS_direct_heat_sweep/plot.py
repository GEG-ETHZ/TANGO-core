"""Visualization stage: success/failure scatter and a parallel-coordinates plot.

Closely modeled on ``applications/run_AGS_direct_heat_sweep/plot.py``.
Run after summarize.py has written outputs/results.parquet.

Only two sweep axes here (well depth, mass flow) — EGS has no horizontal
loop, so there's no loop-length/loop-diameter grid to slice over like the
AGS direct-heat plot.py does. ``plot_success_scatter`` is therefore a single
scatter plot, not a grid of subplots.

``LCOE_USD_per_kWh``/``CAPEX_total_USD`` are now populated (``sweep.py``
reads them from ``DoubletEconomicComponent``'s state) but this module
doesn't use them yet — the parallel-coordinates plots still color by
``thermal_power_kW``, and there's no LCOE-colored grid — that's queued as
separate follow-up plotting work, not done in this pass.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from common import DEFAULT_SWEEP_DIR

T_PROD_THRESHOLD_C = 105.0

# Axes shown in the parallel-coordinates plot, in order.
# row_idx first — not a design parameter, but lets you read off which
# specific design a line belongs to (matches the row_idx column in
# results.parquet and the <row_idx>.json filename in outputs/results/) by
# hovering/dragging on that axis instead of having to reverse-engineer it
# from the other values.
# Then inputs (well_depth_m, mass_flow_kg_per_s), then outputs: T_prod_C
# (whether the district-heating temperature target is met) and
# thermal_power_kW (how much useful heat the design actually delivers).
# CAPEX_total_USD/LCOE_USD_per_kWh are omitted from these axes for now —
# populated (see module docstring) but not yet wired into this plot;
# queued as follow-up plotting work.
_PARCOORD_COLUMNS: list[tuple[str, str]] = [
    ("row_idx", "Design\nindex"),
    ("well_depth_m", "Well depth\n[m]"),
    ("mass_flow_kg_per_s", "Mass flow\n[kg/s]"),
    ("T_prod_C", "T production\n[degC]"),
    ("thermal_power_kW", "Thermal power\n[kW]"),
]

_COLOR_COL_DISPLAY_NAMES: dict[str, str] = {
    "thermal_power_kW": "Thermal power [kW]",
}


def _display_name(color_col: str) -> str:
    """Human-facing label for a column, for titles/legends/colorbars only —
    never use this for data access (pl.col(...), df[...]), only for text
    shown to the viewer.
    """
    return _COLOR_COL_DISPLAY_NAMES.get(color_col, color_col)


def plot_success_scatter(df: pl.DataFrame, out_path: Path) -> None:
    """Single scatter plot: mass flow vs. well depth, colored by whether the
    design meets the T_prod >= 105 degC district-heating threshold.

    Unlike the AGS direct-heat port's grid-of-subplots version (rows/columns
    = loop diameter/length), EGS has only the two sweep axes plotted here,
    so a single panel suffices.
    """
    successful = df.filter(pl.col("error").is_null())
    meets = successful.filter(pl.col("T_prod_C") >= T_PROD_THRESHOLD_C)
    misses = successful.filter(pl.col("T_prod_C") < T_PROD_THRESHOLD_C)

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(
        misses["mass_flow_kg_per_s"],
        misses["well_depth_m"],
        marker="x",
        color="tab:red",
        s=35,
        label=f"< {T_PROD_THRESHOLD_C:.0f} degC",
    )
    ax.scatter(
        meets["mass_flow_kg_per_s"],
        meets["well_depth_m"],
        marker="o",
        color="tab:green",
        s=35,
        label=f">= {T_PROD_THRESHOLD_C:.0f} degC",
    )
    ax.set_xscale("log")
    ax.set_xlabel("Mass flow [kg/s]")
    ax.set_ylabel("Well depth [m]")
    ax.legend(loc="best", fontsize=9)
    ax.set_title(
        f"Designs meeting T_production >= {T_PROD_THRESHOLD_C:.0f} degC (district-heating threshold)",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_parallel_coordinates(df: pl.DataFrame, out_path: Path, color_col: str = "thermal_power_kW") -> None:
    """Parallel-coordinates plot across all sweep inputs and key outputs.

    Each design is one line crossing all axes (min-max normalized per axis so
    columns with very different units/ranges are comparable); lines are
    colored by `color_col` (default thermal_power_kW — switching this to
    LCOE_USD_per_kWh, now that it's populated, is queued as follow-up
    plotting work, see module docstring) so the delivered-heat gradient
    across the whole design space is visible at a glance.

    Color is normalized against the 5th-95th percentile of `color_col`, not
    its min/max, so a handful of outliers don't collapse the gradient for
    everyone else. Designs with `color_col` null (not expected for
    thermal_power_kW on a successful run, but handled defensively — see
    sweep.py, which sets it to NaN only if mass_flow_kg_per_s is zero, which
    never occurs in this sweep) are drawn in flat grey with reduced opacity.
    """
    successful = df.filter(pl.col("error").is_null())
    cols = [c for c, _ in _PARCOORD_COLUMNS if c in successful.columns]
    labels = [label for c, label in _PARCOORD_COLUMNS if c in successful.columns]

    data = successful.select(cols).to_numpy()
    mins = np.nanmin(data, axis=0)
    maxs = np.nanmax(data, axis=0)
    span = np.where(maxs > mins, maxs - mins, 1.0)
    normalized = (data - mins) / span

    color_values = successful[color_col].to_numpy()
    valid = ~np.isnan(color_values)
    cmap = plt.get_cmap("viridis")  # bright/yellow = high thermal power (good)
    c_min, c_max = np.nanpercentile(color_values, [5, 95])
    if c_max <= c_min:
        c_min, c_max = np.nanmin(color_values), np.nanmax(color_values)
    c_span = c_max - c_min if c_max > c_min else 1.0
    clipped_color = np.clip(color_values, c_min, c_max)

    fig, ax = plt.subplots(figsize=(1.8 * len(cols), 6.5))
    x = np.arange(len(cols))
    n_undefined = int((~valid).sum())
    for row, color_value, is_valid in zip(normalized, clipped_color, valid, strict=True):
        if is_valid:
            color = cmap((color_value - c_min) / c_span)
            ax.plot(x, row, color=color, alpha=0.35, linewidth=0.8)
        else:
            ax.plot(x, row, color="lightgrey", alpha=0.6, linewidth=0.8, zorder=-1)
    if n_undefined:
        ax.plot(
            [],
            [],
            color="lightgrey",
            linewidth=2,
            label=f"{_display_name(color_col)} undefined (n={n_undefined})",
        )
        ax.legend(loc="lower right", fontsize=8, framealpha=0.9)

    for i, (col_min, col_max, label) in enumerate(zip(mins, maxs, labels, strict=True)):
        ax.axvline(i, color="grey", linewidth=0.8, zorder=0)
        ax.text(
            i,
            1.04,
            f"{col_max:.3g}",
            ha="center",
            va="bottom",
            fontsize=8,
            transform=ax.get_xaxis_transform(),
        )
        ax.text(
            i,
            -0.04,
            f"{col_min:.3g}",
            ha="center",
            va="top",
            fontsize=8,
            transform=ax.get_xaxis_transform(),
        )
        ax.text(
            i,
            -0.15,
            label,
            ha="center",
            va="top",
            fontsize=9,
            transform=ax.get_xaxis_transform(),
        )

    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlim(-0.2, len(cols) - 0.8)
    ax.set_ylim(-0.28, 1.14)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=c_min, vmax=c_max))
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, extend="both")
    cbar.set_label(f"{_display_name(color_col)} (5th-95th pctile; outliers clipped)")

    fig.suptitle("Triemli EGS direct-heat sweep (tango) — all designs", y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_parallel_coordinates_interactive(
    df: pl.DataFrame,
    out_path: Path,
    color_col: str = "thermal_power_kW",
    title: str | None = None,
) -> bool:
    """Interactive HTML version of plot_parallel_coordinates, using Plotly's
    Parcoords for real axis brushing (drag along an axis to filter the
    range shown) and hover tooltips — matplotlib has no equivalent.

    Requires the `dev` dependency group (plotly). Returns False (and prints
    a note instead of raising) if plotly isn't installed, so the rest of the
    plotting pipeline still runs for a base install.
    """
    try:
        import plotly.graph_objects as go  # noqa: PLC0415
    except ImportError:
        print(
            f"plotly not installed — skipping {out_path.name} (install with `uv sync --group dev`)",
        )
        return False

    successful = df.filter(pl.col("error").is_null())
    n_undefined = successful.filter(pl.col(color_col).is_null()).height
    plotted = successful.filter(pl.col(color_col).is_not_null())

    cols = [c for c, _ in _PARCOORD_COLUMNS if c in plotted.columns]
    labels = [label.replace("\n", " ") for c, label in _PARCOORD_COLUMNS if c in plotted.columns]

    color_values = plotted[color_col].to_numpy()
    c_min, c_max = np.percentile(color_values, [5, 95]) if len(color_values) else (0.0, 1.0)
    if c_max <= c_min:
        c_min, c_max = float(color_values.min()), float(color_values.max())

    dimensions = [
        {"label": label, "values": plotted[col].to_numpy()} for col, label in zip(cols, labels, strict=True)
    ]

    fig = go.Figure(
        data=go.Parcoords(
            line={
                "color": color_values,
                "colorscale": "Viridis",
                "cmin": c_min,
                "cmax": c_max,
                "showscale": True,
                "colorbar": {"title": f"{_display_name(color_col)}\n(5-95 pctile)"},
            },
            unselected={"line": {"color": "lightgrey", "opacity": 0.05}},
            dimensions=dimensions,
        ),
    )
    if title is None:
        title = (
            "Triemli EGS direct-heat sweep (tango) — all designs (interactive: drag along "
            f"an axis to filter; {n_undefined} designs with {_display_name(color_col)} undefined excluded)"
        )
    fig.update_layout(
        title=title,
        paper_bgcolor="#e8e8e8",
        plot_bgcolor="#e8e8e8",
    )
    fig.write_html(out_path)
    return True


def plot_parallel_coordinates_interactive_qualified(
    df: pl.DataFrame,
    out_path: Path,
    color_col: str = "thermal_power_kW",
    min_thermal_power_kW: float = 2000.0,
) -> bool:
    """Same as plot_parallel_coordinates_interactive, but restricted to designs
    that meet the T_prod >= 105 degC district-heating threshold AND deliver
    at least `min_thermal_power_kW` of thermal power.

    Filtering first (rather than plotting everything and asking the viewer to
    drag filters by hand) also tightens the color scale: the 5th-95th
    percentile is computed only over the filtered designs instead of the
    full sweep, so the colorbar actually resolves the spread among the
    designs that matter instead of being dominated by the much wider range
    across the full sweep.
    """
    qualified = df.filter(
        (pl.col("T_prod_C") >= T_PROD_THRESHOLD_C) & (pl.col("thermal_power_kW") >= min_thermal_power_kW),
    )
    n_qualified = qualified.filter(pl.col("error").is_null()).height
    title = (
        f"Triemli EGS direct-heat sweep (tango) — designs meeting T_prod >= {T_PROD_THRESHOLD_C:.0f} "
        f"degC and thermal power >= {min_thermal_power_kW / 1000:.0f} MW only (n={n_qualified}); "
        "interactive: drag along an axis to filter"
    )
    return plot_parallel_coordinates_interactive(qualified, out_path, color_col=color_col, title=title)


def main(quiet: bool = False, sweep_dir: Path | None = None) -> None:
    """Load results.parquet and write the scatter + parallel-coordinates plots."""
    sweep_dir = sweep_dir or DEFAULT_SWEEP_DIR
    results_parquet = sweep_dir / "results.parquet"
    df = pl.read_parquet(results_parquet)

    scatter_path = sweep_dir / "success_scatter.png"
    parcoord_path = sweep_dir / "parallel_coordinates.png"
    parcoord_html_path = sweep_dir / "parallel_coordinates.html"
    parcoord_qualified_html_path = sweep_dir / "parallel_coordinates_qualified.html"

    plot_success_scatter(df, scatter_path)
    # No lcoe_grid.png yet — LCOE_USD_per_kWh is populated now (see module
    # docstring) but this plot hasn't been built yet; queued as follow-up
    # plotting work.
    plot_parallel_coordinates(df, parcoord_path)
    wrote_html = plot_parallel_coordinates_interactive(df, parcoord_html_path)
    wrote_qualified_html = plot_parallel_coordinates_interactive_qualified(df, parcoord_qualified_html_path)

    if not quiet:
        print(f"Wrote {scatter_path}")
        print(f"Wrote {parcoord_path}")
        if wrote_html:
            print(f"Wrote {parcoord_html_path}")
        if wrote_qualified_html:
            print(f"Wrote {parcoord_qualified_html_path}")
        print(
            "Skipped lcoe_grid.png — not built yet in this port "
            "(LCOE_USD_per_kWh is populated; see this module's docstring).",
        )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Generate scatter and parallel-coordinates plots for the tango Triemli EGS sweep",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--quiet", "-q", action="store_true")
    parser.add_argument("--sweep-dir", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(quiet=args.quiet, sweep_dir=args.sweep_dir)
