"""Visualization stage: success/failure scatter, LCOE scatter, and a parallel-coordinates plot.

Run after summarize.py has written outputs/results.parquet.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from common import DEFAULT_SWEEP_DIR

# Qualification criterion for this power-generation sweep: is the design a
# net electricity producer once parasitic pumping/generator loads are
# subtracted? Unlike the sibling direct-heat sweep's fixed T_prod >= 105 degC
# district-heating delivery threshold, there's no analogous fixed target
# temperature for ORC economics — real ORC siting is driven by grid dispatch
# economics, not a delivery-temperature threshold. Positive net electric
# power is the natural binary equivalent (a design that's a net consumer,
# not a producer, of electricity is disqualified outright).
MIN_NET_ELECTRIC_POWER_KW = 0.0

# Axes shown in the parallel-coordinates plot, in order.
# row_idx first — not a design parameter, but lets you read off which
# specific design a line belongs to (matches the row_idx column in
# results.parquet and the <row_idx>.json filename in outputs/results/) by
# hovering/dragging on that axis instead of having to reverse-engineer it
# from the other seven values.
# Then inputs (well_depth_m, mass_flow_kg_s, loop_length_m, loop_diameter_m),
# then outputs chosen to tell the design story end to end:
#   - T_prod_C              production temperature reaching the ORC plant
#   - net_electric_power_kW how much net electricity the design actually delivers
#   - CAPEX_total_USD       what it costs to build
#   - LCOE_USD_per_kWh      the bottom-line cost-of-electricity metric (LCOE)
_PARCOORD_COLUMNS: list[tuple[str, str]] = [
    ("row_idx", "Design\nindex"),
    ("well_depth_m", "Well depth\n[m]"),
    ("mass_flow_kg_s", "Mass flow\n[kg/s]"),
    ("loop_length_m", "Loop length\n[m]"),
    ("loop_diameter_m", "Loop diameter\n[m]"),
    ("T_prod_C", "T production\n[degC]"),
    ("net_electric_power_kW", "Net electric power\n[kW]"),
    ("CAPEX_total_USD", "Total CAPEX\n[USD]"),
    ("LCOE_USD_per_kWh", "LCOE\n[USD/kWh_e]"),
]

# Display label for a color/value column in titles, legends, and colorbars.
# LCOE_USD_per_kWh is the raw column name (matches sweep.py/summarize.py,
# and the fact that it's literally computed as CAPEX / net_power regardless
# of product); this sweep runs in electricity mode, so LCOE is the correct
# term (unlike the sibling direct-heat sweep, which relabels it "LCOH").
_COLOR_COL_DISPLAY_NAMES: dict[str, str] = {
    "LCOE_USD_per_kWh": "LCOE [USD/kWh_e]",
}


def _display_name(color_col: str) -> str:
    """Human-facing label for a column, for titles/legends/colorbars only —
    never use this for data access (pl.col(...), df[...]), only for text
    shown to the viewer.
    """
    return _COLOR_COL_DISPLAY_NAMES.get(color_col, color_col)


def plot_success_scatter(df: pl.DataFrame, out_path: Path) -> None:
    """Grid of scatter subplots (rows = loop diameter, columns = loop length):
    mass flow vs. well depth, colored by whether the design is a net
    electricity producer (net_electric_power_kW > MIN_NET_ELECTRIC_POWER_KW).
    """
    successful = df.filter(pl.col("error").is_null())
    loop_lengths = sorted(successful.select("loop_length_m").unique().to_series().to_list())
    loop_diameters = sorted(successful.select("loop_diameter_m").unique().to_series().to_list())

    fig, axes = plt.subplots(
        len(loop_diameters),
        len(loop_lengths),
        figsize=(3.2 * len(loop_lengths), 3.2 * len(loop_diameters)),
        sharex=True,
        sharey=True,
    )
    axes = np.atleast_2d(axes)

    for row_idx, loop_diameter in enumerate(loop_diameters):
        for col_idx, loop_length in enumerate(loop_lengths):
            ax = axes[row_idx, col_idx]
            sub = successful.filter(
                (pl.col("loop_length_m") - loop_length).abs() < 1e-6,
            ).filter(
                (pl.col("loop_diameter_m") - loop_diameter).abs() < 1e-6,
            )
            meets = sub.filter(pl.col("net_electric_power_kW") > MIN_NET_ELECTRIC_POWER_KW)
            misses = sub.filter(pl.col("net_electric_power_kW") <= MIN_NET_ELECTRIC_POWER_KW)

            ax.scatter(
                misses["mass_flow_kg_s"],
                misses["well_depth_m"],
                marker="x",
                color="tab:red",
                s=35,
            )
            ax.scatter(
                meets["mass_flow_kg_s"],
                meets["well_depth_m"],
                marker="o",
                color="tab:green",
                s=35,
            )
            ax.set_xscale("log")
            if row_idx == 0:
                ax.set_title(f"Loop length\n{loop_length:.0f} m", fontsize=9)
            if col_idx == 0:
                ax.set_ylabel(f"Diameter {loop_diameter:.3g} m\n\nWell depth [m]", fontsize=9)
            if row_idx == len(loop_diameters) - 1:
                ax.set_xlabel("Mass flow [kg/s]", fontsize=9)

    # Figure-level legend outside the axes grid, not inside a data panel —
    # every panel here has real data in its corners (unlike smaller grids),
    # so there's no empty spot to tuck an in-axes legend into without
    # covering points.
    handles = [
        plt.Line2D(
            [],
            [],
            marker="x",
            color="tab:red",
            linestyle="",
            label="net consumer (or 0)",
        ),
        plt.Line2D(
            [],
            [],
            marker="o",
            color="tab:green",
            linestyle="",
            label="net electricity producer",
        ),
    ]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 1.0), ncol=2, fontsize=9)
    fig.suptitle(
        "Designs that are net electricity producers (net_electric_power_kW > 0)",
        y=1.04,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_lcoe_grid(df: pl.DataFrame, out_path: Path, color_col: str = "LCOE_USD_per_kWh") -> None:
    """Grid of scatter subplots (rows = loop diameter, columns = loop length):
    mass flow vs. well depth — same layout as plot_success_scatter, with two
    independent encodings layered together:
      - marker shape: circle if net_electric_power_kW > MIN_NET_ELECTRIC_POWER_KW,
        x otherwise (same qualification/shape convention as
        plot_success_scatter, so the two plots read consistently side by
        side).
      - marker color: `color_col` (default LCOE), so the cost gradient is
        visible within each shape group. Designs with `color_col` null (see
        sweep.py's LCOE-nulling comment) are colored flat grey instead of
        being colormapped — in practice these are always misses (x), never
        designs that also clear the net-electric-power qualification.

    Color scale is shared across all panels (computed once, globally) so
    designs in different panels are directly comparable, normalized against
    the 5th-95th percentile for the same reason as plot_parallel_coordinates.
    """
    successful = df.filter(pl.col("error").is_null())
    loop_lengths = sorted(successful.select("loop_length_m").unique().to_series().to_list())
    loop_diameters = sorted(successful.select("loop_diameter_m").unique().to_series().to_list())

    all_values = successful[color_col].to_numpy()
    cmap = plt.get_cmap("viridis_r")  # reversed: low LCOE (good) = bright/yellow
    c_min, c_max = np.nanpercentile(all_values, [5, 95])
    if c_max <= c_min:
        c_min, c_max = np.nanmin(all_values), np.nanmax(all_values)
    norm = plt.Normalize(vmin=c_min, vmax=c_max)

    fig, axes = plt.subplots(
        len(loop_diameters),
        len(loop_lengths),
        figsize=(3.2 * len(loop_lengths), 3.2 * len(loop_diameters)),
        sharex=True,
        sharey=True,
    )
    axes = np.atleast_2d(axes)

    n_undefined_total = 0
    for row_idx, loop_diameter in enumerate(loop_diameters):
        for col_idx, loop_length in enumerate(loop_lengths):
            ax = axes[row_idx, col_idx]
            sub = successful.filter(
                (pl.col("loop_length_m") - loop_length).abs() < 1e-6,
            ).filter(
                (pl.col("loop_diameter_m") - loop_diameter).abs() < 1e-6,
            )
            meets = sub.filter(pl.col("net_electric_power_kW") > MIN_NET_ELECTRIC_POWER_KW)
            misses = sub.filter(pl.col("net_electric_power_kW") <= MIN_NET_ELECTRIC_POWER_KW)
            misses_defined = misses.filter(pl.col(color_col).is_not_null())
            misses_undefined = misses.filter(pl.col(color_col).is_null())
            n_undefined_total += misses_undefined.height

            ax.scatter(
                misses_undefined["mass_flow_kg_s"],
                misses_undefined["well_depth_m"],
                marker="x",
                color="lightgrey",
                s=30,
                zorder=1,
            )
            ax.scatter(
                misses_defined["mass_flow_kg_s"],
                misses_defined["well_depth_m"],
                c=misses_defined[color_col],
                cmap=cmap,
                norm=norm,
                marker="x",
                s=30,
                zorder=2,
            )
            ax.scatter(
                meets["mass_flow_kg_s"],
                meets["well_depth_m"],
                c=meets[color_col],
                cmap=cmap,
                norm=norm,
                marker="o",
                s=40,
                edgecolors="black",
                linewidths=0.5,
                zorder=3,
            )
            ax.set_xscale("log")
            if row_idx == 0:
                ax.set_title(f"Loop length\n{loop_length:.0f} m", fontsize=9)
            if col_idx == 0:
                ax.set_ylabel(f"Diameter {loop_diameter:.3g} m\n\nWell depth [m]", fontsize=9)
            if row_idx == len(loop_diameters) - 1:
                ax.set_xlabel("Mass flow [kg/s]", fontsize=9)

    # No legend here: the marker shape/color encoding is fully spelled out in
    # the suptitle below, and a legend box in any corner panel covers real
    # data points (this grid has no empty corner to tuck it into).

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    cbar = fig.colorbar(sm, ax=axes, pad=0.015, extend="both", shrink=0.9)
    cbar.set_label(f"{_display_name(color_col)} (5th-95th pctile; outliers clipped)")

    fig.suptitle(
        f"{_display_name(color_col)} across all designs  "
        f"(o = net electricity producer, x = net consumer or 0; color = {_display_name(color_col)}, "
        f"grey = undefined n={n_undefined_total})",
        y=1.02,
    )
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_parallel_coordinates(df: pl.DataFrame, out_path: Path, color_col: str = "LCOE_USD_per_kWh") -> None:
    """Parallel-coordinates plot across all sweep inputs and key outputs.

    Each design is one line crossing all axes (min-max normalized per axis so
    columns with very different units/ranges are comparable); lines are
    colored by `color_col` (default LCOE) so the cost gradient across the
    whole design space is visible at a glance.

    Color is normalized against the 5th-95th percentile of `color_col`, not
    its min/max. A handful of marginal designs (barely clearing the ORC's
    own extraction requirements) have LCOE set to null by sweep.py: the
    native economic unit's Net_Electricity_Generated_kWe goes negative for
    them (parasitic pumping and/or generator load apparently consumes as
    much or more energy as the ORC plant delivers, in its own accounting)
    and CAPEX / negative-power is an undefined ratio, not merely a large one
    — see sweep.py's LCOE-nulling comment and the "known inconsistencies"
    pump-accounting note in docs/TANGO_vision_and_roadmap.md. Those lines
    are drawn in flat grey with reduced opacity instead of being
    colormapped, since they have no valid value for `color_col`; percentile
    clipping on the remaining valid values keeps the plot informative for
    the bulk of the design space instead of one or two extreme finite values
    (were they to occur) collapsing the gradient for everyone else.
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
    cmap = plt.get_cmap("viridis_r")  # reversed: low LCOE (good) = bright/yellow
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

    fig.suptitle("Triemli AGS power-generation sweep — all designs", y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_parallel_coordinates_interactive(
    df: pl.DataFrame,
    out_path: Path,
    color_col: str = "LCOE_USD_per_kWh",
    title: str | None = None,
) -> bool:
    """Interactive HTML version of plot_parallel_coordinates, using Plotly's
    Parcoords for real axis brushing (drag along an axis to filter the
    range shown) and hover tooltips — matplotlib has no equivalent.

    Requires the `dev` dependency group (plotly). Returns False (and prints
    a note instead of raising) if plotly isn't installed, so the rest of the
    plotting pipeline still runs for a base install.

    Unlike the static matplotlib version, designs with `color_col` null are
    excluded rather than drawn in a distinct color: Plotly's Parcoords line
    coloring has no equivalent of matplotlib's cmap.set_bad() for NaN, so
    there's no clean way to render them as visually distinct from a real
    value on this color scale. The exclusion count is reported in the title
    instead of silently dropping them.
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
                # Not reversed (unlike the static plots' viridis_r): most
                # designs have low/good LCOE, so plain Viridis puts them at
                # the dark purple/blue end instead of pale yellow — much
                # better contrast against a light background than the
                # majority of lines being barely-visible pale yellow.
                "colorscale": "Viridis",
                "cmin": c_min,
                "cmax": c_max,
                "showscale": True,
                "colorbar": {"title": f"{_display_name(color_col)}\n(5-95 pctile)"},
            },
            # Default unselected-line dimming is subtle enough that a
            # dragged filter barely stands out, especially at the pale-yellow
            # (low/good LCOE) end of the colorscale against a white
            # background. Push it much further: near-invisible light grey.
            unselected={"line": {"color": "lightgrey", "opacity": 0.05}},
            dimensions=dimensions,
        ),
    )
    if title is None:
        title = (
            "Triemli AGS power-generation sweep — all designs (interactive: drag along an axis "
            f"to filter; {n_undefined} designs with {_display_name(color_col)} undefined excluded)"
        )
    fig.update_layout(
        title=title,
        # Plain white washes out pale colorscale values (e.g. low/good LCOE,
        # which is bright yellow on Viridis_r); a light grey backdrop gives
        # every line, selected or not, more contrast to sit against.
        paper_bgcolor="#e8e8e8",
        plot_bgcolor="#e8e8e8",
    )
    fig.write_html(out_path)
    return True


def plot_parallel_coordinates_interactive_qualified(
    df: pl.DataFrame,
    out_path: Path,
    color_col: str = "LCOE_USD_per_kWh",
) -> bool:
    """Same as plot_parallel_coordinates_interactive, but restricted to designs
    that are net electricity producers (net_electric_power_kW >
    MIN_NET_ELECTRIC_POWER_KW).

    Unlike the sibling direct-heat sweep's qualified plot (which additionally
    requires a minimum thermal power on top of its temperature threshold),
    this sweep uses a single qualification criterion — positive net electric
    power — rather than adding a second minimum-power floor. Judgment call:
    there's no principled "typical minimum viable ORC unit" size to anchor a
    second threshold on the way the direct-heat sweep's 2 MW floor was
    anchored to a round number; adding one here would just be picking an
    arbitrary number and calling it a MW-scale floor. If a real minimum ORC
    unit size becomes relevant later, add it back as a second filter with an
    explicit citation for the floor value, rather than guessing one now.

    Filtering first (rather than plotting everything and asking the viewer to
    drag filters by hand) also tightens the color scale: the 5th-95th
    percentile is computed only over the filtered designs instead of the
    full sweep, so the colorbar actually resolves the LCOE spread among the
    designs that matter instead of being dominated by the much wider range
    across the full sweep.
    """
    qualified = df.filter(pl.col("net_electric_power_kW") > MIN_NET_ELECTRIC_POWER_KW)
    n_qualified = qualified.filter(pl.col("error").is_null()).height
    title = (
        "Triemli AGS power-generation sweep — designs that are net electricity "
        f"producers only (n={n_qualified}); interactive: drag along an axis to filter"
    )
    return plot_parallel_coordinates_interactive(qualified, out_path, color_col=color_col, title=title)


def main(quiet: bool = False, sweep_dir: Path | None = None) -> None:
    """Load results.parquet and write the scatter + parallel-coordinates plots."""
    sweep_dir = sweep_dir or DEFAULT_SWEEP_DIR
    results_parquet = sweep_dir / "results.parquet"
    df = pl.read_parquet(results_parquet)

    scatter_path = sweep_dir / "success_scatter.png"
    lcoe_grid_path = sweep_dir / "lcoe_grid.png"
    parcoord_path = sweep_dir / "parallel_coordinates.png"
    parcoord_html_path = sweep_dir / "parallel_coordinates.html"
    parcoord_qualified_html_path = sweep_dir / "parallel_coordinates_qualified.html"

    plot_success_scatter(df, scatter_path)
    plot_lcoe_grid(df, lcoe_grid_path)
    plot_parallel_coordinates(df, parcoord_path)
    wrote_html = plot_parallel_coordinates_interactive(df, parcoord_html_path)
    wrote_qualified_html = plot_parallel_coordinates_interactive_qualified(df, parcoord_qualified_html_path)

    if not quiet:
        print(f"Wrote {scatter_path}")
        print(f"Wrote {lcoe_grid_path}")
        print(f"Wrote {parcoord_path}")
        if wrote_html:
            print(f"Wrote {parcoord_html_path}")
        if wrote_qualified_html:
            print(f"Wrote {parcoord_qualified_html_path}")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Generate scatter and parallel-coordinates plots for the Triemli sweep",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--quiet", "-q", action="store_true")
    parser.add_argument("--sweep-dir", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(quiet=args.quiet, sweep_dir=args.sweep_dir)
