"""Multi-objective optimization demo for the AGS direct-heat example.

STATUS (2026-08-17): unblocked, actively developed. The original blocker
(sweeping ``loop_diameter`` on ``horizontal_well`` alone collided with
``DoubletEconomicComponent._combined_production_length_and_diameter``,
which required all production-side wells to share one uniform diameter)
was fixed by excluding the horizontal well from that combination entirely
and costing it as its own well section — see ``docs/tango_next_tasks.md``'s
DONE entry for the full writeup. Not yet wired into `just demos`.

Runs the manual baseline once, then searches well depth, horizontal loop
length, horizontal loop diameter, vertical well diameter, injection
pressure, and mass flow rate with NSGA2 to minimize LCOE and maximize mean
net thermal power (``tango_next.pymoo_api.Minimization``), saving the
pareto results/configs and parallel-coordinates plots.

Decision-variable bounds and physical meaning for depth/loop length/loop
diameter/mass flow mirror the existing brute-force sweep
(``applications/tango_next/run_AGS_direct_heat_sweep/common.py``'s
``WELL_DEPTHS_M``/``LOOP_LENGTHS_M``/``LOOP_DIAMETERS_M``/
``MASS_FLOW_RATES_KG_S``), rather than inventing a different design space —
the sweep's own field paths (``sweep.py``'s ``_apply_depth``/
``_apply_loop_length``/``_apply_loop_diameter``) are copied verbatim into
the local ``ParamSpec`` factories below. ``vertical_well_diameter_param``/
``injection_pressure_param`` are new (2026-08-17, Chad's call) — see their
own factory docstrings for why each is a real, consequential parameter
worth exposing here.

Deliberately does NOT expose ``target_extraction_pressure`` as a decision
variable: confirmed by grepping every consumer of it in ``src/tango_next/``
that it's read ONLY by ``LumpedProductionWellWithPump``/
``NumericalProductionWellWithPump`` — AGS's ``production_well`` is a plain
``NumericalProductionWell`` (no pump), so this value is declared but
completely inert for this topology. Sweeping it would waste evaluations on
a parameter with zero effect on either objective; revisit only if AGS's
production well becomes a pump-bearing variant.

Every ``*_param``/``*_objective`` factory below is defined LOCALLY in this
file, including ``mass_rate_param``/``lcoe_objective`` (which happen to be
identical to ``opt_hydro_df_electric.py``'s/``opt_hydro_sf_electric.py``'s
own local copies) — none are imported from ``pymoo_api.py``, which is
deliberately generic and must not assume every system shares a param or
objective just because these three currently do (see ``pymoo_api.py``'s
own ``ParamSpec``/``ObjectiveSpec`` docstrings).
``negative_mean_thermal_power_objective`` specifically exists because AGS
is a direct-heat topology (``role: net_thermal`` in the YAML), so its
surface component's history has ``net_thermal_W``, not the electric
``net_power_W`` the other two scripts' ``negative_mean_power_objective`` reads.

Usage: uv run python applications/tango_next/opt_AGS_direct_heat/opt_AGS_direct_heat.py
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

from tango_next.pymoo_api import (
    Minimization,
    ObjectiveSpec,
    ParamSpec,
    PymooConfig,
    build_pymoo_parser,
    load_params,
    plot_objective_vs_param_scatter,
    plot_param_pair_vs_objective_scatter,
    prepare_plot_df,
)
from tango_next.utils import print_dt
from tango_next.workflows.workflow import Workflow

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
# AGS_direct_heat.yml lives in examples/tango_next/ — shared with
# applications/tango_next/run_AGS_direct_heat_sweep/ (the DVC sweep
# pipeline) and applications/tango_next/sweep_demo_AGS_direct_heat/, both
# of which expect it there, not nested under this script's own directory.
CONFIG_DIR = HERE.parents[2] / "examples/tango_next/"
DEFAULT_OUTPUT_DIR = HERE / "outputs"
PARAMS_FILE = HERE / "params.yaml"


# ---------------------------------------------------------------------------
# Local ParamSpec/ObjectiveSpec factories — AGS-specific, not in pymoo_api.py
# ---------------------------------------------------------------------------


@dataclass
class _DepthApply:
    """Picklable ``ParamSpec.apply`` for ``depth_param``.

    Sets all three depth-dependent fields together, matching
    ``run_AGS_direct_heat_sweep/sweep.py``'s ``_apply_depth`` exactly: for
    the AGS topology (injection_well -> horizontal_well -> production_well),
    depth controls the vertical sections only — loop length is a separate
    axis (see ``_LoopLengthApply``).
    """

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        cfg["components"]["injection_well"]["well_length"] = float(value)
        cfg["components"]["horizontal_well"]["wellhead_depth"] = float(value)
        cfg["components"]["production_well"]["well_length"] = float(value)
        return cfg


def depth_param(bounds: tuple[float, float]) -> ParamSpec:
    """Well depth (m) — vertical well sections + horizontal loop's starting depth."""
    return ParamSpec(name="depth_m", apply=_DepthApply(), bounds=bounds)


