"""End-to-end orchestrator for the tango double-flash sensitivity sweep.

Targets ``example_configs/hydro_df_electric.yml`` via the ``tango`` engine
(``src/tango/``). Runs a one-at-a-time (OFAT) sweep across the
double-flash topology's parameters (material properties, reservoir, wells,
surface plant components — see ``common.py`` for the exact bounds): each
parameter is moved to its low/high bound in its own design point, with
every other parameter held at baseline — see ``generate.py``'s module
docstring for why this replaced the original LHS design (a full,
simultaneous LHS draw across ~30 parameters had a near-0% feasible-design
rate in practice).

Every design point's config includes an ``economic:`` block
(``DoubletEconomicComponent``), so ``LCOE_USD_per_kWh``/``CAPEX_*_USD`` are
computed for real (see ``sweep.py``'s module docstring) alongside
``net_power_W``/``T_prod_K``.

Runs generate -> sweep -> summarize -> plot in sequence. Call individual
stage scripts directly (generate.py, sweep.py, summarize.py, plot.py) if
you only need one stage.

Usage
-----
    cd applications/run_hydro_df_electric_sweep
    uv run python run_hydro_df_electric_sweep.py --n-workers 8

    # Regenerate design matrix and re-run all simulations:
    uv run python run_hydro_df_electric_sweep.py --regenerate

    # Single-threaded (debugging):
    uv run python run_hydro_df_electric_sweep.py --n-workers 1 --log-level INFO

    # Fast smoke test (fresh tempdir, same fixed design):
    uv run python run_hydro_df_electric_sweep.py --smoke --n-workers 2
"""

import argparse
import tempfile
from pathlib import Path

from common import (
    DEFAULT_LOG_LEVEL,
    DEFAULT_N_WORKERS,
    DEFAULT_SWEEP_DIR,
    clean_sweep_dir,
    load_params,
)
from generate import main as generate_main
from plot import main as plot_main
from summarize import main as summarize_main
from sweep import main as sweep_main

from tango.utils import print_dt


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the end-to-end sweep entry point."""
    params = load_params()
    parser = argparse.ArgumentParser(
        description="End-to-end one-at-a-time sensitivity sweep for the tango double-flash topology",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--n-workers",
        type=int,
        default=params.get("n_workers", DEFAULT_N_WORKERS),
        help="Number of parallel workers",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Regenerate design matrix even if it exists (clears old results)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=params.get("log_level", DEFAULT_LOG_LEVEL),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "NONE"],
        help="Log level for tango simulations",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress output",
    )
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
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=(
            "Run the same fixed one-at-a-time design into a fresh OS tempdir "
            "instead of the default outputs/ dir — for a fast 'does the "
            "pipeline still run end to end' check, not a smaller design. "
            "Overrides --sweep-dir. Never touches outputs/ — a new tempdir "
            "is created every run."
        ),
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove all generated artifacts from --sweep-dir (or the default outputs/ dir) and exit",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print_dt()
    if args.quiet and args.progress_interval is not None:
        raise ValueError("--quiet and --progress-interval are mutually exclusive")
    if args.clean and args.smoke:
        raise ValueError("--clean and --smoke are mutually exclusive")

    if args.clean:
        clean_sweep_dir(args.sweep_dir or DEFAULT_SWEEP_DIR, quiet=args.quiet)
        raise SystemExit(0)

    if args.smoke:
        sweep_dir = args.sweep_dir or Path(tempfile.mkdtemp(prefix="tango_df_manual_smoke_"))
        if not args.quiet:
            print(f"Smoke run — writing to {sweep_dir}")
    else:
        sweep_dir = args.sweep_dir if args.sweep_dir is not None else DEFAULT_SWEEP_DIR

    generate_main(
        regenerate=args.regenerate,
        quiet=args.quiet,
        sweep_dir=sweep_dir,
    )
    sweep_main(
        n_workers=args.n_workers,
        log_level=args.log_level,
        quiet=args.quiet,
        progress_interval=args.progress_interval,
        sweep_dir=sweep_dir,
    )
    summarize_main(quiet=args.quiet, sweep_dir=sweep_dir)
    if not args.smoke:
        plot_main(quiet=args.quiet, sweep_dir=sweep_dir)
