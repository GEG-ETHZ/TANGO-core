"""Simulation sweep stage: run each (depth, mass-flow, loop-length, loop-diameter) design point in parallel.

tango_next port of ``applications/run_AGS_direct_heat_sweep/sweep.py``. The
parameter-mutation mechanics are entirely different from the old-tango
version: instead of mutating a live ``Runner.tango.specs`` dict in place,
every design point re-reads ``AGS_direct_heat.yml`` fresh
(``Workflow.from_file(BASE_YAML).to_dict()``), mutates a plain dict copy, and
builds a brand-new ``Workflow`` from it — see ``Workflow``'s class docstring
(``src/tango_next/workflows/workflow.py``) for why a live ``Workflow``/
``Component`` must never be mutated in place. Re-reading from the YAML file
fresh in each worker (rather than passing a pre-built ``Workflow`` between
processes) also sidesteps any question of whether ``Workflow`` objects are
picklable — they never cross a process boundary here.

**No economic component in tango_next yet** (Phase 1): ``EconomicComponent``
is an unwired placeholder — nothing reads ``economic:`` in the YAML, and
CAPEX/LCOE cannot be computed. Every CAPEX_*/LCOE_* field below is set to
``None`` explicitly, not omitted or silently dropped, so a null does not read
as "the plant is unprofitable" — it means "not computed in this phase."

**thermal_power_kW / net_thermal_power_kW naming, deviating from old tango's
literal field semantics:** old tango's ``thermal_power_kW`` was a
hand-computed ``mdot * (h_prod - h_return)`` estimate, and its
``net_thermal_power_kW`` came from the *economic* unit's
``Net_thermal_power_Generated_kWe`` (pump-parasitic-load-adjusted, an
economic-accounting quantity). tango_next's ``GraphSurface`` computes the
district-heating heat exchanger's actual duty directly and correctly via
TESPy (``surface.history.net_thermal_W``, already in watts, already
``mdot * actual enthalpy drop`` — no manual CoolProp Δh estimate needed) but
has no economic component to compute a pump-loss-adjusted net figure. So
here: ``thermal_power_kW`` (the physical, always-available quantity) is
populated from ``net_thermal_W``, replacing old tango's manual estimate with
the more accurate TESPy-computed one; ``net_thermal_power_kW`` (the
economic-accounting quantity) is ``None``, consistent with every other
economic field, since nothing computes it yet.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
import tempfile
import traceback
from pathlib import Path

import CoolProp.CoolProp as CP
import polars as pl
from common import (
    BASE_YAML,
    DEFAULT_LOG_LEVEL,
    DEFAULT_N_WORKERS,
    DEFAULT_SWEEP_DIR,
    load_params,
    set_nested_value,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from tango_next.workflows.workflow import Workflow  # noqa: E402

# Floor value: AGS_direct_heat.yml's original fixed target_extraction_pressure,
# which was valid at every depth up to 7500 m (see _apply_target_extraction_pressure,
# ported from old tango's identically-named function/rationale). Keeping it as
# the floor means depths that were already valid before the 8000 m extension
# get byte-for-byte the same target_extraction_pressure as before, and only
# the newly-added 8000 m tier's value actually changes.
_TARGET_EXTRACTION_PRESSURE_FLOOR_PA = 7_000_000.0
_TARGET_EXTRACTION_PRESSURE_SAFETY_FACTOR = 1.2


def _apply_depth(cfg: dict, depth_m: float) -> None:
    """Update all depth-dependent parameters in-place on a config dict.

    For the AGS topology (injection_well -> horizontal_well -> production_well),
    depth controls the vertical sections only; loop length is a separate axis
    (see _apply_loop_length). Mirrors old tango's _apply_depth, translated to
    tango_next's nested components.<name>.<field> paths.
    """
    set_nested_value(cfg, "components.injection_well.well_length", depth_m)
    set_nested_value(cfg, "components.horizontal_well.wellhead_depth", depth_m)
    set_nested_value(cfg, "components.production_well.well_length", depth_m)


def _apply_target_extraction_pressure(cfg: dict, depth_m: float) -> None:
    """Scale surface.target_extraction_pressure with well depth so it stays
    physically valid across the whole depth sweep.

    Ported from old tango's identically-named function
    (applications/run_AGS_direct_heat_sweep/sweep.py) — same formula, same
    floor/safety-factor rationale, reading common.surface_temperature /
    common.thermal_gradient / common.fluid_name from the tango_next config
    dict instead of old tango's specs["surface"]/specs["props"]. Without
    this, deep designs would have a plant-inlet pressure below the fluid's
    saturation pressure at the estimated plant-inlet temperature
    (surface_temperature + depth * thermal_gradient), i.e. the fluid would
    flash to vapor at the plant inlet — a real physical constraint.
    """
    surface_temp_K = cfg["common"]["surface_temperature"]
    thermal_gradient = cfg["common"]["thermal_gradient"]
    fluid_name = cfg["common"]["fluid_name"]
    te_pp_in_est_K = surface_temp_K + depth_m * thermal_gradient
    p_sat = CP.PropsSI("P", "T", te_pp_in_est_K, "Q", 0, fluid_name)
    required = p_sat * _TARGET_EXTRACTION_PRESSURE_SAFETY_FACTOR
    target = max(_TARGET_EXTRACTION_PRESSURE_FLOOR_PA, required)
    set_nested_value(cfg, "components.surface.target_extraction_pressure", target)


def _apply_loop_length(cfg: dict, loop_length_m: float) -> None:
    """Update the horizontal loop length in-place.

    well_spacing must equal the horizontal loop length by convention (see
    AGS_direct_heat.yml's layout.well_spacing / components.surface.well_spacing
    comments) — all three are updated together, mirroring old tango's
    _apply_loop_length (horizontal_well.well_length + schedule.well_spacing).
    """
    set_nested_value(cfg, "components.horizontal_well.well_length", loop_length_m)
    set_nested_value(cfg, "layout.well_spacing", loop_length_m)
    set_nested_value(cfg, "components.surface.well_spacing", loop_length_m)


def _apply_loop_diameter(cfg: dict, loop_diameter_m: float) -> None:
    """Update the horizontal loop diameter in-place.

    Only horizontal_well.diameter is swept, matching old tango's
    _apply_loop_diameter — injection_well/production_well diameters
    (vertical sections) are left at the base YAML's fixed 0.311 m casing
    assumption, unrelated to this axis.
    """
    set_nested_value(cfg, "components.horizontal_well.diameter", loop_diameter_m)


def _apply_mass_flow(cfg: dict, mdot: float) -> None:
    """Update the mass flow rate in-place (sim_config.mass_rate)."""
    set_nested_value(cfg, "sim_config.mass_rate", mdot)


def run_single_simulation(args: tuple) -> None:
    """Worker: run one (depth, mass-flow, loop-length, loop-diameter) design point and write a JSON result file."""
    row_idx, design_matrix_file, results_dir, _log_level = args
    result_file = results_dir / f"{row_idx:06d}.json"
    if result_file.exists():
        return

    df = pl.read_parquet(design_matrix_file)
    row = df.filter(pl.col("row_idx") == row_idx).to_dicts()[0]
    depth_m: float = row["well_depth_m"]
    mdot: float = row["mass_flow_kg_s"]
    loop_length_m: float = row["loop_length_m"]
    loop_diameter_m: float = row["loop_diameter_m"]

    result: dict = {
        "row_idx": row_idx,
        "well_depth_m": depth_m,
        "mass_flow_kg_s": mdot,
        "loop_length_m": loop_length_m,
        "loop_diameter_m": loop_diameter_m,
        # Physics outputs
        "T_prod_K": None,
        "T_prod_C": None,
        "T_inj_K": None,
        "specific_enthalpy_kJ_kg": None,
        "thermal_power_kW": None,
        # CAPEX components [USD] — None: no EconomicComponent wired up yet in
        # tango_next (Phase 1); see module docstring.
        "CAPEX_well_USD": None,
        "CAPEX_exploration_USD": None,
        "CAPEX_permitting_USD": None,
        "CAPEX_surface_pipes_USD": None,
        "CAPEX_surface_plant_USD": None,
        "CAPEX_total_USD": None,
        # Economic metrics — None for the same reason.
        "LCOE_USD_per_kWh": None,
        "net_thermal_power_kW": None,
        # Simulation status
        "error": None,
    }

    try:
        # Fresh Workflow every design point — never mutate a live Workflow;
        # cfg = base_wf.to_dict() then mutate the plain dict then Workflow(cfg).
        base_wf = Workflow.from_file(BASE_YAML)
        cfg = base_wf.to_dict()

        _apply_depth(cfg, depth_m)
        _apply_target_extraction_pressure(cfg, depth_m)
        _apply_loop_length(cfg, loop_length_m)
        _apply_loop_diameter(cfg, loop_diameter_m)
        _apply_mass_flow(cfg, mdot)

        wf = Workflow(cfg)
        wf.run()

        orch = wf._orchestrator
        prod = orch.components["production_well"]
        surface = orch.components["surface"]

        # Final-timestep production-well outlet temperature — steady-state
        # outlet, matching old tango's semantics (prod_unit.outlet_fluid.T
        # there was read after the run reached steady state; here the
        # equivalent is the last recorded history entry).
        T_prod_K: float = prod.history.T_outlet[-1]

        # Injection temperature = surface outlet (live read). The DH heat
        # exchanger's T_out is a hard TESPy connection constraint, not an
        # effectiveness model, so a converged solve always produces exactly
        # the configured return temperature here — verified equivalent
        # reasoning to old tango's sweep.py (applications/
        # run_AGS_direct_heat_sweep/sweep.py), whose comment documents the
        # same fact for the old native DH heat exchanger node.
        T_inj_K: float = surface.outlet.T

        # Thermal power: tango_next computes this correctly already (mdot *
        # actual enthalpy drop across dh_hx, solved by TESPy) — no manual
        # CoolProp Δh estimate needed, unlike old tango. See module
        # docstring for why this populates thermal_power_kW (not
        # net_thermal_power_kW, which stays None pending the economic
        # component).
        net_thermal_W = surface.history.net_thermal_W[-1]
        thermal_power_kW = net_thermal_W / 1000.0

        # Specific enthalpy, for informational purposes only — derived from
        # the already-correct thermal power rather than a second, possibly
        # slightly-inconsistent FluidState h_prod - h_return calculation.
        specific_enthalpy_kJ_kg = thermal_power_kW / mdot if mdot > 0 else float("nan")

        result["T_prod_K"] = T_prod_K
        result["T_prod_C"] = T_prod_K - 273.15
        result["T_inj_K"] = T_inj_K
        result["specific_enthalpy_kJ_kg"] = specific_enthalpy_kJ_kg
        result["thermal_power_kW"] = thermal_power_kW

    except Exception as e:
        result["error"] = {
            "type": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc(),
        }

    # Atomic write
    results_dir.mkdir(exist_ok=True, parents=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=results_dir, delete=False, suffix=".tmp") as f:
        json.dump(result, f, indent=2)
        tmp_path = Path(f.name)
    tmp_path.rename(result_file)


def run_sweep(
    design_matrix_file: Path,
    results_dir: Path,
    n_workers: int,
    log_level: str = DEFAULT_LOG_LEVEL,
    quiet: bool = False,
    progress_interval: int | None = None,
) -> None:
    """Execute pending design points in parallel, writing one JSON per result."""
    df = pl.read_parquet(design_matrix_file)
    n_total = len(df)
    completed = {int(f.stem) for f in results_dir.glob("*.json")}
    pending = [i for i in range(n_total) if i not in completed]

    if not quiet:
        print(f"Sweep: {len(completed)}/{n_total} done, {len(pending)} pending")
    if not pending:
        if not quiet:
            print("All simulations complete.")
        return

    worker_args = [(idx, design_matrix_file, results_dir, log_level) for idx in pending]
    interval = progress_interval if progress_interval is not None else max(1, n_workers)

    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(n_workers) as pool:
        done = 0
        for _ in pool.imap_unordered(run_single_simulation, worker_args):
            done += 1
            if not quiet and done % interval == 0:
                print(f"  {done}/{len(pending)} completed")
        if not quiet and done % interval != 0:
            print(f"  {done}/{len(pending)} completed")

    if not quiet:
        print("Sweep complete.")


def main(
    n_workers: int = DEFAULT_N_WORKERS,
    log_level: str = DEFAULT_LOG_LEVEL,
    quiet: bool = False,
    progress_interval: int | None = None,
    sweep_dir: Path | None = None,
) -> None:
    """Run the sweep stage from the default sweep directory."""
    sweep_dir = sweep_dir or DEFAULT_SWEEP_DIR
    run_sweep(
        design_matrix_file=sweep_dir / "design_matrix.parquet",
        results_dir=sweep_dir / "results",
        n_workers=n_workers,
        log_level=log_level,
        quiet=quiet,
        progress_interval=progress_interval,
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    params = load_params()
    parser = argparse.ArgumentParser(
        description="Run tango_next Triemli direct-heat sweep simulations",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--n-workers", type=int, default=params.get("n_workers", DEFAULT_N_WORKERS))
    parser.add_argument(
        "--log-level",
        type=str,
        default=params.get("log_level", DEFAULT_LOG_LEVEL),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "NONE"],
    )
    parser.add_argument("--quiet", "-q", action="store_true")
    parser.add_argument("--progress-interval", type=int, default=None)
    parser.add_argument("--sweep-dir", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(
        n_workers=args.n_workers,
        log_level=args.log_level,
        quiet=args.quiet,
        progress_interval=args.progress_interval,
        sweep_dir=args.sweep_dir,
    )