@dataclass
class _LoopLengthApply:
    """Picklable ``ParamSpec.apply`` for ``loop_length_param``.

    ``well_spacing`` must equal the horizontal loop length by convention,
    but is set ONLY via ``layout.well_spacing`` — NOT also on
    ``components.surface`` (unlike old tango's ``sweep.py``'s
    ``_apply_loop_length``, which sets both). ``tango_next`` rejects
    per-component overrides of fields sourced from ``common:``/``layout:``/
    ``sim_config:`` (see ``AGS_direct_heat.yml``'s own
    "well_spacing is NOT set here" comment, and
    docs/tango_next_tasks.md's "common:/component-block override
    ambiguity" section) — confirmed by ``ConfigError`` when this factory
    initially copied old tango's 3-field pattern verbatim.
    """

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        cfg["components"]["horizontal_well"]["well_length"] = float(value)
        cfg["layout"]["well_spacing"] = float(value)
        return cfg


def loop_length_param(bounds: tuple[float, float]) -> ParamSpec:
    """Horizontal loop length (m)."""
    return ParamSpec(name="loop_length_m", apply=_LoopLengthApply(), bounds=bounds)


@dataclass
class _LoopDiameterApply:
    """Picklable ``ParamSpec.apply`` for ``loop_diameter_param``.

    Only ``horizontal_well.diameter`` is swept, matching ``sweep.py``'s
    ``_apply_loop_diameter`` — the vertical sections' casing diameter is a
    separate, unrelated fixed assumption.
    """

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        cfg["components"]["horizontal_well"]["diameter"] = float(value)
        return cfg


def loop_diameter_param(bounds: tuple[float, float]) -> ParamSpec:
    """Horizontal loop diameter (m)."""
    return ParamSpec(name="loop_diameter_m", apply=_LoopDiameterApply(), bounds=bounds)


@dataclass
class _VerticalWellDiameterApply:
    """Picklable ``ParamSpec.apply`` for ``vertical_well_diameter_param``.

    Sets ``injection_well.diameter`` and ``production_well.diameter`` to
    the SAME value — one decision variable, not two independent ones, per
    Chad's call to avoid the complexity of the two vertical wells having
    different casing diameters. Deliberately independent of
    ``loop_diameter_param`` (the horizontal segment's own diameter): this
    also means ``DoubletEconomicComponent``'s uniform-diameter requirement
    for the combined vertical-production well is trivially satisfied by
    construction (there's only one vertical production-side component for
    AGS — ``production_well`` — so "uniform" is automatic here regardless
    of what this parameter is set to).
    """

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        cfg["components"]["injection_well"]["diameter"] = float(value)
        cfg["components"]["production_well"]["diameter"] = float(value)
        return cfg


