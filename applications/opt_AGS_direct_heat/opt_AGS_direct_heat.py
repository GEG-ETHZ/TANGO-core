"""Multi-objective optimization demo for the AGS direct-heat example.

The horizontal well is costed as its own
well section, independent of ``DoubletEconomicComponent``'s
uniform-diameter requirement for the combined vertical-production well —
see ``vertical_well_diameter_param``'s docstring for how that requirement
stays satisfied here.

Runs the manual baseline once, then searches well depth, horizontal loop
length, horizontal loop diameter, vertical well diameter, injection
pressure, and mass flow rate with NSGA2 to minimize LCOE and minimize
specific investment cost (``tango.pymoo_api.Minimization``), saving
the pareto results/configs and parallel-coordinates plots. Mean net
thermal power and production temperature are reporting-only read-outs,
not active objectives — see ``_objective_specs``/``_report_specs``.

Decision-variable bounds and physical meaning for depth/loop length/loop
diameter/mass flow mirror the existing brute-force sweep
(``applications/run_AGS_direct_heat_sweep/common.py``'s
``WELL_DEPTHS_M``/``LOOP_LENGTHS_M``/``LOOP_DIAMETERS_M``/
``MASS_FLOW_RATES_KG_S``), rather than inventing a different design space —
the sweep's own field paths (``sweep.py``'s ``_apply_depth``/
``_apply_loop_length``/``_apply_loop_diameter``) are copied verbatim into
the local ``ParamSpec`` factories below. ``vertical_well_diameter_param``
and ``injection_pressure_param`` have no sweep-script analog; see their
own factory docstrings for why each is a real, consequential parameter
worth exposing here.

Deliberately does NOT expose ``target_extraction_pressure`` as a decision
variable: confirmed by grepping every consumer of it in ``src/tango/``
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
``negative_mean_thermal_power_report`` specifically exists because AGS
is a direct-heat topology (``role: net_thermal`` in the YAML), so its
surface component's history has ``net_thermal_W``, not the electric
``net_power_W`` the other two scripts' ``negative_mean_power_objective`` reads.

Usage: ``dvc repro`` from this directory (or ``sbatch
opt_AGS_direct_heat_job.sh`` on Euler) — runs both the ``optimize`` and
``plot`` stages in ``dvc.yaml`` under DVC's dependency/output tracking.
Running this script directly with ``uv run python
opt_AGS_direct_heat.py`` also works but bypasses that tracking, so its
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
    ConstraintSpec,
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
# AGS_direct_heat.yml lives in example_configs/ — shared with
# applications/run_AGS_direct_heat_sweep/ (the DVC sweep
# pipeline) and applications/sweep_demo_AGS_direct_heat/, both
# of which expect it there, not nested under this script's own directory.
CONFIG_DIR = HERE.parents[1] / "example_configs/"
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
    ``components.surface``. ``tango`` rejects
    per-component overrides of fields sourced from ``common:``/``layout:``/
    ``sim_config:`` (see ``AGS_direct_heat.yml``'s own
    "well_spacing is NOT set here" comment, and
    docs/tango_tasks.md's "common:/component-block override
    ambiguity" section) — confirmed by ``ConfigError`` when this factory
    initially set it in both places.
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
    the SAME value — one decision variable, not two independent ones,
    avoiding the complexity of the two vertical wells having different
    casing diameters. Deliberately independent of
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
class _SpecificInvestmentCostEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` for ``specific_investment_cost_objective`` — see ``_MassRateApply``."""

    def __call__(self, wf: Workflow) -> float:
        return float(wf.to_dict()["economic"]["state"]["specific_investment_cost"])


def specific_investment_cost_objective() -> ObjectiveSpec:
    """Total investment cost per unit of (main-product) power ($/kW), from ``DoubletEconomicComponent``.

    An active NSGA2 objective — pass via ``Minimization(objectives=[...])``,
    NOT ``report_specs=``. See
    ``DoubletEconomicComponent._compute_specific_investment_cost``'s
    docstring for the exact formula and its caveats (run-averaged, not
    nameplate, power) — for this app's ``main_product: heat`` config, the
    denominator is ``net_thermal_W``, the same power LCOH itself uses.
    """
    return ObjectiveSpec(name="specific_investment_cost", evaluate=_SpecificInvestmentCostEvaluate())


