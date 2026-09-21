"""Multi-objective optimization demo for the flexible Single-Flash hydrothermal example.

Runs the manual-flow-rate baseline once, then searches mass flow rate,
injection wellhead pressure, and target extraction pressure with NSGA2 to
minimize LCOE and maximize mean net electric power
(``tango.pymoo_api.Minimization``), saving the pareto results/configs
and parallel-coordinates plots.

The ``*_param``/``*_objective`` factories below are defined LOCALLY in this
script, not imported from ``pymoo_api.py`` — that module is deliberately
generic (see its ``ParamSpec``/``ObjectiveSpec`` docstrings) and must not
assume every future system looks like this one. A coupled reservoir model
with its own inlet/outlet mass-flow mismatch, for instance, won't have a
single constant global mass flow rate the way this DOUBLET topology does —
so ``mass_rate_param`` belongs here, scoped to what THIS system actually
needs, not baked into the shared API as if it applied universally. (Same
definitions as ``opt_hydro_df_electric.py``'s — duplicated deliberately,
not shared, since both scripts happen to need the same ones for now; that
overlap isn't evidence they belong in ``pymoo_api.py`` instead.)

Usage: ``dvc repro`` from this directory (or ``sbatch
opt_hydro_sf_electric_job.sh`` on Euler) — runs both the ``optimize`` and
``plot`` stages in ``dvc.yaml`` under DVC's dependency/output tracking.
Running this script directly with ``uv run python
opt_hydro_sf_electric.py`` also works but bypasses that tracking, so its
outputs won't be reflected in ``dvc.lock``.
"""

from __future__ import annotations

import argparse
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pymoo.core.result import Result

from tango.pymoo_api import (
    Minimization,
    ObjectiveSpec,
    ParamSpec,
    PymooConfig,
    build_pymoo_parser,
    load_params,
    plot_objective_vs_param_scatter,
    plot_param_pair_vs_objective_scatter,
    prepare_plot_df,
    strip_column_prefixes,
)
from tango.utils import print_dt
from tango.workflows.workflow import Workflow

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
# hydro_sf_electric.yml lives one level up (example_configs/) — it's
# shared with this script's own sibling demo
# (applications/demo_hydro_sf_electric/), which expects it directly
# under example_configs/, not nested under this script's own
# subdirectory. Unlike hydro_df_electric, there is no
# run_hydro_sf_electric_sweep/ DVC pipeline (yet).
CONFIG_DIR = HERE.parents[1] / "example_configs/"
DEFAULT_OUTPUT_DIR = HERE / "outputs"
PARAMS_FILE = HERE / "params.yaml"


# ---------------------------------------------------------------------------
# Local ParamSpec/ObjectiveSpec factories — specific to this system, not in
# pymoo_api.py (see this module's own docstring, and pymoo_api.py's
# ParamSpec/ObjectiveSpec docstrings, for why).
# ---------------------------------------------------------------------------


@dataclass
class _MassRateApply:
    """Picklable ``ParamSpec.apply`` for ``mass_rate_param``.

    A LOCAL closure (``def apply(...): ...`` nested inside a factory
    function) can't be pickled — ``pickle``/``multiprocessing`` serialize
    callables by module + qualified name and can't re-import a
    runtime-only local closure. That only breaks in the ``n_processes > 1``
    path (``multiprocessing.Pool.starmap`` requires every argument,
    including this callable, to pickle). A module-level dataclass with
    ``__call__`` pickles fine (by class reference + simple field values),
    so every factory below uses this pattern instead of a closure.
    """

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        cfg["sim_config"]["mass_rate"] = float(value)
        return cfg


def mass_rate_param(bounds: tuple[float, float]) -> ParamSpec:
    """Mass flow rate (``sim_config.mass_rate``, kg/s) as a decision variable."""
    return ParamSpec(name="mass_rate_kg_per_s", apply=_MassRateApply(), bounds=bounds)


@dataclass
class _InjectionPressureApply:
    """Picklable ``ParamSpec.apply`` for ``injection_pressure_param`` — see ``_MassRateApply``."""

    surface_name: str = "surface"

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        cfg["components"][self.surface_name]["injection_pressure"] = float(value)
        return cfg


