"""Multi-objective optimization demo for the AGS binary-cycle (ORC) electric example.

Runs the manual baseline once, then searches well depth, horizontal loop
length, horizontal loop diameter, vertical well diameter, surface pipe
diameter, injection pressure, mass flow rate, and the ORC feed-pump outlet
pressure with NSGA2 to minimize LCOE and maximize mean net electric power
(``tango.pymoo_api.Minimization``), saving the pareto results/configs and
plots. Production temperature, specific investment cost, and OPEX are
reporting-only read-outs — see ``_report_specs``.

The geometry parameters (depth, loop length, loop diameter, vertical well
diameter) use the same field paths as ``opt_AGS_direct_heat.py``, since both
configs share the same closed-loop subsurface shape. Their bounds differ:
binary-cycle power needs much hotter produced fluid than district heating,
so the depth range here sits around ``AGS_ORC_electric.yml``'s own 8000 m.

Every decision variable that ``AGS_ORC_electric.yml`` exposes is included,
except:

- ``target_extraction_pressure``: read only by pump-bearing production wells.
  AGS's ``production_well`` is a plain numerical well, so the value is inert
  for this topology.
- The ORC condensing pressure (``orc_turbine``/``orc_desuperheater``/
  ``orc_condenser``'s ``p_out_megapascals``): it follows from the site's
  cooling limit (surface temperature plus ``approach_temperature``), so it is
  a site condition, not a design choice.

The injection policy is forced to ``manual`` on the base workflow, whatever
the YAML says: the ``auto-*`` policies solve for mass flow rate or injection
pressure on every pass, which would fight the optimizer over the same
variables. AGS has no reservoir, so ``manual-fracking-check`` doesn't apply.

Every ``*_param``/``*_objective`` factory below is defined locally in this
file, not imported from ``pymoo_api.py``, which is deliberately generic (see
its ``ParamSpec``/``ObjectiveSpec`` docstrings).

Usage: ``dvc repro`` from this directory (or ``sbatch
opt_AGS_ORC_electric_job.sh`` on Euler) — runs both the ``optimize`` and
``plot`` stages in ``dvc.yaml`` under DVC's dependency/output tracking.
Running this script directly with ``uv run python
opt_AGS_ORC_electric.py`` also works but bypasses that tracking, so its
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
import yaml
from CoolProp.CoolProp import PropsSI
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
CONFIG_PATH = HERE.parents[1] / "example_configs" / "AGS_ORC_electric.yml"
DEFAULT_OUTPUT_DIR = HERE / "outputs"
PARAMS_FILE = HERE / "params.yaml"


# ---------------------------------------------------------------------------
# Local ParamSpec/ObjectiveSpec factories — AGS/ORC-specific, not in pymoo_api.py
# ---------------------------------------------------------------------------


@dataclass
class _DepthApply:
    """Picklable ``ParamSpec.apply`` for ``depth_param``.

    A closure defined inside a factory function can't be pickled, which
    breaks the ``n_processes > 1`` path; a module-level dataclass with
    ``__call__`` pickles fine, so every factory below uses this shape.

    Sets all three depth-dependent fields together: for the AGS topology
    (injection_well -> horizontal_well -> production_well), depth controls the
    vertical sections and the horizontal loop's starting depth. Loop length is
    a separate axis (see ``_LoopLengthApply``).
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

    ``well_spacing`` (the surface pipe run) equals the horizontal loop length
    by convention, but is set only via ``layout.well_spacing``: ``tango``
    rejects per-component overrides of fields sourced from ``layout:``, so
    setting it on ``components.surface`` as well raises ``ConfigError``.
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
    """Picklable ``ParamSpec.apply`` for ``loop_diameter_param`` — see ``_DepthApply``."""

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        cfg["components"]["horizontal_well"]["diameter"] = float(value)
        return cfg


def loop_diameter_param(bounds: tuple[float, float]) -> ParamSpec:
    """Horizontal loop diameter (m)."""
    return ParamSpec(name="loop_diameter_m", apply=_LoopDiameterApply(), bounds=bounds)


@dataclass
class _VerticalWellDiameterApply:
    """Picklable ``ParamSpec.apply`` for ``vertical_well_diameter_param``.

    Sets ``injection_well.diameter`` and ``production_well.diameter`` to the
    same value: one decision variable, not two. This also keeps
    ``DoubletEconomicComponent``'s uniform-diameter requirement for the
    production side satisfied by construction (AGS has a single vertical
    production component).
    """

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        cfg["components"]["injection_well"]["diameter"] = float(value)
        cfg["components"]["production_well"]["diameter"] = float(value)
        return cfg


