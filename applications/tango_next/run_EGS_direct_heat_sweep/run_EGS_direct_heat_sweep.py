"""End-to-end orchestrator for the tango_next Triemli EGS direct-heat parameter sweep.

tango_next port of ``applications/run_EGS_direct_heat_sweep/``, targeting
``examples/tango_next/EGS_direct_heat.yml`` via the ``tango_next`` engine
(``src/tango_next/``) instead of ``src/tango/``'s ``Runner``. Sweeps well
depth (2-6.5 km) x mass flow rate (5-100 kg/s) over 100 designs and reports
production temperature, specific enthalpy, and thermal power — see
``common.py`` for the exact grids (copied verbatim from old tango's current
constants). Only two sweep axes here, unlike the AGS direct-heat sweep's
four (depth, mass-flow, loop-length, loop-diameter) — EGS has no horizontal
loop.

Runs generate -> sweep -> summarize -> plot in sequence, same as the old-tango
version (which stops at summarize — plot.py is new in this port, see its
module docstring). Call individual stage scripts directly (generate.py,
sweep.py, summarize.py, plot.py) if you only need one stage.

**No CAPEX/LCOE in this port.** tango_next has no wired-up
``EconomicComponent`` yet (Phase 2 placeholder — nothing reads the
``economic:`` YAML block, confirmed by grep). Every CAPEX_*/LCOE_* field in
each result is explicitly ``None`` (not omitted, not silently dropped — see
``sweep.py``'s module docstring), and ``plot.py`` skips ``lcoe_grid.png``
entirely rather than plot an all-null column. Re-run this sweep once a real
economic component lands.

plot.py writes these to the sweep directory:
  - success_scatter.png       mass flow vs. well depth, colored by whether
                              T_prod meets the 105 degC district-heating
                              threshold.
  - parallel_coordinates.png  static matplotlib version: every design as one
                              line across well depth, mass flow, T_prod, and
                              thermal power, colored by thermal power (LCOH
                              isn't available yet, see above).
  - parallel_coordinates.html interactive Plotly version of the same plot —
                              draggable axis brushing/filtering. Requires
                              the `dev` dependency group (plotly); skipped
                              with a printed note if plotly isn't installed.
  - parallel_coordinates_qualified.html  same, pre-filtered to designs
                              meeting the 105 degC threshold and >= 2 MW
                              thermal power.

Use find_design.py to look up a design's row_idx/result JSON from
approximate parameter values read off a parallel-coordinates plot (Plotly's
Parcoords trace has no hover tooltips):

    python find_design.py --well-depth-m 5000 --mass-flow-kg-s 30

Usage
-----
    cd applications/tango_next/run_EGS_direct_heat_sweep
    uv run python run_EGS_direct_heat_sweep.py --n-workers 8

    # Regenerate design matrix and re-run all simulations:
    uv run python run_EGS_direct_heat_sweep.py --regenerate --n-workers 8

    # Single-threaded (debugging):
    uv run python run_EGS_direct_heat_sweep.py --n-workers 1 --log-level INFO

    # Fast smoke test (4-design corner subset, fresh tempdir):
    uv run python run_EGS_direct_heat_sweep.py --smoke --n-workers 2
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from common import DEFAULT_LOG_LEVEL, DEFAULT_N_WORKERS, DEFAULT_SWEEP_DIR, load_params
from generate import main as generate_main
from plot import main as plot_main
from summarize import main as summarize_main
from sweep import main as sweep_main


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    params = load_params()
    parser = argparse.ArgumentParser(
        description="tango_next Triemli EGS direct-heat sweep (depth x mass-flow)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--n-workers",
        type=int,
        default=params.get("n_workers", DEFAULT_N_WORKERS),
        help="Parallel worker processes",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=params.get("log_level", DEFAULT_LOG_LEVEL),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "NONE"],
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Regenerate design matrix and clear existing results",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress output (pivot tables are still printed at end)",
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
        help=f"Output directory (default: {DEFAULT_SWEEP_DIR})",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=(
            "Run a tiny 4-design corner sweep into a fresh OS tempdir instead "
            "of the full 100-design grid — for a fast 'does the pipeline still "
            "run end to end' check, not real results. Skips plot.py (not "
            "meaningful on 4 designs). Never touches outputs/ — a new tempdir "
            "is created every run."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.smoke:
        sweep_dir = args.sweep_dir or Path(tempfile.mkdtemp(prefix="tango_next_egs_dh_smoke_"))
        if not args.quiet:
            print(f"Smoke run — writing to {sweep_dir}")
    else:
        sweep_dir = args.sweep_dir or DEFAULT_SWEEP_DIR

    generate_main(
        regenerate=args.regenerate,
        quiet=args.quiet,
        sweep_dir=sweep_dir,
        smoke=args.smoke,
    )
    sweep_main(
        n_workers=args.n_workers,
        log_level=args.log_level,
        quiet=args.quiet,
        progress_interval=args.progress_interval,
        sweep_dir=sweep_dir,
    )
    summarize_main(quiet=False, sweep_dir=sweep_dir)  # always print tables at end
    if not args.smoke:
        plot_main(quiet=args.quiet, sweep_dir=sweep_dir)