@dataclass
class _OpexEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` for ``opex_report`` — see ``_MassRateApply``."""

    def __call__(self, wf: Workflow) -> float:
        return float(wf.to_dict()["economic"]["state"]["OPEX"])


def opex_report() -> ObjectiveSpec:
    """Net annual OPEX ($/yr), from ``DoubletEconomicComponent`` — see ``_compute_opex``.

    REPORTING only — pass via ``Minimization(report_specs=[opex_report()])``,
    NOT ``objectives=``. OPEX should show up in ``pareto_results.csv``/the
    parallel-coordinates plot, but doesn't need to actively drive the
    search — NSGA2 already has 2 real objectives (LCOE, specific investment
    cost); adding this would meaningfully dilute convergence for a value
    that already correlates tightly with CAPEX (and so with specific
    investment cost, itself an active objective) — not clearly worth the
    added search-dimensionality cost for a metric this redundant with
    what's already there.
    """
    return ObjectiveSpec(name="OPEX", evaluate=_OpexEvaluate())


@dataclass
class _NegativeMeanThermalPowerEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` for ``negative_mean_thermal_power_report``."""

    surface_name: str = "surface"

    def __call__(self, wf: Workflow) -> float:
        surface = wf._orchestrator.components[self.surface_name]  # noqa: SLF001
        history = getattr(surface, "history", None)
        net_thermal_w_history: list[float] = getattr(history, "net_thermal_W", [])
        mean_w = sum(net_thermal_w_history) / len(net_thermal_w_history) if net_thermal_w_history else 0.0
        return -mean_w


def negative_mean_thermal_power_report(surface_name: str = "surface") -> ObjectiveSpec:
    """``-`` mean net thermal power over the run (W).

    REPORTING only — pass via ``Minimization(report_specs=[...])``, NOT
    ``objectives=``. Still shown (negated back to a human-friendly sign by
    ``DISPLAY_RENAME``) in ``pareto_results.csv``/the parallel-coordinates
    plot. Mirrors ``pymoo_api.negative_mean_power_objective`` exactly,
    reading ``history.net_thermal_W`` (direct-heat systems) instead of
    ``history.net_power_W`` (electric systems). See this module's own
    docstring for why this lives here rather than in ``pymoo_api.py``.
    """
    return ObjectiveSpec(
        name="negative_mean_thermal_power_W",
        evaluate=_NegativeMeanThermalPowerEvaluate(surface_name),
    )


def _production_well_outlet_temperature_c(wf: Workflow, well_name: str = "production_well") -> float:
    """Final-timestep production-well outlet temperature (degC).

    Matches ``run_AGS_direct_heat_sweep/sweep.py``'s own established
    convention exactly: the FINAL timestep's ``history.T_outlet`` (K) is
    the steady-state outlet, read after the run reached steady state, not
    a run-averaged mean like the power objectives above — a production-
    temperature THRESHOLD is a steady-state engineering criterion, not
    something meaningful to average over transient ramp-up.
    """
    well = wf._orchestrator.components[well_name]  # noqa: SLF001
    history = getattr(well, "history", None)
    t_outlet_k_history: list[float] = getattr(history, "T_outlet", [])
    if not t_outlet_k_history:
        return float("nan")
    return t_outlet_k_history[-1] - 273.15


_MIN_PRODUCTION_TEMPERATURE_C = 105.0
"""District-heating threshold — same value already used, informationally
only (post-hoc "qualified" flagging, never enforced), by
``run_AGS_direct_heat_sweep/plot.py``'s ``T_PROD_THRESHOLD_C`` and
``summarize.py``. This app's ``production_temperature_constraint`` is the
first place this threshold is actually ENFORCED during a search, not just
reported on afterward."""


@dataclass
class _ProductionTemperatureConstraintEvaluate:
    """Picklable ``ConstraintSpec.evaluate`` for ``production_temperature_constraint``."""

    well_name: str = "production_well"
    min_temperature_c: float = _MIN_PRODUCTION_TEMPERATURE_C

    def __call__(self, wf: Workflow) -> float:
        return self.min_temperature_c - _production_well_outlet_temperature_c(wf, self.well_name)


def production_temperature_constraint(
    well_name: str = "production_well",
    min_temperature_c: float = _MIN_PRODUCTION_TEMPERATURE_C,
) -> ConstraintSpec:
    """Reject designs whose final production-well outlet temperature is below ``min_temperature_c`` degC.

    Returns a genuine violation MAGNITUDE (degrees below the threshold),
    not just a flat sign — see ``ConstraintSpec``'s docstring for why that
    gives NSGA2 more signal than a binary feasible/infeasible flag would.
    """
    return ConstraintSpec(
        name="production_temperature_constraint",
        evaluate=_ProductionTemperatureConstraintEvaluate(well_name, min_temperature_c),
    )


@dataclass
class _NegativeProductionTemperatureEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` for ``negative_production_temperature_report``."""

    well_name: str = "production_well"

    def __call__(self, wf: Workflow) -> float:
        return -_production_well_outlet_temperature_c(wf, self.well_name)