def vertical_well_diameter_param(bounds: tuple[float, float]) -> ParamSpec:
    """Injection + production (vertical) well diameter (m), shared by both."""
    return ParamSpec(name="vertical_well_diameter_m", apply=_VerticalWellDiameterApply(), bounds=bounds)


@dataclass
class _SurfacePipeDiameterApply:
    """Picklable ``ParamSpec.apply`` for ``surface_pipe_diameter_param``.

    ``components.<surface_name>.pipe_diameter`` sets both the friction
    pressure drop along the ``well_spacing`` surface pipe run and that pipe's
    cost, so it affects both objectives.
    """

    surface_name: str = "surface"

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        cfg["components"][self.surface_name]["pipe_diameter"] = float(value)
        return cfg


def surface_pipe_diameter_param(bounds: tuple[float, float], surface_name: str = "surface") -> ParamSpec:
    """Surface pipe diameter (``components.<surface_name>.pipe_diameter``, m)."""
    return ParamSpec(
        name="surface_pipe_diameter_m",
        apply=_SurfacePipeDiameterApply(surface_name),
        bounds=bounds,
    )


@dataclass
class _InjectionPressureApply:
    """Picklable ``ParamSpec.apply`` for ``injection_pressure_param``.

    Under ``injection_mode: manual``, ``components.<surface_name>.injection_pressure``
    is the loop's fixed boundary condition, so it directly sets how much work
    ``circulation_control`` does.
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
    """Picklable ``ParamSpec.apply`` for ``mass_rate_param`` — see ``_DepthApply``."""

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        cfg["sim_config"]["mass_rate"] = float(value)
        return cfg


def mass_rate_param(bounds: tuple[float, float]) -> ParamSpec:
    """Mass flow rate (``sim_config.mass_rate``, kg/s) as a decision variable."""
    return ParamSpec(name="mass_rate_kg_per_s", apply=_MassRateApply(), bounds=bounds)


@dataclass
class _OrcFeedPumpPressureApply:
    """Picklable ``ParamSpec.apply`` for ``orc_feed_pump_pressure_param``.

    ``orc_feed_pump``'s outlet pressure is the ORC's high pressure: the
    preheater and evaporator both have ``pressure_ratio2: 1.0``, so this value
    is also the evaporating pressure and the turbine inlet pressure. The
    evaporator's ``vapor_mass_fraction_out2: 1`` then fixes the evaporating
    temperature at R245fa's saturation temperature at this pressure.

    Also moves the TESPy starting guesses that depend on this pressure, since
    a guess left at the base design's value makes the solve fail at many
    pressures inside the bounds:

    - the preheater's and evaporator's ``p0_out2``, to this pressure;
    - the evaporator's ``h0_out1`` (geofluid outlet enthalpy), to its exact
      solved value: R245fa enters the evaporator as saturated liquid
      (``preheater.vapor_mass_fraction_out2: 0``), so ``ttd_l`` puts the
      geofluid outlet at the saturation temperature plus ``ttd_l``. Taken as
      saturated-liquid geofluid at that temperature, which is within a
      fraction of a percent of the compressed-liquid value.
    """

    power_plant_path: tuple[str, ...] = ("surface", "power_plant")

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        plant = cfg["components"]
        for key in self.power_plant_path:
            plant = plant[key]
        nodes = plant["nodes"]
        nodes["orc_feed_pump"]["p_out_megapascals"] = float(value)
        nodes["preheater"]["p0_out2"] = float(value)
        nodes["evaporator"]["p0_out2"] = float(value)

        orc_fluid = nodes["preheater"]["fluid_out2"]
        geofluid = cfg["common"]["fluid_name"]
        t_saturation_k = PropsSI("T", "P", float(value) * 1.0e6, "Q", 0, orc_fluid)
        t_geofluid_out_k = t_saturation_k + float(nodes["evaporator"]["ttd_l"])
        nodes["evaporator"]["h0_out1"] = (
            PropsSI("H", "T", t_geofluid_out_k, "Q", 0, geofluid) / 1.0e3
        )  # J/kg -> kJ/kg
        return cfg


def orc_feed_pump_pressure_param(bounds: tuple[float, float]) -> ParamSpec:
    """ORC feed-pump outlet (= evaporating) pressure (``orc_feed_pump.p_out_megapascals``, MPa)."""
    return ParamSpec(name="orc_feed_pump_pressure_MPa", apply=_OrcFeedPumpPressureApply(), bounds=bounds)


@dataclass
class _LcoeEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` for ``lcoe_objective`` — see ``_DepthApply``."""

    def __call__(self, wf: Workflow) -> float:
        return float(wf.to_dict()["economic"]["state"]["LCOE"])


