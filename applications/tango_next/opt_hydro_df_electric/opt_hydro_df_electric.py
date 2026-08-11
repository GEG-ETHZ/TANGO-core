"""Multi-objective optimization demo for the double-flash hydrothermal example.

Runs the manual-flow-rate baseline once, then searches mass flow rate +
injection wellhead pressure with NSGA2 to minimize LCOE and maximize mean
net electric power (``tango_next.pymoo_api.Minimization``), saving the
pareto results/configs and parallel-coordinates plots.

Usage: uv run python applications/tango_next/opt_hydro_df_electric/opt_hydro_df_electric.py
"""

from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pymoo.core.result import Result

from tango_next.pymoo_api import (
    Minimization,
    PymooConfig,
    injection_pressure_param,
    lcoe_objective,
    mass_rate_param,
    negative_mean_power_objective,
)
from tango_next.utils import print_dt
from tango_next.workflows.workflow import Workflow

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
# hydro_df_electric.yml lives one level up (examples/tango_next/) — it's
# shared with applications/tango_next/run_hydro_df_electric_sweep/ (the DVC
# sweep pipeline) and tests/regtest/test_old_new_economic_parity.py, both of
# which expect it directly under examples/tango_next/, not nested under
# this script's own subdirectory.
CONFIG_DIR = HERE.parents[2] / "examples/tango_next/"
DEFAULT_OUTPUT_DIR = HERE / "outputs"

# Hyperparameter defaults for --help text and argparse defaults come from
# this single instance, not hardcoded numbers repeated in the parser — so
# "the default" always means PymooConfig's own default, one source of truth.
_DEFAULT_PYMOO_CONFIG = PymooConfig()


def build_parser() -> argparse.ArgumentParser:
    """CLI for tuning the pymoo search — modeled loosely on
    ``fastsim.pymoo_api.get_parser()``, adapted to tango_next's
    ``PymooConfig`` fields (not copied 1:1 — fastsim's script externalizes
    its own ``multiprocessing.Pool``/``StarmapParallelization`` wiring into
    the calling script and threads a `--skip-minimize` flag through a
    previous-results cache; neither exists here: ``Minimization`` already
    manages its own worker pool internally via ``PymooConfig.n_processes``,
    and there's no cached-results-loading feature to expose a flag for).
    """
    parser = argparse.ArgumentParser(
        description="Multi-objective optimization demo for the double-flash hydrothermal example.",
    )
    parser.add_argument(
        "--n-max-gen",
        type=int,
        default=_DEFAULT_PYMOO_CONFIG.n_max_gen,
        help=f"Max generations (hard cap). Defaults to {_DEFAULT_PYMOO_CONFIG.n_max_gen}.",
    )
    parser.add_argument(
        "--pop-size",
        type=int,
        default=_DEFAULT_PYMOO_CONFIG.pop_size,
        help=f"Population size per generation. Defaults to {_DEFAULT_PYMOO_CONFIG.pop_size}.",
    )
    parser.add_argument(
        "--ftol",
        type=float,
        default=_DEFAULT_PYMOO_CONFIG.ftol,
        help=f"Objective-space convergence tolerance. Defaults to {_DEFAULT_PYMOO_CONFIG.ftol}.",
    )
    parser.add_argument(
        "--xtol",
        type=float,
        default=_DEFAULT_PYMOO_CONFIG.xtol,
        help=f"Design-space convergence tolerance. Defaults to {_DEFAULT_PYMOO_CONFIG.xtol}.",
    )
    parser.add_argument(
        "-p",
        "--n-processes",
        type=int,
        default=_DEFAULT_PYMOO_CONFIG.n_processes,
        help=f"Worker processes for parallel evaluation (1 = serial). Defaults to {_DEFAULT_PYMOO_CONFIG.n_processes}.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=_DEFAULT_PYMOO_CONFIG.seed,
        help=f"Random seed for reproducibility. Defaults to {_DEFAULT_PYMOO_CONFIG.seed}. Ignored if --no-seed is given.",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Pass seed=None instead (non-reproducible run) — overrides --seed.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print pymoo's per-generation progress table.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help=(
            "Python logging level for tango_next's own loggers (workflow "
            "loading, per-timestep orchestrator state) — independent of "
            "--verbose, which only controls pymoo's own progress table. "
            "Defaults to WARNING. INFO/DEBUG print on EVERY evaluation "
            "across the whole run, not just once."
        ),
    )
    parser.add_argument(
        "--save-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Where to write results/plots. Defaults to {DEFAULT_OUTPUT_DIR}.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help=(
            "Delete --save-dir entirely before running. Without this, a run "
            "producing FEWER pareto designs than a previous run leaves the "
            "previous run's extra pareto_configs/design_NNN.yml files behind "
            "(Minimization._save() only overwrites indices that exist in the "
            "CURRENT result, it doesn't clear stale ones) — easy to mistake "
            "for part of the current result."
        ),
    )
    parser.add_argument(
        "--seed-from",
        type=Path,
        default=None,
        help=(
            "Path to a previous run's pareto_results.csv (or "
            "pareto_results_partial.csv from an interrupted run) to "
            "warm-start the initial population from, instead of pymoo's "
            "default random/LHS init. NOT a true resume (fresh RNG state, "
            "restarts at generation 1) -- see Minimization's seed_from "
            "docstring for the full tradeoff. Remaining population slots "
            "beyond what the file provides are filled via LHS."
        ),
    )
    return parser