def negative_production_temperature_report(well_name: str = "production_well") -> ObjectiveSpec:
    """``-`` final production-well outlet temperature (degC).

    REPORTING only — pass via ``Minimization(report_specs=[...])``, NOT
    ``objectives=``. Still shown (negated back to a human-friendly sign by
    ``DISPLAY_RENAME``) in ``pareto_results.csv``/the parallel-coordinates
    plot, alongside ``production_temperature_constraint``'s hard floor at
    105 degC, which remains the only thing actively enforced during the
    search.
    """
    return ObjectiveSpec(
        name="negative_production_temperature_C",
        evaluate=_NegativeProductionTemperatureEvaluate(well_name),
    )


# Single source of truth for the "negate for a human-friendly plot/print label"
# rename applied in main() — keyed off each objective's own ``.name`` rather
# than a second, independently-typed copy of that string, so a future rename
# of an objective itself can't silently desync from this.
DISPLAY_RENAME = {
    negative_mean_thermal_power_report().name: "mean_thermal_power_W",
    negative_production_temperature_report().name: "production_temperature_C",
}

# Full plot-axis display label for each column (parallel-coordinates plots)
# -- keyed on each column's DISPLAY name (post-DISPLAY_RENAME), not its
# raw/negated pymoo name. A full REPLACEMENT label, not a "name + [unit]"
# append -- several columns already carry their unit as a name suffix
# (mass_rate_kg_per_s, injection_pressure_Pa, depth_m, ...), and appending
# "[unit]" on top of that reads as redundant ("mass_rate_kg_per_s [kg/s]");
# stripping the suffix into a clean bracketed unit instead
# ("mass_rate [kg/s]") avoids that. LCOE/specific_investment_cost/OPEX/
# euclidean have no such suffix at all, so their bracket is pure addition,
# not a strip+replace. Columns absent here (design_number) show unchanged
# -- it's an index, not a physical quantity. Also carries the SAME
# par:/obj:/rep: category prefix ``Minimization._column_rename`` writes
# to the CSV (Chad's call, 2026-09-07: without it, a plot mixing decision
# variables, active objectives, and inert report_specs read-outs gives no
# way to tell which is which at a glance) -- euclidean stays bare here
# too, matching the CSV convention (it's neither a param, an objective,
# nor a report_specs value).
COLUMN_LABELS = {
    "depth_m": "par:depth [m]",
    "loop_length_m": "par:loop_length [m]",
    "loop_diameter_m": "par:loop_diameter [m]",
    "vertical_well_diameter_m": "par:vertical_well_diameter [m]",
    "injection_pressure_Pa": "par:injection_pressure [Pa]",
    "mass_rate_kg_per_s": "par:mass_rate [kg/s]",
    "LCOE": "obj:LCOE [$/kWh]",
    "mean_thermal_power_W": "rep:mean_thermal_power [W]",
    "production_temperature_C": "rep:production_temperature [°C]",
    "specific_investment_cost": "obj:specific_investment_cost [$/kW]",
    "OPEX": "rep:OPEX [$/yr]",
    "euclidean": "euclidean [z-score]",
}


def _pretty_label(label: str) -> str:
    """``"mass_rate [kg/s]"`` if ``label`` has a known display form (see ``COLUMN_LABELS``), else unchanged."""
    return COLUMN_LABELS.get(label, label)