def lcoe_objective() -> ObjectiveSpec:
    """LCOE ($/kWh), from ``DoubletEconomicComponent`` — requires an ``economic:`` block."""
    return ObjectiveSpec(name="LCOE", evaluate=_LcoeEvaluate())


@dataclass
class _NegativeMeanPowerEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` for ``negative_mean_power_objective`` — see ``_DepthApply``."""

    surface_name: str = "surface"

    def __call__(self, wf: Workflow) -> float:
        surface = wf._orchestrator.components[self.surface_name]  # noqa: SLF001
        history = getattr(surface, "history", None)
        net_power_w_history: list[float] = getattr(history, "net_power_W", [])
        mean_w = sum(net_power_w_history) / len(net_power_w_history) if net_power_w_history else 0.0
        return -mean_w


def negative_mean_power_objective(surface_name: str = "surface") -> ObjectiveSpec:
    """``-`` mean net electric power over the run (W) — minimizing this maximizes power.

    Mean rather than total energy: every timestep has the same duration, so
    the two differ only by a constant factor and carry the same optimization
    signal, and "450 kW average" is easier to read than a total in joules.
    """
    return ObjectiveSpec(name="negative_mean_power_W", evaluate=_NegativeMeanPowerEvaluate(surface_name))


@dataclass
class _SpecificInvestmentCostEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` for ``specific_investment_cost_report`` — see ``_DepthApply``."""

    def __call__(self, wf: Workflow) -> float:
        return float(wf.to_dict()["economic"]["state"]["specific_investment_cost"])


def specific_investment_cost_report() -> ObjectiveSpec:
    """Total investment cost per unit of net electric power ($/kW), from ``DoubletEconomicComponent``.

    REPORTING only — pass via ``Minimization(report_specs=[...])``, not
    ``objectives=``.
    """
    return ObjectiveSpec(name="specific_investment_cost", evaluate=_SpecificInvestmentCostEvaluate())


@dataclass
class _OpexEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` for ``opex_report`` — see ``_DepthApply``."""

    def __call__(self, wf: Workflow) -> float:
        return float(wf.to_dict()["economic"]["state"]["OPEX"])


def opex_report() -> ObjectiveSpec:
    """Net annual OPEX ($/yr), from ``DoubletEconomicComponent``.

    REPORTING only — pass via ``Minimization(report_specs=[...])``, not
    ``objectives=``.
    """
    return ObjectiveSpec(name="OPEX", evaluate=_OpexEvaluate())