def vertical_well_diameter_param(bounds: tuple[float, float]) -> ParamSpec:
    """Injection + production (vertical) well diameter (m), shared by both."""
    return ParamSpec(name="vertical_well_diameter_m", apply=_VerticalWellDiameterApply(), bounds=bounds)


@dataclass
class _InjectionPressureApply:
    """Picklable ``ParamSpec.apply`` for ``injection_pressure_param``.

    ``components.<surface_name>.injection_pressure`` is a real, consequential
    parameter for AGS's closed loop under ``injection_mode: manual`` — it's
    used directly as the loop's actual boundary condition (not iteratively
    refined; see the base YAML's own "Phase 1 limitation: this guess isn't
    yet solved for" comment), unlike ``target_extraction_pressure`` (see
    module docstring for why THAT one is excluded). Same field
    ``opt_hydro_df_electric.py``/``opt_hydro_sf_electric.py`` already expose
    as a decision variable for their own topologies.
    """

    surface_name: str = "surface"

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        cfg["components"][self.surface_name]["injection_pressure"] = float(value)
        return cfg


def injection_pressure_param(bounds: tuple[float, float], surface_name: str = "surface") -> ParamSpec:
    """Injection wellhead pressure (``components.<surface_name>.injection_pressure``, Pa)."""
    return ParamSpec(name="injection_pressure_Pa", apply=_InjectionPressureApply(surface_name), bounds=bounds)


@dataclass
class _MassRateApply:
    """Picklable ``ParamSpec.apply`` for ``mass_rate_param``.

    Same definition as ``opt_hydro_df_electric.py``'s/``opt_hydro_sf_electric.py``'s
    — duplicated deliberately, not shared via ``pymoo_api.py``, since this
    field means the same thing (``sim_config.mass_rate``, kg/s) across all
    three systems today. That overlap isn't evidence it belongs in the
    shared API instead — a future coupled reservoir model with its own
    inlet/outlet mass-flow mismatch won't have a single constant global
    mass flow rate the way these three do.
    """

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        cfg["sim_config"]["mass_rate"] = float(value)
        return cfg


def mass_rate_param(bounds: tuple[float, float]) -> ParamSpec:
    """Mass flow rate (``sim_config.mass_rate``, kg/s) as a decision variable."""
    return ParamSpec(name="mass_rate_kg_per_s", apply=_MassRateApply(), bounds=bounds)