# ---------------------------------------------------------------------------
# CLI / baseline / optimization — same shape as opt_hydro_df_electric.py
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """CLI for tuning the pymoo search — thin wrapper around
    ``pymoo_api.build_pymoo_parser``, the shared, non-domain-specific half
    (see its own docstring for why this lives in ``pymoo_api.py`` while
    ``ParamSpec``/``ObjectiveSpec`` do not), plus this app's one
    domain-specific flag.
    """
    parser = build_pymoo_parser(
        description="Multi-objective optimization demo for the AGS direct-heat example.",
        default_output_dir=DEFAULT_OUTPUT_DIR,
        params=load_params(PARAMS_FILE),
    )
    parser.add_argument(
        "--min-production-temperature-c",
        type=float,
        default=_MIN_PRODUCTION_TEMPERATURE_C,
        help=(
            "production_temperature_constraint's threshold (degC). Defaults to the real "
            f"district-heating requirement ({_MIN_PRODUCTION_TEMPERATURE_C}). A tiny "
            "population/generation budget (e.g. a smoke run) can legitimately find zero "
            "designs clearing the real threshold at random -- lower this instead of "
            "accepting an empty Pareto front, so a smoke run still exercises the full "
            "search + plotting pipeline against real, non-empty results (see justfile's "
            "demos recipe for the value it uses)."
        ),
    )
    return parser


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
        # depth_param(bounds=(2_000.0, 3_500.0)),
        depth_param(bounds=(2_000.0, 4_500.0)),
        # depth_param(bounds=(2_000.0, 5_500.0)),
        loop_length_param(bounds=(500.0, 8_000.0)),
        loop_diameter_param(bounds=(0.15, 0.75)),
        # Same range as loop_diameter_param — no other precedent to
        # match (the brute-force sweep never varies vertical-well
        # diameter independently), flagged for Chad to adjust if a
        # different casing-diameter range is more realistic.
        vertical_well_diameter_param(bounds=(0.2, 0.75)),
        injection_pressure_param(bounds=(0.5e6, 3.0e6)),
        mass_rate_param(bounds=(3.5, 50.0)),
    ]


def _objective_specs() -> list[ObjectiveSpec]:
    """Objectives: minimize LCOE, minimize specific investment cost — see
    ``_param_specs``' docstring for why this is its own function. Mean
    thermal power, production temperature, and OPEX are REPORTING only
    (see ``_report_specs``), not active objectives here.
    """
    return [
        lcoe_objective(),
        specific_investment_cost_objective(),
    ]


def _report_specs() -> list[ObjectiveSpec]:
    """Reporting-only read-outs: mean net thermal power, production-well
    outlet temperature, OPEX — computed once for the final pareto front,
    shown in ``pareto_results.csv``/the parallel-coordinates plot, but not
    fed to NSGA2 as objectives (see ``negative_mean_thermal_power_report``/
    ``negative_production_temperature_report``/``opex_report``'s own
    docstrings for why). See ``_param_specs``' docstring for why this is
    its own function.
    """
    return [negative_mean_thermal_power_report(), negative_production_temperature_report(), opex_report()]


def _constraint_specs(
    min_production_temperature_c: float = _MIN_PRODUCTION_TEMPERATURE_C,
) -> list[ConstraintSpec]:
    """Constraints beyond built-in physical feasibility: production-well
    outlet temperature must clear ``min_production_temperature_c`` — see
    ``_param_specs``' docstring for why this is its own function.
    """
    return [production_temperature_constraint(min_temperature_c=min_production_temperature_c)]


