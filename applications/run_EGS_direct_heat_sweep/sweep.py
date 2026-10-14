"""Simulation sweep stage: run each (depth, mass-flow) design point in parallel.

Every design point re-reads ``EGS_direct_heat.yml`` fresh as a plain
dict (not ``Workflow.to_dict()``, which writes out every derived value and
would pin it at the base design's), mutates it, and
builds a brand-new ``Workflow`` from it — see ``Workflow``'s class docstring
(``src/tango/workflows/workflow.py``) for why a live ``Workflow``/
``Component`` must never be mutated in place. Re-reading from the YAML file
fresh in each worker (rather than passing a pre-built ``Workflow`` between
processes) also sidesteps any question of whether ``Workflow`` objects are
picklable — they never cross a process boundary here.

Every design point's config includes an ``economic:`` block
(``DoubletEconomicComponent``), so ``CAPEX_*_USD``/``LCOE_USD_per_kWh``/
``net_thermal_power_kW`` are read from ``wf.to_dict()["economic"]["state"]``
after ``wf.run()`` — the same access pattern the ``opt_*`` pymoo apps use.
These fields start ``None`` in the result dict below and only get
overwritten if the run succeeds, so a failed design point's JSON still has
every key present (for a uniform ``results.parquet`` schema) with an
``error`` block explaining why, rather than a null that could be misread as
"computed and unprofitable."

**thermal_power_kW vs. net_thermal_power_kW:** ``thermal_power_kW`` is the
physical quantity — ``surface.history.net_thermal_W`` (TESPy-solved district-
heating exchanger duty) at the final timestep, in kW. ``net_thermal_power_kW``
is the economic-accounting quantity — ``DoubletEconomicComponent``'s own
run-averaged ``net_thermal_W`` (see that class's ``_read_net_power``
docstring: unaffected by any parasitic-power netting for this topology, so
in practice it's close to but not necessarily identical to
``thermal_power_kW``, since one is a final-timestep read and the other a
whole-run average).

**No ``_apply_target_extraction_pressure`` here** — unlike the AGS
direct-heat sweep, this topology has no depth-scaled
target-extraction-pressure function at all; the base YAML's fixed
``surface.target_extraction_pressure: 7_000_000`` is used unchanged across
the whole depth sweep.

**Thread oversubscription fix (2026-08-17):** each of the ``n_workers``
worker PROCESSES (spawned by ``multiprocessing.Pool`` in ``run_sweep``)
independently lets ``polars``/OpenBLAS spin up their OWN internal thread
pool sized to every available core, unaware they're one of many sibling
workers. With ``n_workers`` in the dozens, that's ``n_workers`` times as
many threads as cores — confirmed the hard way on a real Euler run
(2026-08-17): 45 workers each defaulting to ~48 threads blew through the
cluster's ``RLIMIT_NPROC`` (4096), and ``polars.read_parquet``/the
``polars-stream`` async executor (called by every worker at startup) was
what finally tripped a Rust panic, crashing worker processes mid-sweep.
The env vars below cap every thread-pool-owning library to 1 thread per
process *before* any of them get imported (spawned workers re-run this
module's top-level code from scratch under the 'spawn' start method, so
setting these here applies to every worker, not just this main process) —
the outer ``multiprocessing.Pool`` is already the parallelism; no worker
needs its own internal multithreading on top of it.
"""

from __future__ import annotations

import os