@dataclass
class _NegativeProductionTemperatureEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` for ``negative_production_temperature_report``."""

    well_name: str = "production_well"

    def __call__(self, wf: Workflow) -> float:
        well = wf._orchestrator.components[self.well_name]  # noqa: SLF001
        history = getattr(well, "history", None)
        t_outlet_k_history: list[float] = getattr(history, "T_outlet", [])
        if not t_outlet_k_history:
            return float("nan")
        return -(t_outlet_k_history[-1] - 273.15)


def negative_production_temperature_report(well_name: str = "production_well") -> ObjectiveSpec:
    """``-`` final-timestep production-well outlet temperature (degC).

    The final timestep, not a run average: it's the longest-run outlet
    temperature the plant has to keep working with. REPORTING only — pass via
    ``Minimization(report_specs=[...])``, not ``objectives=``.
    """
    return ObjectiveSpec(
        name="negative_production_temperature_C",
        evaluate=_NegativeProductionTemperatureEvaluate(well_name),
    )


# Single source of truth for the "negate for a human-friendly plot/print label"
# rename applied in main() — keyed off each spec's own ``.name`` so a rename of
# the spec can't silently desync from this.
DISPLAY_RENAME = {
    negative_mean_power_objective().name: "mean_power_W",
    negative_production_temperature_report().name: "production_temperature_C",
}

# Full plot-axis display label for each column, keyed on its DISPLAY name
# (post-DISPLAY_RENAME). A full replacement label rather than a "[unit]"
# append, since most names already end in a unit suffix. Carries the same
# par:/obj:/rep: category prefix ``Minimization._column_rename`` writes to the
# CSV, so a plot mixing decision variables, objectives, and reporting-only
# read-outs shows which is which. Columns absent here (design_number) show
# unchanged.
COLUMN_LABELS = {
    "depth_m": "par:depth [m]",
    "loop_length_m": "par:loop_length [m]",
    "loop_diameter_m": "par:loop_diameter [m]",
    "vertical_well_diameter_m": "par:vertical_well_diameter [m]",
    "surface_pipe_diameter_m": "par:surface_pipe_diameter [m]",
    "injection_pressure_Pa": "par:injection_pressure [Pa]",
    "mass_rate_kg_per_s": "par:mass_rate [kg/s]",
    "orc_feed_pump_pressure_MPa": "par:orc_feed_pump_pressure [MPa]",
    "LCOE": "obj:LCOE [$/kWh]",
    "mean_power_W": "obj:mean_power [W]",
    "production_temperature_C": "rep:production_temperature [°C]",
    "specific_investment_cost": "rep:specific_investment_cost [$/kW]",
    "OPEX": "rep:OPEX [$/yr]",
    "euclidean": "euclidean [z-score]",
}


def _pretty_label(label: str) -> str:
    """``"par:mass_rate [kg/s]"`` if ``label`` has a known display form (see ``COLUMN_LABELS``), else unchanged."""
    return COLUMN_LABELS.get(label, label)


# ---------------------------------------------------------------------------
# CLI / baseline / optimization
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """CLI for tuning the pymoo search — thin wrapper around ``pymoo_api.build_pymoo_parser``."""
    return build_pymoo_parser(
        description="Multi-objective optimization demo for the AGS binary-cycle (ORC) electric example.",
        default_output_dir=DEFAULT_OUTPUT_DIR,
        params=load_params(PARAMS_FILE),
    )


def build_baseline() -> tuple[Workflow, Workflow]:
    """Build the unrun template workflow and a separately-run manual baseline.

    Forces ``sim_config.injection_mode`` to ``manual`` (see module docstring).

    Returns:
        ``(wf, wf_manual)`` — ``wf`` is UNRUN and must stay that way:
        ``Minimization`` builds every evaluation's config from
        ``wf.to_dict()``, which includes each component's history, so a run
        ``wf`` would pre-populate every evaluation with the baseline's
        timesteps. ``wf_manual`` is an independent copy, built with
        ``Workflow(wf.to_dict())`` (``copy.deepcopy`` doesn't survive
        ``GraphSurface``'s live TESPy network), run only to report the
        baseline.

    """
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    cfg["sim_config"]["injection_mode"] = "manual"
    wf = Workflow(cfg)
    wf_manual = Workflow(wf.to_dict())
    wf_manual.run()
    return wf, wf_manual


DEFAULT_BOUNDS: dict[str, tuple[float, float]] = {
    # Brackets the base YAML's 8000 m. The shallow end is where produced
    # fluid gets too cool to evaporate R245fa at the lower feed-pump
    # pressures; the deep end matches the deepest closed-loop concepts.
    "depth_m": (6_000.0, 10_000.0),
    # Same ranges as opt_AGS_direct_heat.py for the loop geometry and well
    # diameters (the AGS sweep's own loop length/diameter axes).
    "loop_length_m": (500.0, 8_000.0),
    "loop_diameter_m": (0.15, 0.75),
    "vertical_well_diameter_m": (0.2, 0.75),
    "surface_pipe_diameter_m": (0.2, 0.75),
    "injection_pressure_Pa": (0.5e6, 6.0e6),
    "mass_rate_kg_per_s": (5.0, 70.0),
    # Lower bound stays well above the 0.125 MPa condensing pressure, so the
    # feed pump always raises pressure. Upper bound saturates R245fa at
    # ~142 degC, 0.65 MPa below its 3.65 MPa critical pressure; designs whose
    # produced fluid is too cool for the chosen pressure fail to solve and are
    # rejected as infeasible.
    "orc_feed_pump_pressure_MPa": (0.35, 3.0),
}


def _param_specs(bounds: dict[str, tuple[float, float]] | None = None) -> list[ParamSpec]:
    """Decision variables, with ``DEFAULT_BOUNDS`` unless ``bounds`` overrides them.

    Args:
        bounds: Replacement bounds keyed by param name (e.g. a narrow range
            around the base YAML for a smoke test). Must have exactly the
            same keys as ``DEFAULT_BOUNDS``.

    Extracted as its own function so the DVC ``plot`` stage can recover each
    column's ``.name`` without building a ``Minimization`` or rerunning any
    simulation — see ``main``'s ``--plot-only`` path.
    """
    b = DEFAULT_BOUNDS if bounds is None else bounds
    if set(b) != set(DEFAULT_BOUNDS):
        raise ValueError(f"bounds keys {sorted(b)} must match {sorted(DEFAULT_BOUNDS)}")
    return [
        depth_param(bounds=b["depth_m"]),
        loop_length_param(bounds=b["loop_length_m"]),
        loop_diameter_param(bounds=b["loop_diameter_m"]),
        vertical_well_diameter_param(bounds=b["vertical_well_diameter_m"]),
        surface_pipe_diameter_param(bounds=b["surface_pipe_diameter_m"]),
        injection_pressure_param(bounds=b["injection_pressure_Pa"]),
        mass_rate_param(bounds=b["mass_rate_kg_per_s"]),
        orc_feed_pump_pressure_param(bounds=b["orc_feed_pump_pressure_MPa"]),
    ]


def _objective_specs() -> list[ObjectiveSpec]:
    """Objectives: minimize LCOE, maximize mean net electric power."""
    return [lcoe_objective(), negative_mean_power_objective()]


def _report_specs() -> list[ObjectiveSpec]:
    """Reporting-only read-outs: final production temperature, specific investment cost, OPEX.

    Computed once for the final pareto front and shown in
    ``pareto_results.csv``/the plots, but not fed to NSGA2.
    """
    return [negative_production_temperature_report(), specific_investment_cost_report(), opex_report()]


def run_optimization(
    base_wf: Workflow,
    args: argparse.Namespace,
    param_specs: list[ParamSpec] | None = None,
) -> tuple[Result, pd.DataFrame, Minimization]:
    """Search every decision variable in ``_param_specs`` to minimize LCOE / maximize mean power.

    Args:
        base_wf: UNRUN template workflow — see ``build_baseline``'s docstring.
        args: Parsed CLI args from ``build_parser()``.
        param_specs: Decision variables; defaults to ``_param_specs()``.

    Returns:
        ``(res, df, m)`` — ``m`` (the ``Minimization`` instance) is returned
        so callers can read ``m.params``/``m.objectives`` for their names.

    """
    m = Minimization(
        base_workflow=base_wf,
        params=_param_specs() if param_specs is None else param_specs,
        objectives=_objective_specs(),
        report_specs=_report_specs(),
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


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------


def plot_pareto_parallel_coordinates(df: pd.DataFrame, out_path: Path, color_col: str = "euclidean") -> None:
    """Static parallel-coordinates plot across every pareto-front design.

    Prepends a ``design_number`` axis (0-based, matching
    ``pareto_configs/design_NNN.yml``) so a line can be traced back to its
    saved config. Operates on a copy of ``df``.
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

    fig.suptitle("AGS_ORC_electric — pareto front", y=0.99)
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


def plot_pareto_scatter(
    df: pd.DataFrame,
    out_path: Path,
    color_col: str = "production_temperature_C",
) -> None:
    """2D scatter of LCOE vs. mean net electric power (the two objectives), colored by production temperature."""
    power_mw = df["mean_power_W"] / 1.0e6
    lcoe = df["LCOE"]
    color_values = df[color_col].to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(8, 6))
    sc = ax.scatter(lcoe, power_mw, s=40, c=color_values, cmap="viridis", zorder=3)
    xytext, ha = _diagonal_label_offset(lcoe, power_mw)
    for i, (x, y) in enumerate(zip(lcoe, power_mw, strict=True)):
        ax.annotate(str(i), (x, y), textcoords="offset points", xytext=xytext, ha=ha, fontsize=8)

    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label(_pretty_label(color_col))

    ax.set_xlabel("LCOE ($/kWh)")
    ax.set_ylabel("Mean net electric power (MW)")
    ax.set_title("AGS_ORC_electric — pareto front (objective space, color = production temperature)")
    ax.grid(visible=True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_pareto_scatter_zscore(
    df: pd.DataFrame,
    out_path: Path,
    color_col: str = "production_temperature_C",
) -> None:
    """Z-score-normalized variant of ``plot_pareto_scatter``."""
    lcoe = df["LCOE"]
    power = df["mean_power_W"]
    lcoe_z = (lcoe - lcoe.mean()) / (lcoe.std() or 1.0)
    power_z = (power - power.mean()) / (power.std() or 1.0)
    color_values = df[color_col].to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.axhline(0, color="grey", linewidth=0.8, zorder=1)
    ax.axvline(0, color="grey", linewidth=0.8, zorder=1)
    sc = ax.scatter(lcoe_z, power_z, s=40, c=color_values, cmap="viridis", zorder=3)
    xytext, ha = _diagonal_label_offset(lcoe_z, power_z)
    for i, (x, y) in enumerate(zip(lcoe_z, power_z, strict=True)):
        ax.annotate(str(i), (x, y), textcoords="offset points", xytext=xytext, ha=ha, fontsize=8)

    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label(_pretty_label(color_col))

    ax.set_xlabel("LCOE (z-score)")
    ax.set_ylabel("Mean net electric power (z-score)")
    ax.set_title("AGS_ORC_electric — pareto front (z-score, color = production temperature)")
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

    # "~s" (SI-prefix style: 1.3G, 823k) only for magnitudes >= 1: below 1,
    # d3 uses milli/micro prefixes, so 0.215 would render as "215m" and read
    # as meters on an "_m" column. Smaller columns get plain "~g" instead.
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
        title="AGS_ORC_electric — pareto front (interactive: drag along an axis to filter)",
        paper_bgcolor="#e8e8e8",
        plot_bgcolor="#e8e8e8",
        # Parcoords can't rotate axis labels, so widen the figure per
        # dimension instead to keep labels from overlapping.
        width=max(1200, 220 * len(cols)),
        height=700,
    )
    fig.write_html(out_path)
    return True


def make_plots(df: pd.DataFrame, save_dir: Path, param_cols: list[str], objective_cols: list[str]) -> None:
    """Build every plot from a pareto-front dataframe — the DVC ``plot`` stage's whole job.

    ``param_cols``/``objective_cols`` are passed in (derived from
    ``_param_specs``/``_objective_specs``) rather than read off a live
    ``Minimization``, since ``--plot-only`` never builds one. No empty-``df``
    guard: an empty front means no feasible design was found, which should
    fail loudly here.
    """
    plot_df = prepare_plot_df(df, DISPLAY_RENAME)

    plot_pareto_parallel_coordinates(plot_df, save_dir / "pareto_parallel_coordinates.png")
    plot_pareto_parallel_coordinates_interactive(plot_df, save_dir / "pareto_parallel_coordinates.html")
    plot_pareto_scatter(plot_df, save_dir / "pareto_scatter.png")
    plot_pareto_scatter_zscore(plot_df, save_dir / "pareto_scatter_zscore.png")
    plot_objective_vs_param_scatter(
        plot_df,
        param_cols=param_cols,
        objective_cols=objective_cols,
        out_path=save_dir / "pareto_scatter_by_param.png",
        title="AGS_ORC_electric — objectives vs. parameters",
    )
    plot_param_pair_vs_objective_scatter(
        plot_df,
        param_cols=param_cols,
        objective_cols=objective_cols,
        out_path=save_dir / "pareto_scatter_param_pairs.png",
        title="AGS_ORC_electric — objective vs. parameter pairs",
    )


def main(args: argparse.Namespace) -> None:
    """Run the baseline + optimize, then plot — or only one half, via ``--plot-only``/``--no-plot``.

    The split lets the DVC pipeline (``dvc.yaml``) treat "run NSGA2" and
    "build plots from the result" as separate stages, so a plotting-only
    change reruns just the ``plot`` stage.
    """
    print("opt_AGS_ORC_electric.py starting at")
    print_dt()
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
        baseline_power_w = -negative_mean_power_objective().evaluate(wf_manual)
        print(
            f"Baseline (manual design point): LCOE={baseline_lcoe:.4f} $/kWh, "
            f"mean net power={baseline_power_w / 1e3:.1f} kW",
        )

        _res, df, _m = run_optimization(wf, args)
        print(f"Pareto front: {len(df)} designs")
        print(df)

        if args.no_plot:
            return

    make_plots(df, args.save_dir, param_cols, objective_cols)


if __name__ == "__main__":
    main(build_parser().parse_args())
