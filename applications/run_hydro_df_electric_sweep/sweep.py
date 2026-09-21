"""Simulation sweep stage: run each one-at-a-time design point in parallel.

Every design point re-reads ``hydro_df_electric.yml`` fresh
(``Workflow.from_file(BASE_YAML).to_dict()``), mutates a plain dict copy
using the scale factors read per-row from the design matrix (see
``generate.py`` for how those rows are built), and builds a brand-new
``Workflow`` from it — see ``Workflow``'s class docstring
(``src/tango/workflows/workflow.py``) for why a live ``Workflow``/
``Component`` must never be mutated in place. Re-reading from the YAML file
fresh in each worker (rather than passing a pre-built ``Workflow`` between
processes) also sidesteps any question of whether ``Workflow`` objects are
picklable — they never cross a process boundary here.

Every design point's config includes an ``economic:`` block
(``DoubletEconomicComponent``), so ``LCOE_USD_per_kWh``/``CAPEX_*_USD`` are
read from ``wf.to_dict()["economic"]["state"]`` after ``wf.run()`` — the
same access pattern the ``opt_*`` pymoo apps use, supporting this sweep's
actual point (an LCOE sensitivity check). ``net_power_W`` (the double-flash
topology's actual TESPy-solved net electric power, read from
``surface.history.net_power_W[-1]``) and ``T_prod_K`` (from
``production_well_upper.history.T_outlet[-1]``) are still tracked as
before — physical quantities, distinct from ``DoubletEconomicComponent``'s
own run-averaged, parasitic-netted net electric power (see that class's
``_read_net_power`` docstring), which isn't separately recorded here.
``swept_param``/``level`` are copied straight through from the design
matrix row (see ``generate.py``) so ``summarize.py`` can group results by
which single parameter each design point actually varied.

**Thread oversubscription fix (2026-08-17):** each of the ``n_workers``
worker PROCESSES (spawned by ``multiprocessing.Pool`` in ``run_sweep``)
independently lets ``polars``/OpenBLAS spin up their OWN internal thread
pool sized to every available core, unaware they're one of many sibling
workers. With ``n_workers`` in the dozens, that's ``n_workers`` times as
many threads as cores — confirmed the hard way on a real Euler run
(2026-08-17): 45 workers each defaulting to ~48 threads blew through the
cluster's ``RLIMIT_NPROC`` (4096), and ``polars.read_parquet`` (called by
every worker at startup) was what finally tripped a Rust panic
(`ThreadPoolBuildError`), crashing worker processes mid-sweep. The env
vars below cap every thread-pool-owning library to 1 thread per process
*before* any of them get imported (spawned workers re-run this module's
top-level code from scratch under the 'spawn' start method, so setting
these here applies to every worker, not just this main process) — the
outer ``multiprocessing.Pool`` is already the parallelism; no worker needs
its own internal multithreading on top of it.
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
from common import (
    BASE_YAML,
    DEFAULT_LOG_LEVEL,
    DEFAULT_N_WORKERS,
    DEFAULT_SWEEP_DIR,
    PARAMETERS,
    get_nested_value,
    load_params,
    set_nested_value,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from tango.workflows.workflow import Workflow  # noqa: E402


def _sync_injection_well_length(cfg: dict) -> None:
    """Sync injection well length to the (scaled) sum of the two production well segments.

    Sets ``injection_well.well_length = production_well_lower.well_length
    + production_well_upper.well_length`` after all scale factors are
    applied, i.e. total injection depth = sum of the two production well
    segments post-scaling. The sampled scale factor for
    ``injection_well.well_length`` itself is thrown away — which is why
    it isn't in ``PARAMETER_BOUNDS`` at all here (see common.py's
    docstring).
    """
    prod_len = get_nested_value(cfg, "components.production_well_lower.well_length")
    pump_len = get_nested_value(cfg, "components.production_well_upper.well_length")
    set_nested_value(cfg, "components.injection_well.well_length", prod_len + pump_len)


def run_single_simulation(args: tuple) -> None:
    """Worker: run one one-at-a-time design point and write a JSON result file."""
    row_idx, design_matrix_file, results_dir, _log_level = args
    result_file = results_dir / f"{row_idx:06d}.json"
    if result_file.exists():
        return

    df = pl.read_parquet(design_matrix_file)
    row = df.filter(pl.col("row_idx") == row_idx).to_dicts()[0]

    result: dict = {
        "row_idx": row_idx,
        "swept_param": row["swept_param"],
        "level": row["level"],
        "net_power_W": None,
        "T_prod_K": None,
        # CAPEX components [USD] — filled in from DoubletEconomicComponent's
        # state below if the run succeeds; stays None on a failed design
        # point (see module docstring).
        "CAPEX_well_USD": None,
        "CAPEX_exploration_USD": None,
        "CAPEX_permitting_USD": None,
        "CAPEX_surface_pipes_USD": None,
        "CAPEX_surface_plant_USD": None,
        "CAPEX_total_USD": None,
        "LCOE_USD_per_kWh": None,
        "error": None,
    }

    try:
        # Fresh Workflow every design point — never mutate a live Workflow;
        # cfg = base_wf.to_dict() then mutate the plain dict then Workflow(cfg).
        base_wf = Workflow.from_file(BASE_YAML)
        cfg = base_wf.to_dict()

        for param in PARAMETERS:
            original_value = get_nested_value(cfg, param)
            scale_factor = row[param]
            set_nested_value(cfg, param, original_value * scale_factor)

        # Sync injection well length to the (scaled) sum of the production
        # well segments — see _sync_injection_well_length's docstring.
        _sync_injection_well_length(cfg)

        # No mirroring of layout.well_spacing onto components.surface here:
        # well_spacing is sourced only from layout: and rejected as a
        # per-component override (see Workflow's _PROTECTED_COMPONENT_KEYS)
        # — layout.well_spacing being one of the swept PARAMETERS is
        # already enough, nothing else needs to read it.

        wf = Workflow(cfg)
        wf.run()

        orch = wf._orchestrator
        surface = orch.components["surface"]
        production_well_upper = orch.components["production_well_upper"]

        result["net_power_W"] = surface.history.net_power_W[-1]
        result["T_prod_K"] = production_well_upper.history.T_outlet[-1]

        econ_state = wf.to_dict()["economic"]["state"]
        result["CAPEX_well_USD"] = econ_state["CAPEX_well"]
        result["CAPEX_exploration_USD"] = econ_state["CAPEX_exploration"]
        result["CAPEX_permitting_USD"] = econ_state["CAPEX_permitting"]
        result["CAPEX_surface_pipes_USD"] = econ_state["CAPEX_surface_pipes"]
        result["CAPEX_surface_plant_USD"] = econ_state["CAPEX_surface_plant"]
        result["CAPEX_total_USD"] = econ_state["CAPEX_total"]
        result["LCOE_USD_per_kWh"] = econ_state["LCOE"]

    except Exception as e:
        result["error"] = {
            "type": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc(),
        }

    # Atomic write so a mid-write crash doesn't leave a corrupt file that the
    # resume logic would mistake for a completed run.
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
    n_samples = len(df)

    results_dir.mkdir(exist_ok=True, parents=True)
    completed = {int(f.stem) for f in results_dir.glob("*.json")}
    pending = [i for i in range(n_samples) if i not in completed]

    if not quiet:
        print(f"Sweep status: {len(completed)}/{n_samples} completed, {len(pending)} pending")

    if not pending:
        if not quiet:
            print("All simulations complete!")
        return

    worker_args = [(idx, design_matrix_file, results_dir, log_level) for idx in pending]
    interval = progress_interval if progress_interval is not None else max(1, n_workers)

    # Use 'spawn' context for HPC compatibility (fork can cause issues on SLURM)
    if not quiet:
        print(f"Starting pool with {n_workers} workers (spawn context)...")
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(n_workers) as pool:
        completed_count = 0
        total = len(pending)
        for _ in pool.imap_unordered(run_single_simulation, worker_args):
            completed_count += 1
            if not quiet and completed_count % interval == 0:
                print(f"Progress: {completed_count}/{total} completed")

        if not quiet and completed_count % interval != 0:
            print(f"Progress: {completed_count}/{total} completed")

    if not quiet:
        print("Sweep complete!")


def main(
    n_workers: int = DEFAULT_N_WORKERS,
    log_level: str = DEFAULT_LOG_LEVEL,
    quiet: bool = False,
    progress_interval: int | None = None,
    sweep_dir: Path | None = None,
) -> None:
    """Run the parameter sweep using the pre-generated design matrix."""
    sweep_dir = sweep_dir if sweep_dir is not None else DEFAULT_SWEEP_DIR
    design_matrix_file = sweep_dir / "design_matrix.parquet"
    results_dir = sweep_dir / "results"

    if not quiet:
        print(f"Workers: {n_workers}")
    run_sweep(design_matrix_file, results_dir, n_workers, log_level, quiet, progress_interval)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the sweep runner."""
    params = load_params()
    parser = argparse.ArgumentParser(
        description="Run the tango double-flash LHS sweep simulations",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--n-workers",
        type=int,
        default=params.get("n_workers", DEFAULT_N_WORKERS),
        help="Number of parallel workers",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=params.get("log_level", DEFAULT_LOG_LEVEL),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "NONE"],
        help="Log level for tango simulations",
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress progress output")
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=None,
        help="Print progress every N completions (default: n_workers)",
    )
    parser.add_argument(
        "--sweep-dir",
        type=Path,
        default=None,
        help=f"Directory for sweep outputs (default: {DEFAULT_SWEEP_DIR})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.quiet and args.progress_interval is not None:
        raise ValueError("--quiet and --progress-interval are mutually exclusive")
    main(
        n_workers=args.n_workers,
        log_level=args.log_level,
        quiet=args.quiet,
        progress_interval=args.progress_interval,
        sweep_dir=args.sweep_dir,
    )