os.environ.setdefault("POLARS_MAX_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import argparse
import json
import multiprocessing
import sys
import tempfile
import traceback
from pathlib import Path

import polars as pl
import yaml
from common import (
    BASE_YAML,
    DEFAULT_LOG_LEVEL,
    DEFAULT_N_WORKERS,
    DEFAULT_SWEEP_DIR,
    load_params,
    set_nested_value,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from tango.pymoo_api import INFEASIBLE_DESIGN_EXCEPTIONS  # noqa: E402
from tango.workflows.workflow import Workflow  # noqa: E402


def _apply_depth(cfg: dict, depth_m: float) -> None:
    """Set the reservoir depth and the pump setting depth (20% of it) in-place on a config dict.

    Everything else that follows depth (the injection well's length, the
    lower production segment's length and starting depth, and
    ``hydro_static_pressure``) is derived from these two
    (``tango.workflows.linked_quantities``).
    """
    set_nested_value(cfg, "components.reservoir.reservoir_depth", depth_m)
    set_nested_value(cfg, "components.production_well_upper.well_length", 0.2 * depth_m)


def _apply_mass_flow(cfg: dict, mdot: float) -> None:
    """Update the mass flow rate in-place (sim_config.mass_rate)."""
    set_nested_value(cfg, "sim_config.mass_rate", mdot)


def run_single_simulation(args: tuple) -> None:
    """Worker: run one (depth, mass-flow) design point and write a JSON result file."""
    row_idx, design_matrix_file, results_dir, _log_level = args
    result_file = results_dir / f"{row_idx:06d}.json"
    if result_file.exists():
        return

    df = pl.read_parquet(design_matrix_file)
    row = df.filter(pl.col("row_idx") == row_idx).to_dicts()[0]
    depth_m: float = row["well_depth_m"]
    mdot: float = row["mass_flow_kg_per_s"]

    result: dict = {
        "row_idx": row_idx,
        "well_depth_m": depth_m,
        "mass_flow_kg_per_s": mdot,
        # Physics outputs
        "T_prod_K": None,
        "T_prod_C": None,
        "T_inj_K": None,
        "specific_enthalpy_kJ_kg": None,
        "thermal_power_kW": None,
        # CAPEX components [USD] — filled in from DoubletEconomicComponent's
        # state below if the run succeeds; stays None on a failed design
        # point (see module docstring).
        "CAPEX_well_USD": None,
        "CAPEX_exploration_USD": None,
        "CAPEX_permitting_USD": None,
        "CAPEX_surface_pipes_USD": None,
        "CAPEX_surface_plant_USD": None,
        "CAPEX_total_USD": None,
        # Economic metrics — same as above.
        "LCOE_USD_per_kWh": None,
        "net_thermal_power_kW": None,
        # Simulation status
        "error": None,
    }

    try:
        # Fresh Workflow every design point — never mutate a live Workflow;
        # Config dict as written in the YAML (not Workflow.to_dict(), which
        # writes out every derived value and would pin it at the base
        # design's), mutated, then Workflow(cfg).
        cfg = yaml.safe_load(BASE_YAML.read_text())

        _apply_depth(cfg, depth_m)
        _apply_mass_flow(cfg, mdot)

        wf = Workflow(cfg)
        wf.run()

        orch = wf._orchestrator
        # production_well_upper = the pump/upper segment, adjacent to the
        # surface plant (not production_well_lower, which is the
        # reservoir-adjacent segment further downhole).
        prod = orch.components["production_well_upper"]
        surface = orch.components["surface"]

        # Final-timestep production-well outlet temperature — steady-state
        # outlet, read after the run reached steady state (the last
        # recorded history entry).
        T_prod_K: float = prod.history.T_outlet[-1]

        # Injection temperature = surface outlet, last recorded timestep. The DH heat
        # exchanger's T_out is a hard TESPy connection constraint, not an
        # effectiveness model, so a converged solve always produces exactly
        # the configured return temperature here.
        T_inj_K: float = surface.history.T_outlet[-1]

        # Thermal power: tango computes this correctly already (mdot *
        # actual enthalpy drop across dh_hx, solved by TESPy) — no manual
        # CoolProp Δh estimate needed.
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

        econ_state = wf.to_dict()["economic"]["state"]
        result["CAPEX_well_USD"] = econ_state["CAPEX_well"]
        result["CAPEX_exploration_USD"] = econ_state["CAPEX_exploration"]
        result["CAPEX_permitting_USD"] = econ_state["CAPEX_permitting"]
        result["CAPEX_surface_pipes_USD"] = econ_state["CAPEX_surface_pipes"]
        result["CAPEX_surface_plant_USD"] = econ_state["CAPEX_surface_plant"]
        result["CAPEX_total_USD"] = econ_state["CAPEX_total"]
        result["LCOE_USD_per_kWh"] = econ_state["LCOE"]
        result["net_thermal_power_kW"] = econ_state["net_thermal_W"] / 1000.0

    # Only the errors that mean "this design doesn't work" (fracking, a failed
    # fluid-property lookup, non-convergence, ...) are recorded as a failed
    # design. Anything else is a bug and stops the sweep, instead of being
    # recorded once per design.
    except INFEASIBLE_DESIGN_EXCEPTIONS as e:
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
        allow_abbrev=False,
        description="Run tango Triemli EGS direct-heat sweep simulations",
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