def build_baseline() -> tuple[Workflow, Workflow]:
    """Build the unrun template workflow and a separately-run manual baseline.

    Returns:
        ``(wf, wf_manual)`` — ``wf`` is UNRUN and must stay that way (see
        ``run_optimization``'s docstring for why); ``wf_manual`` is a
        SEPARATE, already-``run()`` copy used only to report the baseline
        LCOE for comparison.

    """
    wf = Workflow.from_file(CONFIG_DIR / "hydro_df_electric.yml")
    # Workflow(wf.to_dict()), NOT copy.copy(wf) or copy.deepcopy(wf):
    #
    # - copy.copy() only duplicates Workflow's own __dict__, leaving both
    #   copies pointing at the SAME orchestrator/components, so running
    #   wf_manual would silently corrupt wf's state too.
    # - copy.deepcopy() looks safer but is ALSO wrong, in a way that only
    #   shows up once you actually run() the copy: GraphSurface builds a live
    #   TESPy Network/Connection object graph once in init() and stores it as
    #   private (non-Pydantic) attributes, specifically excluded from
    #   model_dump() (see that class's docstring — "on restore, call init()
    #   again to rebuild the network"). Verified empirically: deepcopy-ing an
    #   already-init()'d Workflow and then .run()-ing the copy raises
    #   TESPyNetworkError ("missing fluid composition information") — TESPy's
    #   own object graph doesn't survive a generic deepcopy correctly.
    # - Workflow(wf.to_dict()) is the pattern the class's own docstring already
    #   documents for exactly this need (independent copies for a sweep) — it
    #   round-trips through the validated config instead of copying live
    #   objects, so every component's init() genuinely reruns from scratch.
    #
    # Keeping wf itself UNRUN (only wf_manual is .run()) matters beyond just
    # avoiding a mutation footgun: Minimization builds every evaluation's
    # config from wf.to_dict(), which includes each component's full state/
    # history. If wf had already been run, every fresh Workflow(cfg) built
    # from that config would start pre-populated with the baseline's own
    # 20-timestep history — its own run() would then APPEND to that instead of
    # starting empty, silently corrupting every history-derived objective
    # (e.g. negative_mean_power_objective, which averages history.net_power_W)
    # with pre-existing baseline timesteps mixed into the mean.
    wf_manual = Workflow(wf.to_dict())
    wf_manual.run()
    return wf, wf_manual