@dataclass
class _LcoeEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` for ``lcoe_objective`` — see ``_MassRateApply``."""

    def __call__(self, wf: Workflow) -> float:
        return float(wf.to_dict()["economic"]["state"]["LCOE"])


def lcoe_objective() -> ObjectiveSpec:
    """LCOE ($/kWh), from ``DoubletEconomicComponent`` — requires an ``economic:`` block.

    Works for AGS's direct-heat topology too, despite its ``main_product:
    heat``/LCOH framing — confirmed empirically: ``economic.state`` still
    stores the value under the key ``LCOE`` regardless of product type.
    """
    return ObjectiveSpec(name="LCOE", evaluate=_LcoeEvaluate())


@dataclass
class _NegativeMeanThermalPowerEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` for ``negative_mean_thermal_power_objective``."""

    surface_name: str = "surface"

    def __call__(self, wf: Workflow) -> float:
        surface = wf._orchestrator.components[self.surface_name]  # noqa: SLF001
        history = getattr(surface, "history", None)
        net_thermal_w_history: list[float] = getattr(history, "net_thermal_W", [])
        mean_w = sum(net_thermal_w_history) / len(net_thermal_w_history) if net_thermal_w_history else 0.0
        return -mean_w


def negative_mean_thermal_power_objective(surface_name: str = "surface") -> ObjectiveSpec:
    """``-`` mean net thermal power over the run (W) — minimizing this maximizes heat delivered.

    Mirrors ``pymoo_api.negative_mean_power_objective`` exactly, reading
    ``history.net_thermal_W`` (direct-heat systems) instead of
    ``history.net_power_W`` (electric systems). See this module's own
    docstring for why this lives here rather than in ``pymoo_api.py``.
    """
    return ObjectiveSpec(
        name="negative_mean_thermal_power_W",
        evaluate=_NegativeMeanThermalPowerEvaluate(surface_name),
    )


# Single source of truth for the "negate for a human-friendly plot/print label"
# rename applied in main() — keyed off negative_mean_thermal_power_objective()'s
# own ``.name`` rather than a second, independently-typed copy of that string,
# so a future rename of the objective itself can't silently desync from this.
DISPLAY_RENAME = {negative_mean_thermal_power_objective().name: "mean_thermal_power_W"}


# ---------------------------------------------------------------------------
# CLI / baseline / optimization — same shape as opt_hydro_df_electric.py
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """CLI for tuning the pymoo search — thin wrapper around
    ``pymoo_api.build_pymoo_parser``, the shared, non-domain-specific half
    (see its own docstring for why this lives in ``pymoo_api.py`` while
    ``ParamSpec``/``ObjectiveSpec`` do not).
    """
    return build_pymoo_parser(
        description="Multi-objective optimization demo for the AGS direct-heat example.",
        default_output_dir=DEFAULT_OUTPUT_DIR,
        params=load_params(PARAMS_FILE),
    )


def build_baseline() -> tuple[Workflow, Workflow]:
    """Build the unrun template workflow and a separately-run manual baseline.

    Returns:
        ``(wf, wf_manual)`` — ``wf`` is UNRUN and must stay that way (see
        ``opt_hydro_df_electric.py``'s ``build_baseline`` docstring for the
        full rationale — ``Workflow(wf.to_dict())``, not ``copy.copy``/
        ``copy.deepcopy``, and ``wf`` itself must never be ``run()``).

    """
    wf = Workflow.from_file(CONFIG_DIR / "AGS_direct_heat.yml")
    wf_manual = Workflow(wf.to_dict())
    wf_manual.run()
    return wf, wf_manual


def _param_specs() -> list[ParamSpec]:
    """Decision variables: depth, loop length, loop diameter, vertical well
    diameter, injection pressure, mass flow rate.

    Depth/loop length/loop diameter/mass flow bounds match the existing
    brute-force sweep's own axis ranges (``run_AGS_direct_heat_sweep/
    common.py``'s ``WELL_DEPTHS_M``/``LOOP_LENGTHS_M``/``LOOP_DIAMETERS_M``/
    ``MASS_FLOW_RATES_KG_S``), not freshly-guessed values. Vertical well
    diameter/injection pressure have no sweep precedent — see their own
    ``ParamSpec`` factories' docstrings for bounds rationale.

    Extracted as its own function (rather than inlined in
    ``run_optimization``) so the DVC ``plot`` stage can recover each
    column's ``.name`` for plot axis labels without needing a
    ``Minimization`` instance or rerunning any simulation — see ``main``'s
    ``--plot-only`` path.
    """
    return [
        depth_param(bounds=(2000.0, 8000.0)),
        loop_length_param(bounds=(500.0, 8000.0)),
        loop_diameter_param(bounds=(0.2, 0.75)),
        # Same range as loop_diameter_param — no other precedent to
        # match (the brute-force sweep never varies vertical-well
        # diameter independently), flagged for Chad to adjust if a
        # different casing-diameter range is more realistic.
        vertical_well_diameter_param(bounds=(0.2, 0.75)),
        injection_pressure_param(bounds=(0.5e6, 3.0e6)),
        mass_rate_param(bounds=(3.5, 40.0)),
    ]


def _objective_specs() -> list[ObjectiveSpec]:
    """Objectives: minimize LCOE, maximize mean net thermal power — see
    ``_param_specs``' docstring for why this is its own function.
    """
    return [lcoe_objective(), negative_mean_thermal_power_objective()]


def run_optimization(
    base_wf: Workflow,
    args: argparse.Namespace,
) -> tuple[Result, pd.DataFrame, Minimization]:
    """Search depth + loop length + loop diameter + vertical well diameter +
    injection pressure + mass flow rate to minimize LCOE / maximize mean
    thermal power.

    Args:
        base_wf: UNRUN template workflow — see ``build_baseline``'s docstring.
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


