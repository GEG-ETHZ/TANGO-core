"""Simulation sweep stage: run each LHS-sampled design point in parallel.

tango_next port of ``applications/run_flexible_DF_manual_sweep/sweep.py``.
The parameter-mutation mechanics are entirely different from the old-tango
version: instead of mutating a live ``Runner.tango.specs`` dict in place,
every design point re-reads ``hydro_df_electric.yml`` fresh
(``Workflow.from_file(BASE_YAML).to_dict()``), mutates a plain dict copy
using the scale factors sampled per-row in the design matrix, and builds a
brand-new ``Workflow`` from it — see ``Workflow``'s class docstring
(``src/tango_next/workflows/workflow.py``) for why a live ``Workflow``/
``Component`` must never be mutated in place. Re-reading from the YAML file
fresh in each worker (rather than passing a pre-built ``Workflow`` between
processes) also sidesteps any question of whether ``Workflow`` objects are
picklable — they never cross a process boundary here.

**No economic component in tango_next yet** (Phase 1, bigger deal here than
for the AGS/EGS ports): ``EconomicComponent`` is an unwired placeholder —
nothing reads ``economic:`` in the YAML, so old tango's entire point in this
sweep (an LCOE sensitivity sweep across 23 parameters) can't be replicated
yet. ``LCOE`` is kept as an explicit ``None`` field (documented, not
omitted or silently dropped) rather than faked. Instead, this port tracks
what tango_next CAN produce today: ``net_power_W`` (the double-flash
topology's actual TESPy-solved net electric power, read from
``surface.history.net_power_W[-1]``) and ``T_prod_K`` (from
``production_well_upper.history.T_outlet[-1]``). The port still validates
that the double-flash topology holds up (or doesn't) across the same 21-D
parameter space old tango explored — it just can't yet report the economic
sensitivity that was the original point, pending tango_next's economic
component.

The ``specs_hash``/ArangoDB-hash field from old tango's result dict is
dropped entirely — that was an old-tango-specific integration with no
tango_next equivalent.
"""

from __future__ import annotations

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

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from tango_next.workflows.workflow import Workflow  # noqa: E402


def _sync_injection_well_length(cfg: dict) -> None:
    """Sync injection well length to the (scaled) sum of the two production well segments.

    Old tango sets ``injection_well.well_length = production_well.well_length
    + production_well_pump.well_length`` after all scale factors are
    applied, i.e. total injection depth = sum of the two production well
    segments post-scaling. The sampled scale factor for
    ``injection_well.well_length`` itself is thrown away in old tango too —
    which is why it isn't in ``PARAMETER_BOUNDS`` at all here (see
    common.py's docstring). Note: old tango also syncs
    ``well_length_seq``/``well_diameter_seq`` fields here — skipped
    entirely, tango_next's ``NumericalWell`` schema has no ``_seq`` fields.
    """
    prod_len = get_nested_value(cfg, "components.production_well_lower.well_length")
    pump_len = get_nested_value(cfg, "components.production_well_upper.well_length")
    set_nested_value(cfg, "components.injection_well.well_length", prod_len + pump_len)


def run_single_simulation(args: tuple) -> None:
    """Worker: run one LHS design point and write a JSON result file."""
    row_idx, design_matrix_file, results_dir, _log_level = args
    result_file = results_dir / f"{row_idx:06d}.json"
    if result_file.exists():
        return

    df = pl.read_parquet(design_matrix_file)
    row = df.filter(pl.col("row_idx") == row_idx).to_dicts()[0]

    result: dict = {
        "row_idx": row_idx,
        # LCOE cannot be computed — no EconomicComponent wired up yet in
        # tango_next (Phase 1); see module docstring. Kept explicit, not
        # omitted, so a null does not silently read as "zero cost."
        "LCOE": None,
        "net_power_W": None,
        "T_prod_K": None,
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

        # well_spacing must be kept in sync between layout and the surface
        # component (same convention as the AGS/EGS ports' well_spacing
        # handling) — but here layout.well_spacing IS one of the swept
        # PARAMETERS, so mirror the scaled value onto the surface component
        # after the loop above rather than sweeping both independently.
        set_nested_value(
            cfg,
            "components.surface.well_spacing",
            get_nested_value(cfg, "layout.well_spacing"),
        )

        wf = Workflow(cfg)
        wf.run()

        orch = wf._orchestrator
        surface = orch.components["surface"]
        production_well_upper = orch.components["production_well_upper"]

        result["net_power_W"] = surface.history.net_power_W[-1]
        result["T_prod_K"] = production_well_upper.history.T_outlet[-1]

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
        description="Run the tango_next double-flash LHS sweep simulations",
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
        help="Log level for tango_next simulations",
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
