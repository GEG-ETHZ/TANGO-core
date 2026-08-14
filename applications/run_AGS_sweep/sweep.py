"""Simulation sweep stage: run each (depth, mass-flow, loop-length, loop-diameter) design point in parallel.

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
!!! DO NOT TRUST MULTI-TIMESTEP RESULTS FROM THIS SWEEP (confirmed 2026-08-01) !!!
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
Every design point here is an AGS config (horizontal_well, no reservoir),
which src/tango/utils.py::system_name() (~line 875-876) silently routes to
the SystemNative orchestrator (src/tango/orchestrators/native.py:14-77) —
its update_time_dependent_vars()/update()/balanced() are literal no-op
placeholders. NOTHING advances between timesteps: every design point's
multi-timestep run repeats the SAME solved state at every timestep after
t=0. Any apparent decline over time in this sweep's output is NOT REAL
PHYSICS. See docs/tango_next_tasks.md's "AGS_direct_heat.yml parity" entry
(section 4) for the full root-cause trace and status. NOT YET FIXED.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
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

from tango.runner import Runner

# Floor value: triemli_dh_base.yml's original fixed target_extraction_pressure,
# which was valid at every depth up to 7500 m (see _apply_target_extraction_pressure).
# Keeping it as the floor means depths that were already valid before the
# 8000 m extension get byte-for-byte the same target_extraction_pressure as
# before, and only the newly-added 8000 m tier's value actually changes.
_TARGET_EXTRACTION_PRESSURE_FLOOR_PA = 7_000_000.0
_TARGET_EXTRACTION_PRESSURE_SAFETY_FACTOR = 1.2


def _apply_depth(specs: dict, depth_m: float) -> None:
    """Update all depth-dependent parameters in-place.

    For the AGS topology (injection_well → horizontal_well → production_well),
    depth controls the vertical sections only; loop length is a separate axis
    (see _apply_loop_length).

    Parameters updated:
      - injection_well.well_length (and _seq)  — vertical descent = depth
      - horizontal_well.wellhead_depth          — loop sits at bottom of vertical section
      - production_well.well_length (and _seq) — vertical ascent = depth (symmetric)
    """
    set_nested_value(specs, "injection_well.well_length", depth_m)
    set_nested_value(specs, "injection_well.well_length_seq", [depth_m])

    set_nested_value(specs, "horizontal_well.wellhead_depth", depth_m)

    set_nested_value(specs, "production_well.well_length", depth_m)
    set_nested_value(specs, "production_well.well_length_seq", [depth_m])


def _apply_target_extraction_pressure(specs: dict, depth_m: float) -> None:
    """Scale surface.target_extraction_pressure with well depth so it stays
    physically valid across the whole depth sweep.

    Ported unchanged from the sibling direct-heat sweep, where
    SurfaceUnitFlexiblePP.validate_custom() (src/tango/units/native/surface/
    flexible_pp.py) requires target_extraction_pressure to exceed the
    saturation pressure at the estimated plant-inlet temperature
    (surface_temperature + depth * thermal_gradient — same formula the
    validator itself uses, replicated here). This sweep's surface unit is
    native_ORC (SurfaceUnitORCNative, src/tango/units/native/surface/ORC.py)
    instead, which — confirmed by inspection — has no validate_custom() at
    all, so there is no equivalent upfront ValidationError gating this for
    the ORC path. The underlying physical concern is not surface-unit
    specific, though: if target_extraction_pressure is set below the
    saturation pressure at the plant inlet, the fluid flashes to vapor
    before reaching the plant, which is unphysical regardless of which
    surface unit consumes target_extraction_pressure downstream (it's read
    generically as a pump setpoint in
    src/tango/orchestrators/BC_calculator.py, not only by the flexible_pp
    validator). Kept as a protective measure so the deepest (8000 m) tier
    doesn't silently produce a flashing/invalid plant-inlet state without
    an explicit error to catch it — see "8000 m depth tier needed
    target_extraction_pressure to scale with depth" in the sibling
    run_AGS_direct_heat_sweep.py's docstring for the original bug this
    fixed there.

    Floor at the original fixed value (not just at the computed minimum)
    so every depth that was already valid keeps exactly the same
    target_extraction_pressure as before this axis existed; only the newly
    invalid tier's value actually changes. The 1.2x safety factor is applied
    on top of the raw saturation pressure, not the validator's own 1.01x
    warn threshold, for real engineering margin rather than just clearing
    the check.
    """
    surface_temp_K = specs["surface"]["surface_temperature"]
    thermal_gradient = specs["props"]["thermal_gradient"]
    fluid_name = specs["props"]["fluid_name"]
    te_pp_in_est_K = surface_temp_K + depth_m * thermal_gradient
    p_sat = CP.PropsSI("P", "T", te_pp_in_est_K, "Q", 0, fluid_name)
    required = p_sat * _TARGET_EXTRACTION_PRESSURE_SAFETY_FACTOR
    target = max(_TARGET_EXTRACTION_PRESSURE_FLOOR_PA, required)
    set_nested_value(specs, "surface.target_extraction_pressure", target)


def _apply_loop_length(specs: dict, loop_length_m: float) -> None:
    """Update the horizontal loop length in-place.

    well_spacing must equal the horizontal loop length by convention (see
    horizontal_well.py's Inconsistent well_spacing/length warning) — both are
    updated together.
    """
    set_nested_value(specs, "horizontal_well.well_length", loop_length_m)
    set_nested_value(specs, "horizontal_well.well_length_seq", [loop_length_m])
    set_nested_value(specs, "schedule.well_spacing", loop_length_m)


def _apply_loop_diameter(specs: dict, loop_diameter_m: float) -> None:
    """Update the horizontal loop diameter in-place.

    Only horizontal_well.diameter is swept, per the original TODO ("loop
    diameter (horizontal_well.diameter)") — injection_well/production_well
    diameters (vertical sections) are left at the base YAML's fixed 0.311 m
    casing assumption, unrelated to this axis.
    """
    set_nested_value(specs, "horizontal_well.diameter", loop_diameter_m)
    set_nested_value(specs, "horizontal_well.well_diameter_seq", [loop_diameter_m])


def _apply_mass_flow(specs: dict, mdot: float) -> None:
    """Update all mass-flow-rate parameters in-place (both schedule keys)."""
    set_nested_value(specs, "schedule.mass_flow_rate", mdot)
    set_nested_value(specs, "schedule.mass_rate.value", mdot)


def run_single_simulation(args: tuple) -> None:
    """Worker: run one (depth, mass-flow, loop-length, loop-diameter) design point and write a JSON result file."""
    row_idx, design_matrix_file, results_dir, log_level = args
    result_file = results_dir / f"{row_idx:06d}.json"
    if result_file.exists():
        return

    df = pl.read_parquet(design_matrix_file)
    row = df.filter(pl.col("row_idx") == row_idx).to_dicts()[0]
    depth_m: float = row["well_depth_m"]
    mdot: float = row["mass_flow_kg_per_s"]
    loop_length_m: float = row["loop_length_m"]
    loop_diameter_m: float = row["loop_diameter_m"]

    runner = Runner(input_file=BASE_YAML, no_save=True, log_level=log_level)

    result: dict = {
        "row_idx": row_idx,
        "well_depth_m": depth_m,
        "mass_flow_kg_per_s": mdot,
        "loop_length_m": loop_length_m,
        "loop_diameter_m": loop_diameter_m,
        # Physics outputs
        "T_prod_K": None,
        "T_prod_C": None,
        # CAPEX components [USD]
        "CAPEX_well_USD": None,
        "CAPEX_exploration_USD": None,
        "CAPEX_permitting_USD": None,
        "CAPEX_surface_pipes_USD": None,
        "CAPEX_surface_plant_USD": None,
        "CAPEX_total_USD": None,
        # Economic metrics
        # No gross electric power figure exists in economic.py's _results
        # (only Net_Electricity_Generated_kWe / Net_thermal_power_Generated_kWe
        # — checked economic.py's _compute()/_compute_LCOE() fully), so it's
        # omitted here rather than fabricated.
        "LCOE_USD_per_kWh": None,
        "net_electric_power_kW": None,
        # Simulation status
        "error": None,
    }

    try:
        _apply_depth(runner.tango.specs, depth_m)
        _apply_target_extraction_pressure(runner.tango.specs, depth_m)
        _apply_loop_length(runner.tango.specs, loop_length_m)
        _apply_loop_diameter(runner.tango.specs, loop_diameter_m)
        _apply_mass_flow(runner.tango.specs, mdot)
        runner.update_parameters()
        runner.start()

        # --- Production-well outlet ---
        orch = runner.tango.workflow.orchestrator
        prod_unit = getattr(orch.unit, "production_well", None)

        if prod_unit is not None and hasattr(prod_unit, "outlet_fluid"):
            T_prod_K: float = prod_unit.outlet_fluid.T
        else:
            T_prod_K = float("nan")

        result["T_prod_K"] = T_prod_K
        result["T_prod_C"] = T_prod_K - 273.15

        # --- Economic results ---
        eco = runner.tango.workflow.economic
        if eco is not None:
            er = eco._results
            result["CAPEX_well_USD"] = er.get("CAPEX_well")
            result["CAPEX_exploration_USD"] = er.get("CAPEX_exploration")
            result["CAPEX_permitting_USD"] = er.get("CAPEX_permitting")
            result["CAPEX_surface_pipes_USD"] = er.get("CAPEX_surface_gathering_system")
            result["CAPEX_surface_plant_USD"] = er.get("CAPEX_surface_plant")
            result["CAPEX_total_USD"] = er.get("CAPEX_total")
            net_electric_power_kW = er.get("Net_Electricity_Generated_kWe")  # kW_e
            result["net_electric_power_kW"] = net_electric_power_kW

            lcoe = er.get("LCOE")
            # LCOE = CAPEX / net_power. When net_electric_power_kW <= 0
            # (parasitic pumping and/or generator load exceeds gross ORC
            # output — a real outcome for marginal designs near the
            # threshold where the working fluid barely clears the ORC's
            # own extraction requirements, not a simulation error), this
            # ratio is undefined, not merely large: the plant isn't
            # producing the product LCOE prices in the first place.
            # Dividing CAPEX by a negative number flips the sign, producing
            # a nonsensical negative "cost." NaN (not +inf) is the honest
            # representation — +inf would imply a diminishing-returns limit
            # as net power shrinks toward zero from above, which isn't what's
            # happening here, and NaN is skipped by default in
            # mean/percentile aggregations downstream (summarize.py, plot.py)
            # instead of corrupting them the way +inf would.
            if net_electric_power_kW is not None and net_electric_power_kW <= 0:
                lcoe = None
            result["LCOE_USD_per_kWh"] = lcoe

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
        description="Run Triemli AGS power-generation sweep simulations",
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