def run_optimization(
    base_wf: Workflow,
    args: argparse.Namespace,
) -> tuple[Result, pd.DataFrame, Minimization]:
    """Search depth + loop length + loop diameter + vertical well diameter +
    injection pressure + mass flow rate to minimize LCOE / minimize
    specific investment cost.

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
        constraints=_constraint_specs(args.min_production_temperature_c),
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


def plot_pareto_scatter(
    df: pd.DataFrame,
    out_path: Path,
    color_col: str = "production_temperature_C",
) -> None:
    """2D scatter of LCOE vs. mean net thermal power, colored by production temperature.

    LCOE and specific investment cost are this app's only active
    objectives (see ``_objective_specs``), but mean thermal power and
    production temperature (both reporting-only, see ``_report_specs``)
    are still the more physically meaningful axes for eyeballing the
    front, so this plot uses those instead of the raw objective pair. Two
    designs that trade off against the (invisible) third quantity shown
    only via color can look like one flat-out beats the other on both
    axes — a domination violation that isn't real, just an artifact of the
    projection: cheap+powerful designs in this front achieve that
    specifically by running closer to the production-temperature floor,
    while expensive+weak ones push temperature margin higher — a genuine
    trade-off, not a sign bug. Coloring by production temperature makes
    that trade-off visible instead of hiding it.
    """
    thermal_mw = df["mean_thermal_power_W"] / 1.0e6
    lcoe = df["LCOE"]
    color_values = df[color_col].to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(8, 6))
    sc = ax.scatter(lcoe, thermal_mw, s=40, c=color_values, cmap="viridis", zorder=3)
    xytext, ha = _diagonal_label_offset(lcoe, thermal_mw)
    for i, (x, y) in enumerate(zip(lcoe, thermal_mw, strict=True)):
        ax.annotate(str(i), (x, y), textcoords="offset points", xytext=xytext, ha=ha, fontsize=8)

    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label(_pretty_label(color_col))

    ax.set_xlabel("LCOE ($/kWh)")
    ax.set_ylabel("Mean net thermal power (MW)")
    ax.set_title("AGS_direct_heat — pareto front (objective space, color = production temperature)")
    ax.grid(visible=True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_pareto_scatter_zscore(
    df: pd.DataFrame,
    out_path: Path,
    color_col: str = "production_temperature_C",
) -> None:
    """Z-score-normalized variant of ``plot_pareto_scatter`` — see its docstring for the color choice."""
    lcoe = df["LCOE"]
    thermal = df["mean_thermal_power_W"]
    lcoe_z = (lcoe - lcoe.mean()) / (lcoe.std() or 1.0)
    thermal_z = (thermal - thermal.mean()) / (thermal.std() or 1.0)
    color_values = df[color_col].to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.axhline(0, color="grey", linewidth=0.8, zorder=1)
    ax.axvline(0, color="grey", linewidth=0.8, zorder=1)
    sc = ax.scatter(lcoe_z, thermal_z, s=40, c=color_values, cmap="viridis", zorder=3)
    xytext, ha = _diagonal_label_offset(lcoe_z, thermal_z)
    for i, (x, y) in enumerate(zip(lcoe_z, thermal_z, strict=True)):
        ax.annotate(str(i), (x, y), textcoords="offset points", xytext=xytext, ha=ha, fontsize=8)

    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label(_pretty_label(color_col))

    ax.set_xlabel("LCOE (z-score)")
    ax.set_ylabel("Mean net thermal power (z-score)")
    ax.set_title("AGS_direct_heat — pareto front (z-score, color = production temperature)")
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
        title="AGS_direct_heat — pareto front (interactive: drag along an axis to filter)",
        paper_bgcolor="#e8e8e8",
        plot_bgcolor="#e8e8e8",
        # Plotly's Parcoords has no axis-label-rotation option (unlike the
        # static matplotlib version's rotated labels) -- its default width
        # is a fixed ~700px regardless of dimension count, so with 12+
        # dimensions (params + objectives + report_specs + euclidean) and
        # unit-suffixed labels like "specific_investment_cost [$/kW]", the
        # labels run into each other. Scaling width by dimension count
        # (same 1.8x-per-column idea as the static plot's own
        # figsize=(1.8 * len(cols), ...)), just in pixels, gives each one
        # enough room -- an HTML file has no fixed viewport to fit, so a
        # wide, scrollable/zoomable figure is fine.
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

    Deliberately has no empty-``df`` guard: a genuinely empty Pareto front
    means the search found zero designs clearing every constraint, which
    is a real problem (bad bounds, an unsatisfiable constraint, or a bug)
    that should surface loudly here, not be silently skipped. A tiny
    population/generation budget that would otherwise hit this by chance
    (e.g. a smoke run) should relax its constraints instead — see
    ``build_parser``'s ``--min-production-temperature-c`` and the
    ``justfile``'s ``demos`` recipe.
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
        df = strip_column_prefixes(pd.read_csv(args.save_dir / "pareto_results.csv"))
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