def injection_pressure_param(bounds: tuple[float, float], surface_name: str = "surface") -> ParamSpec:
    """Injection wellhead pressure (``components.<surface_name>.injection_pressure``, Pa)."""
    return ParamSpec(name="injection_pressure_Pa", apply=_InjectionPressureApply(surface_name), bounds=bounds)


@dataclass
class _TargetExtractionPressureApply:
    """Picklable ``ParamSpec.apply`` for ``target_extraction_pressure_param`` — see ``_MassRateApply``."""

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        cfg["sim_config"]["target_extraction_pressure"] = float(value)
        return cfg


def target_extraction_pressure_param(bounds: tuple[float, float]) -> ParamSpec:
    """Minimum required extraction pressure at the surface inlet
    (``sim_config.target_extraction_pressure``, Pa) — the SINGLE shared
    source threaded to every component declaring this field (surface,
    pump-bearing production wells; see ``Workflow``'s ``_LAYOUT_EXTRA_KEYS``
    docstring). Deliberately NOT ``components.<surface_name>.*`` — that was
    a pre-fix duplication bug this field's docstring warns about.
    """
    return ParamSpec(
        name="target_extraction_pressure_Pa",
        apply=_TargetExtractionPressureApply(),
        bounds=bounds,
    )


@dataclass
class _LcoeEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` for ``lcoe_objective`` — see ``_MassRateApply``."""

    def __call__(self, wf: Workflow) -> float:
        return float(wf.to_dict()["economic"]["state"]["LCOE"])


def lcoe_objective() -> ObjectiveSpec:
    """LCOE ($/kWh), from ``DoubletEconomicComponent`` — requires an ``economic:`` block."""
    return ObjectiveSpec(name="LCOE", evaluate=_LcoeEvaluate())


@dataclass
class _NegativeMeanPowerEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` for ``negative_mean_power_objective`` — see ``_MassRateApply``."""

    surface_name: str = "surface"

    def __call__(self, wf: Workflow) -> float:
        surface = wf._orchestrator.components[self.surface_name]  # noqa: SLF001
        history = getattr(surface, "history", None)
        net_power_w_history: list[float] = getattr(history, "net_power_W", [])
        mean_w = sum(net_power_w_history) / len(net_power_w_history) if net_power_w_history else 0.0
        return -mean_w


def negative_mean_power_objective(surface_name: str = "surface") -> ObjectiveSpec:
    """``-`` mean net electric power over the run (W) — minimizing this maximizes power.

    Mean, not total energy: a human reading the results has direct
    intuition for "1.3 MW average" but none for "1.1e15 J total" — and
    since every timestep has the SAME duration in tango today
    (``dt_years`` is a single scalar for the whole run), the mean of
    ``history.net_power_W`` and the time-integrated total energy differ
    only by that one shared, constant scale factor (``dt_years *
    YEAR_TO_SECOND``) — the mean carries exactly the same optimization
    signal, it's just a friendlier unit to look at.
    """
    return ObjectiveSpec(name="negative_mean_power_W", evaluate=_NegativeMeanPowerEvaluate(surface_name))


# Single source of truth for the "negate for a human-friendly plot/print label"
# rename applied in main() — keyed off negative_mean_power_objective()'s own
# ``.name`` rather than a second, independently-typed copy of that string, so
# a future rename of the objective itself can't silently desync from this.
DISPLAY_RENAME = {negative_mean_power_objective().name: "mean_power_W"}

# Full plot-axis display label for each column (parallel-coordinates plots)
# -- keyed on each column's DISPLAY name (post-DISPLAY_RENAME), not its
# raw/negated pymoo name. A full REPLACEMENT label, not a "name + [unit]"
# append -- several columns already carry their unit as a name suffix
# (mass_rate_kg_per_s, injection_pressure_Pa, ...), and appending "[unit]"
# on top of that reads as redundant ("mass_rate_kg_per_s [kg/s]");
# stripping the suffix into a clean bracketed unit instead
# ("mass_rate [kg/s]") avoids that. LCOE/euclidean have no such suffix at
# all, so their bracket is pure addition, not a strip+replace. Columns
# absent here (design_number) show unchanged -- it's an index, not a
# physical quantity. Also carries the SAME par:/obj: category prefix
# ``Minimization._column_rename`` writes to the CSV (Chad's call,
# 2026-09-07) -- euclidean stays bare here too, matching the CSV
# convention (neither a param nor an objective).
COLUMN_LABELS = {
    "mass_rate_kg_per_s": "par:mass_rate [kg/s]",
    "injection_pressure_Pa": "par:injection_pressure [Pa]",
    "target_extraction_pressure_Pa": "par:target_extraction_pressure [Pa]",
    "LCOE": "obj:LCOE [$/kWh]",
    "mean_power_W": "obj:mean_power [W]",
    "euclidean": "euclidean [z-score]",
}


def _pretty_label(label: str) -> str:
    """``"mass_rate [kg/s]"`` if ``label`` has a known display form (see ``COLUMN_LABELS``), else unchanged."""
    return COLUMN_LABELS.get(label, label)


def build_parser() -> argparse.ArgumentParser:
    """CLI for tuning the pymoo search — thin wrapper around
    ``pymoo_api.build_pymoo_parser``, the shared, non-domain-specific half
    (see its own docstring for why this lives in ``pymoo_api.py`` while
    ``ParamSpec``/``ObjectiveSpec`` do not).
    """
    return build_pymoo_parser(
        description="Multi-objective optimization demo for the flexible Single-Flash hydrothermal example.",
        default_output_dir=DEFAULT_OUTPUT_DIR,
        params=load_params(PARAMS_FILE),
    )


def build_baseline() -> tuple[Workflow, Workflow]:
    """Build the unrun template workflow and a separately-run manual baseline.

    Returns:
        ``(wf, wf_manual)`` — ``wf`` is UNRUN and must stay that way (see
        ``run_optimization``'s docstring for why); ``wf_manual`` is a
        SEPARATE, already-``run()`` copy used only to report the baseline
        LCOE for comparison.

    """
    wf = Workflow.from_file(CONFIG_DIR / "hydro_sf_electric.yml")
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


def _param_specs() -> list[ParamSpec]:
    """Decision variables: mass flow rate, injection pressure, target
    extraction pressure.

    Extracted as its own function (rather than inlined in
    ``run_optimization``) so the DVC ``plot`` stage can recover each
    column's ``.name`` for plot axis labels without needing a
    ``Minimization`` instance or rerunning any simulation — see ``main``'s
    ``--plot-only`` path.
    """
    return [
        mass_rate_param(bounds=(10.0, 100.0)),
        injection_pressure_param(bounds=(1.0e6, 8.0e6)),
        # (0.7, 1.5)x the base YAML's 7.0 MPa — same scale factor used for
        # this field in run_hydro_df_electric_sweep/common.py's LHS sweep
        # bounds. hydro_sf_electric.yml shares the identical base value
        # (target_extraction_pressure: 7_000_000) and well/reservoir
        # topology (only the surface plant differs, SF vs. DF), so the
        # same bounds apply directly rather than being a fresh guess.
        target_extraction_pressure_param(bounds=(4.9e6, 10.5e6)),
    ]


def _objective_specs() -> list[ObjectiveSpec]:
    """Objectives: minimize LCOE, maximize mean net power — see
    ``_param_specs``' docstring for why this is its own function.
    """
    return [lcoe_objective(), negative_mean_power_objective()]


def run_optimization(
    base_wf: Workflow,
    args: argparse.Namespace,
) -> tuple[Result, pd.DataFrame, Minimization]:
    """Search mass flow rate + injection pressure + target extraction pressure
    to minimize LCOE / maximize mean power.

    Args:
        base_wf: UNRUN template workflow — see ``build_baseline``'s docstring
            for why it must not have been ``run()`` yet.
        args: Parsed CLI args from ``build_parser()``.

    Returns:
        ``(res, df, m)`` — ``m`` (the ``Minimization`` instance) is returned
        alongside ``res``/``df`` so callers can read ``m.params``/
        ``m.objectives`` for their own ``.name`` values (e.g. for plot axis
        labels) instead of re-typing those same strings a second time.

    """
    m = Minimization(
        base_workflow=base_wf,
        params=_param_specs(),
        objectives=_objective_specs(),
        pymoo_config=PymooConfig(
            n_max_gen=args.n_max_gen,
            pop_size=args.pop_size,
            ftol=args.ftol,
            xtol=args.xtol,
            termination_period=args.termination_period,
            n_processes=args.n_processes,
            seed=None if args.no_seed else args.seed,
            crossover_prob=args.crossover_prob,
            mutation_prob=args.mutation_prob,
        ),
        verbose=not args.quiet,
        save_dir=args.save_dir,
    )
    res, df = m.run()
    return res, df, m


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
        ax.text(
            i,
            -0.15,
            _pretty_label(label),
            ha="right",
            va="top",
            fontsize=8,
            rotation=30,
            rotation_mode="anchor",
            transform=ax.get_xaxis_transform(),
        )

    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlim(-0.2, len(cols) - 0.8)
    ax.set_ylim(-0.45, 1.14)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=c_min, vmax=c_max))
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, extend="both")
    cbar.set_label(f"{color_col} (5th-95th pctile; outliers clipped)")

    fig.suptitle("hydro_sf_electric — pareto front (mass flow rate x injection pressure)", y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _diagonal_label_offset(x: pd.Series, y: pd.Series) -> tuple[tuple[float, float], str]:
    """Pick a point-label offset perpendicular to the data's dominant diagonal.

    A pareto front's points lie roughly along a diagonal; offsetting labels
    along THAT diagonal drives them into the next point, while offsetting
    across it clears neighbors. Which diagonal the front follows depends on
    the sign of the correlation between x and y (not r^2, which discards
    the sign): positive -> front runs bottom-left to upper-right -> offset
    upper-left. Negative -> front runs upper-left to bottom-right -> offset
    upper-right. Falls back to upper-left (this module's common case) if
    the correlation is undefined, e.g. a constant x or y.
    """
    with np.errstate(invalid="ignore"):
        r = np.corrcoef(x, y)[0, 1]
    if np.isnan(r) or r >= 0:
        return (-5, 5), "right"
    return (5, 5), "left"


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
    xytext, ha = _diagonal_label_offset(lcoe, power_mw)
    for i, (x, y) in enumerate(zip(lcoe, power_mw, strict=True)):
        ax.annotate(str(i), (x, y), textcoords="offset points", xytext=xytext, ha=ha, fontsize=8)

    ax.set_xlabel("LCOE ($/kWh)")
    ax.set_ylabel("Mean net power (MW)")
    ax.set_title("hydro_sf_electric — pareto front (objective space, labeled by design number)")
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
    xytext, ha = _diagonal_label_offset(lcoe_z, power_z)
    for i, (x, y) in enumerate(zip(lcoe_z, power_z, strict=True)):
        ax.annotate(str(i), (x, y), textcoords="offset points", xytext=xytext, ha=ha, fontsize=8)

    ax.set_xlabel("LCOE (z-score)")
    ax.set_ylabel("Mean net power (z-score)")
    ax.set_title("hydro_sf_electric — pareto front (z-score-normalized objective space)")
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
    # "~s" (d3-format's SI-prefix style: 1.3G, 823k, ...) fixes that and is
    # human-readable, but ONLY for magnitude >= 1 — d3 also applies NEGATIVE
    # SI prefixes (milli, micro, ...) below 1, so e.g. LCOE's 0.349157
    # renders as "349.157m", where that "m" means milli, not meters (and
    # collides badly with any already-"_m"-suffixed column, silently
    # misreading e.g. a 0.215 m design as 215 m). Columns with magnitude < 1
    # get plain fixed-point instead, with no prefix to misread.
    dimensions: list[dict[str, Any]] = [
        {
            "label": _pretty_label(c),
            "values": df[c].to_numpy(),
            "tickformat": "~s" if np.max(np.abs(df[c].to_numpy())) >= 1 else "~g",
        }
        for c in cols
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
        title="hydro_sf_electric — pareto front (interactive: drag along an axis to filter)",
        paper_bgcolor="#e8e8e8",
        plot_bgcolor="#e8e8e8",
        # Plotly's Parcoords has no axis-label-rotation option (unlike the
        # static matplotlib version's rotated labels) -- its default width
        # is a fixed ~700px regardless of dimension count, so unit-suffixed
        # labels like "target_extraction_pressure [Pa]" run into each
        # other once there are more than a few dimensions. Scaling width
        # by dimension count (same 1.8x-per-column idea as the static
        # plot's own figsize=(1.8 * len(cols), ...)), just in pixels,
        # gives each one enough room -- an HTML file has no fixed viewport
        # to fit, so a wide, scrollable/zoomable figure is fine.
        width=max(1200, 220 * len(cols)),
        height=700,
    )
    fig.write_html(out_path)
    return True


def make_plots(df: pd.DataFrame, save_dir: Path, param_cols: list[str], objective_cols: list[str]) -> None:
    """Build every plot from a pareto-front dataframe — the DVC ``plot`` stage's
    entire job, shared with the direct (non-``--plot-only``) code path.

    ``param_cols``/``objective_cols`` are passed in (derived from
    ``_param_specs``/``_objective_specs``) rather than read off a live
    ``Minimization`` instance, since ``--plot-only`` never builds one.
    """
    plot_df = prepare_plot_df(df, DISPLAY_RENAME)

    plot_pareto_parallel_coordinates(plot_df, save_dir / "pareto_parallel_coordinates.png")
    plot_pareto_parallel_coordinates_interactive(
        plot_df,
        save_dir / "pareto_parallel_coordinates.html",
    )
    plot_pareto_scatter(plot_df, save_dir / "pareto_scatter.png")
    plot_pareto_scatter_zscore(plot_df, save_dir / "pareto_scatter_zscore.png")
    plot_objective_vs_param_scatter(
        plot_df,
        param_cols=param_cols,
        objective_cols=objective_cols,
        out_path=save_dir / "pareto_scatter_by_param.png",
        title="hydro_sf_electric — objectives vs. parameters",
    )
    plot_param_pair_vs_objective_scatter(
        plot_df,
        param_cols=param_cols,
        objective_cols=objective_cols,
        out_path=save_dir / "pareto_scatter_param_pairs.png",
        title="hydro_sf_electric — objective vs. parameter pairs",
    )


def main(args: argparse.Namespace) -> None:
    """Run the baseline + optimize, then plot — or only one half, via
    ``--plot-only``/``--no-plot`` (see ``build_pymoo_parser``'s docstring).

    This split lets the DVC pipeline (``dvc.yaml``) treat "run NSGA2" and
    "build plots from the result" as separate stages: a plotting-only code
    change reruns just the ``plot`` stage instead of a full search.

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
    print("opt_hydro_sf_electric.py starting at")
    print_dt()
    # --quiet suppresses pymoo's OWN per-generation progress table (printed
    # directly by pymoo/Minimization, not via `logging` at all) — kept
    # separate from Python's logging level (--log-level) on purpose:
    # tying them together would flood the console with every module's
    # INFO logs (workflow loading, per-timestep orchestrator state) on
    # EVERY evaluation across an entire NSGA2 run (hundreds to thousands
    # of them), which --quiet has nothing to do with.
    logging.basicConfig(level=args.log_level)

    param_cols = [p.name for p in _param_specs()]
    objective_cols = [DISPLAY_RENAME.get(o.name, o.name) for o in _objective_specs()]

    if args.plot_only:
        df = strip_column_prefixes(pd.read_csv(args.save_dir / "pareto_results.csv"))
    else:
        if args.clean and args.save_dir.exists():
            shutil.rmtree(args.save_dir)
        args.save_dir.mkdir(parents=True, exist_ok=True)

        wf, wf_manual = build_baseline()
        baseline_lcoe = wf_manual.to_dict()["economic"]["state"]["LCOE"]
        print(f"Baseline (manual flow rate): LCOE={baseline_lcoe:.4f} $/kWh")

        _res, df, _m = run_optimization(wf, args)
        print(f"Pareto front: {len(df)} designs")
        print(df)

        if args.no_plot:
            return

    make_plots(df, args.save_dir, param_cols, objective_cols)


if __name__ == "__main__":
    main(build_parser().parse_args())