# ---------------------------------------------------------------------------
# Plotting — same construction as opt_hydro_df_electric.py, retitled
# ---------------------------------------------------------------------------


def plot_pareto_parallel_coordinates(df: pd.DataFrame, out_path: Path, color_col: str = "euclidean") -> None:
    """Static parallel-coordinates plot across every pareto-front design."""
    df = df.copy()
    df.insert(0, "design_number", range(len(df)))
    cols = list(df.columns)
    data = df[cols].to_numpy(dtype=float)
    mins = data.min(axis=0)
    maxs = data.max(axis=0)
    span = np.where(maxs > mins, maxs - mins, 1.0)
    normalized = (data - mins) / span

    color_values = df[color_col].to_numpy(dtype=float)
    cmap = plt.get_cmap("viridis_r")
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

    fig.suptitle("AGS_direct_heat — pareto front (depth x loop length x loop diameter x mass rate)", y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _diagonal_label_offset(x: pd.Series, y: pd.Series) -> tuple[tuple[float, float], str]:
    """Pick a point-label offset perpendicular to the data's dominant diagonal."""
    with np.errstate(invalid="ignore"):
        r = np.corrcoef(x, y)[0, 1]
    if np.isnan(r) or r >= 0:
        return (-5, 5), "right"
    return (5, 5), "left"


def plot_pareto_scatter(df: pd.DataFrame, out_path: Path) -> None:
    """2D scatter of the two objectives (LCOE vs. mean net thermal power), each point
    labeled by its design number.
    """
    thermal_mw = df["mean_thermal_power_W"] / 1.0e6
    lcoe = df["LCOE"]

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(lcoe, thermal_mw, s=40, color="tab:blue", zorder=3)
    xytext, ha = _diagonal_label_offset(lcoe, thermal_mw)
    for i, (x, y) in enumerate(zip(lcoe, thermal_mw, strict=True)):
        ax.annotate(str(i), (x, y), textcoords="offset points", xytext=xytext, ha=ha, fontsize=8)

    ax.set_xlabel("LCOE ($/kWh)")
    ax.set_ylabel("Mean net thermal power (MW)")
    ax.set_title("AGS_direct_heat — pareto front (objective space, labeled by design number)")
    ax.grid(visible=True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_pareto_scatter_zscore(df: pd.DataFrame, out_path: Path) -> None:
    """Z-score-normalized variant of ``plot_pareto_scatter``."""
    lcoe = df["LCOE"]
    thermal = df["mean_thermal_power_W"]
    lcoe_z = (lcoe - lcoe.mean()) / (lcoe.std() or 1.0)
    thermal_z = (thermal - thermal.mean()) / (thermal.std() or 1.0)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.axhline(0, color="grey", linewidth=0.8, zorder=1)
    ax.axvline(0, color="grey", linewidth=0.8, zorder=1)
    ax.scatter(lcoe_z, thermal_z, s=40, color="tab:orange", zorder=3)
    xytext, ha = _diagonal_label_offset(lcoe_z, thermal_z)
    for i, (x, y) in enumerate(zip(lcoe_z, thermal_z, strict=True)):
        ax.annotate(str(i), (x, y), textcoords="offset points", xytext=xytext, ha=ha, fontsize=8)

    ax.set_xlabel("LCOE (z-score)")
    ax.set_ylabel("Mean net thermal power (z-score)")
    ax.set_title("AGS_direct_heat — pareto front (z-score-normalized objective space)")
    ax.grid(visible=True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_pareto_parallel_coordinates_interactive(
    df: pd.DataFrame,
    out_path: Path,
    color_col: str = "euclidean",
) -> bool:
    """Interactive HTML version of ``plot_pareto_parallel_coordinates`` (Plotly Parcoords)."""
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

    # "~s" (d3-format SI-prefix style: 1.3G, 823k, ...) is human-readable and
    # never emits markup (Plotly's default formatter renders scientific
    # notation as literal "<sup>...</sup>" text here, which Parcoords'
    # plain-SVG tick labels can't render), but ONLY for magnitude >= 1 — d3
    # also applies NEGATIVE SI prefixes (milli, micro, ...) below 1, so e.g.
    # 0.214927 renders as "214.927m", where that "m" means milli, not
    # meters. That collides badly with an already-"_m"-suffixed column name
    # like loop_diameter_m, silently misreading a 0.215 m design as 215 m.
    # Columns with magnitude < 1 get plain fixed-point instead, with no
    # prefix to misread.
    dimensions: list[dict[str, Any]] = [
        {
            "label": c,
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
        title="AGS_direct_heat — pareto front (interactive: drag along an axis to filter)",
        paper_bgcolor="#e8e8e8",
        plot_bgcolor="#e8e8e8",
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

    # n_gen is run provenance (constant across every row of a single optimization
    # run), not a per-design axis — drop it from the parallel-coordinates plots,
    # which otherwise plot every df column, since a constant column carries no
    # visual information there. Still present in pareto_results.csv (via df).
    parcoord_df = plot_df.drop(columns=["n_gen"], errors="ignore")
    plot_pareto_parallel_coordinates(parcoord_df, save_dir / "pareto_parallel_coordinates.png")
    plot_pareto_parallel_coordinates_interactive(
        parcoord_df,
        save_dir / "pareto_parallel_coordinates.html",
    )
    plot_pareto_scatter(plot_df, save_dir / "pareto_scatter.png")
    plot_pareto_scatter_zscore(plot_df, save_dir / "pareto_scatter_zscore.png")
    plot_objective_vs_param_scatter(
        plot_df,
        param_cols=param_cols,
        objective_cols=objective_cols,
        out_path=save_dir / "pareto_scatter_by_param.png",
        title="AGS_direct_heat — objectives vs. parameters",
    )
    plot_param_pair_vs_objective_scatter(
        plot_df,
        param_cols=param_cols,
        objective_cols=objective_cols,
        out_path=save_dir / "pareto_scatter_param_pairs.png",
        title="AGS_direct_heat — objective vs. parameter pairs",
    )


def main(args: argparse.Namespace) -> None:
    """Run the baseline + optimize, then plot — or only one half, via
    ``--plot-only``/``--no-plot`` (see ``build_pymoo_parser``'s docstring).

    This split lets the DVC pipeline (``dvc.yaml``) treat "run NSGA2" and
    "build plots from the result" as separate stages: a plotting-only code
    change reruns just the ``plot`` stage instead of a full search.
    """
    print("opt_AGS_direct_heat.py starting at")
    print_dt()
    logging.basicConfig(level=args.log_level)

    param_cols = [p.name for p in _param_specs()]
    objective_cols = [DISPLAY_RENAME.get(o.name, o.name) for o in _objective_specs()]

    if args.plot_only:
        df = pd.read_csv(args.save_dir / "pareto_results.csv")
    else:
        if args.clean and args.save_dir.exists():
            shutil.rmtree(args.save_dir)
        args.save_dir.mkdir(parents=True, exist_ok=True)

        wf, wf_manual = build_baseline()
        baseline_lcoe = wf_manual.to_dict()["economic"]["state"]["LCOE"]
        print(f"Baseline (manual design point): LCOE={baseline_lcoe:.4f} $/kWh")

        _res, df, _m = run_optimization(wf, args)
        print(f"Pareto front: {len(df)} designs")
        print(df)

        if args.no_plot:
            return

    make_plots(df, args.save_dir, param_cols, objective_cols)


if __name__ == "__main__":
    main(build_parser().parse_args())