def run_optimization(base_wf: Workflow, args: argparse.Namespace) -> tuple[Result, pd.DataFrame]:
    """Search mass flow rate + injection pressure to minimize LCOE / maximize mean power.

    Args:
        base_wf: UNRUN template workflow — see ``build_baseline``'s docstring
            for why it must not have been ``run()`` yet.
        args: Parsed CLI args from ``build_parser()``.

    """
    m = Minimization(
        base_workflow=base_wf,
        params=[
            mass_rate_param(bounds=(10.0, 100.0)),
            injection_pressure_param(bounds=(1.0e6, 8.0e6)),
        ],
        objectives=[lcoe_objective(), negative_mean_power_objective()],
        pymoo_config=PymooConfig(
            n_max_gen=args.n_max_gen,
            pop_size=args.pop_size,
            ftol=args.ftol,
            xtol=args.xtol,
            n_processes=args.n_processes,
            seed=None if args.no_seed else args.seed,
        ),
        verbose=args.verbose,
        save_dir=args.save_dir,
    )
    return m.run()


def plot_pareto_parallel_coordinates(df: pd.DataFrame, out_path: Path, color_col: str = "euclidean") -> None:
    """Static parallel-coordinates plot across every pareto-front design.

    Same construction as ``applications/run_AGS_sweep/plot.py``'s
    ``plot_parallel_coordinates`` (min-max normalized axes, viridis_r
    colormap clipped to the 5th-95th percentile of ``color_col``), adapted
    to a small pandas pareto-front dataframe rather than a large polars
    sweep-grid dataframe — every design here is feasible by construction
    (``Minimization`` only returns the pareto front, which by definition
    excludes constraint-violating designs), so there's no "undefined color"
    case to handle the way that sweep-grid plot does.

    Prepends a ``design_number`` axis on the far left (0-based, matching
    ``pareto_configs/design_NNN.yml``'s numbering) so a line can be traced
    back to its saved config — operates on a COPY, doesn't mutate the
    caller's ``df``.
    """
    df = df.copy()
    df.insert(0, "design_number", range(len(df)))
    cols = list(df.columns)
    data = df[cols].to_numpy(dtype=float)
    mins = data.min(axis=0)
    maxs = data.max(axis=0)
    span = np.where(maxs > mins, maxs - mins, 1.0)
    normalized = (data - mins) / span

    color_values = df[color_col].to_numpy(dtype=float)
    cmap = plt.get_cmap("viridis_r")  # reversed: low value (good) = bright/yellow
    c_min, c_max = np.percentile(color_values, [5, 95])
    if c_max <= c_min:
        c_min, c_max = float(color_values.min()), float(color_values.max())
    c_span = c_max - c_min if c_max > c_min else 1.0
    clipped = np.clip(color_values, c_min, c_max)

    fig, ax = plt.subplots(figsize=(1.8 * len(cols), 6.5))
    x = np.arange(len(cols))
    for row, color_value in zip(normalized, clipped, strict=True):
        color = cmap((color_value - c_min) / c_span)
        ax.plot(x, row, color=color, alpha=0.5, linewidth=1.0)

    for i, (col_min, col_max, label) in enumerate(zip(mins, maxs, cols, strict=True)):
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
        ax.text(i, -0.15, label, ha="center", va="top", fontsize=9, transform=ax.get_xaxis_transform())

    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlim(-0.2, len(cols) - 0.8)
    ax.set_ylim(-0.28, 1.14)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=c_min, vmax=c_max))
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, extend="both")
    cbar.set_label(f"{color_col} (5th-95th pctile; outliers clipped)")

    fig.suptitle("hydro_df_electric — pareto front (mass flow rate x injection pressure)", y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_pareto_scatter(df: pd.DataFrame, out_path: Path) -> None:
    """2D scatter of the two objectives (LCOE vs. mean net power), each point
    labeled by its design number.

    With exactly two objectives, this is a more direct view of the actual
    tradeoff curve than the parallel-coordinates plot -- every point on
    this plot IS a point on the pareto front, in objective space, no
    normalization or projection involved. Labels match
    pareto_configs/design_NNN.yml's numbering: df's row order comes
    straight from pymoo's res.X/res.F with no reordering in between, and
    Minimization._write_pareto() writes design files in that same order.
    """
    power_mw = df["mean_power_W"] / 1.0e6
    lcoe = df["LCOE"]

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(lcoe, power_mw, s=40, color="tab:blue", zorder=3)
    for i, (x, y) in enumerate(zip(lcoe, power_mw, strict=True)):
        ax.annotate(str(i), (x, y), textcoords="offset points", xytext=(5, 5), fontsize=8)

    ax.set_xlabel("LCOE ($/kWh)")
    ax.set_ylabel("Mean net power (MW)")
    ax.set_title("hydro_df_electric — pareto front (objective space, labeled by design number)")
    ax.grid(visible=True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_pareto_scatter_zscore(df: pd.DataFrame, out_path: Path) -> None:
    """Z-score-normalized variant of ``plot_pareto_scatter``.

    Both axes standardized (``(x - mean) / std``) instead of raw units, so
    the visual spread of each objective reflects its RELATIVE variation
    across the front, not whatever units it happens to be measured in —
    LCOE (~0.2-0.4) and mean power (~3-3.7 MW) look very differently
    "spread out" in raw units purely because of arbitrary unit choice;
    z-score removes that distortion. Same normalization
    ``pymoo_api.Minimization``'s ``euclidean`` column already uses.
    Zero-lines mark the mean of each objective across the front.
    """
    lcoe = df["LCOE"]
    power = df["mean_power_W"]
    lcoe_z = (lcoe - lcoe.mean()) / (lcoe.std() or 1.0)
    power_z = (power - power.mean()) / (power.std() or 1.0)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.axhline(0, color="grey", linewidth=0.8, zorder=1)
    ax.axvline(0, color="grey", linewidth=0.8, zorder=1)
    ax.scatter(lcoe_z, power_z, s=40, color="tab:orange", zorder=3)
    for i, (x, y) in enumerate(zip(lcoe_z, power_z, strict=True)):
        ax.annotate(str(i), (x, y), textcoords="offset points", xytext=(5, 5), fontsize=8)

    ax.set_xlabel("LCOE (z-score)")
    ax.set_ylabel("Mean net power (z-score)")
    ax.set_title("hydro_df_electric — pareto front (z-score-normalized objective space)")
    ax.grid(visible=True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_pareto_parallel_coordinates_interactive(
    df: pd.DataFrame,
    out_path: Path,
    color_col: str = "euclidean",
) -> bool:
    """Interactive HTML version of ``plot_pareto_parallel_coordinates`` (Plotly Parcoords).

    Requires the ``dev`` dependency group (plotly). Returns ``False`` (and
    prints a note instead of raising) if plotly isn't installed, so the
    rest of the pipeline still runs for a base install — same fallback
    ``applications/run_AGS_sweep/plot.py`` uses.

    Prepends a ``design_number`` axis on the far left (0-based, matching
    ``pareto_configs/design_NNN.yml``'s numbering) so a line can be traced
    back to its saved config — operates on a COPY, doesn't mutate the
    caller's ``df``.
    """
    try:
        import plotly.graph_objects as go  # noqa: PLC0415
    except ImportError:
        print(f"plotly not installed — skipping {out_path.name} (install with `uv sync --group dev`)")
        return False

    df = df.copy()
    df.insert(0, "design_number", range(len(df)))
    cols = list(df.columns)
    color_values = df[color_col].to_numpy(dtype=float)
    c_min, c_max = np.percentile(color_values, [5, 95])
    if c_max <= c_min:
        c_min, c_max = float(color_values.min()), float(color_values.max())

    # Explicit tickformat: Plotly's default tick formatter emits scientific
    # notation as literal "<sup>...</sup>" text for large numbers (e.g. the
    # ~1e15 J energy values here) — Parcoords tick labels are plain SVG text,
    # not HTML, so those tags render as garbage instead of superscripts.
    # "~s" is d3-format's SI-prefix style (1.3G, 823k, ...) — human-readable
    # and never emits markup, regardless of magnitude.
    dimensions: list[dict[str, Any]] = [
        {"label": c, "values": df[c].to_numpy(), "tickformat": "~s"} for c in cols
    ]
    fig = go.Figure(
        data=go.Parcoords(
            line={
                "color": color_values,
                "colorscale": "Viridis",
                "cmin": c_min,
                "cmax": c_max,
                "showscale": True,
                "colorbar": {"title": f"{color_col} (5-95 pctile)"},
            },
            dimensions=dimensions,
        ),
    )
    fig.update_layout(
        title="hydro_df_electric — pareto front (interactive: drag along an axis to filter)",
        paper_bgcolor="#e8e8e8",
        plot_bgcolor="#e8e8e8",
    )
    fig.write_html(out_path)
    return True


def main(args: argparse.Namespace) -> None:
    """Run the baseline, optimize, and write results/plots.

    Nothing in this module runs any workflow (or does anything expensive)
    until THIS is called with already-parsed args — ``--help`` exits via
    ``argparse`` before ``main`` is ever reached, and building/running the
    baseline workflow happens here, not at import time.
    """
    # Script-entry timestamp — deliberately the very first thing that
    # happens, before the baseline workflow (~100s+) or anything else runs.
    # ``Minimization.run()`` prints its OWN print_dt() too, but that one
    # fires only once the NSGA2 search itself starts, well after this —
    # for log-scraping purposes (e.g. SLURM job output, where queue wait
    # time isn't otherwise visible) you want the earliest possible mark of
    # when the script actually started doing anything, not just when the
    # optimization phase specifically began.
    print("opt_hydro_df_electric.py starting at")
    print_dt()
    # --verbose controls pymoo's OWN per-generation progress table (printed
    # directly by pymoo/Minimization, not via `logging` at all) — kept
    # separate from Python's logging level (--log-level) on purpose:
    # tying them together would flood the console with every module's
    # INFO logs (workflow loading, per-timestep orchestrator state) on
    # EVERY evaluation across an entire NSGA2 run (hundreds to thousands
    # of them), which is not what --verbose is for.
    logging.basicConfig(level=args.log_level)
    if args.clean and args.save_dir.exists():
        shutil.rmtree(args.save_dir)
    args.save_dir.mkdir(parents=True, exist_ok=True)

    wf, wf_manual = build_baseline()
    baseline_lcoe = wf_manual.to_dict()["economic"]["state"]["LCOE"]
    print(f"Baseline (manual flow rate): LCOE={baseline_lcoe:.4f} $/kWh")

    _res, df = run_optimization(wf, args)
    print(f"Pareto front: {len(df)} designs")
    print(df)

    # pymoo minimizes negative_mean_power_W (so maximizing power fits the
    # minimization framework) — that's the right column for the CSV/raw
    # results (matches the actual objective), but a human reading the PLOT
    # cares about mean power PRODUCED, not the sign flip needed to optimize
    # it. Flip only for the two plots below; df/the CSV keep the objective's
    # own sign.
    plot_df = df.rename(columns={"negative_mean_power_W": "mean_power_W"})
    plot_df["mean_power_W"] = -plot_df["mean_power_W"]

    plot_pareto_parallel_coordinates(plot_df, args.save_dir / "pareto_parallel_coordinates.png")
    plot_pareto_parallel_coordinates_interactive(plot_df, args.save_dir / "pareto_parallel_coordinates.html")
    plot_pareto_scatter(plot_df, args.save_dir / "pareto_scatter.png")
    plot_pareto_scatter_zscore(plot_df, args.save_dir / "pareto_scatter_zscore.png")


if __name__ == "__main__":
    main(build_parser().parse_args())
