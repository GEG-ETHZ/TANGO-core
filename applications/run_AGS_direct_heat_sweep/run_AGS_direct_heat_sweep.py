"""End-to-end orchestrator for the tango Triemli AGS direct-heat parameter sweep.

Targets ``example_configs/AGS_direct_heat.yml`` via the ``tango`` engine.
Sweeps well depth (2-8 km) x mass flow rate (3.5-40 kg/s) x horizontal
loop length (1000-8000 m) x loop diameter (0.2-0.75 m) over 12,870
designs and reports production temperature, specific enthalpy, and
thermal power — see ``common.py`` for the exact grids.

Runs generate -> sweep -> summarize -> plot in sequence. Call individual
stage scripts directly (generate.py, sweep.py, summarize.py, plot.py) if
you only need one stage.

**No CAPEX/LCOE in this port.** tango has no wired-up
``EconomicComponent`` yet (Phase 2 placeholder — nothing reads the
``economic:`` YAML block, confirmed by grep). Every CAPEX_*/LCOE_* field in
each result is explicitly ``None`` (not omitted, not silently dropped — see
``sweep.py``'s module docstring), and ``plot.py`` skips ``lcoe_grid.png``
entirely rather than plot an all-null column. Re-run this sweep once a real
economic component lands.

plot.py writes these to the sweep directory:
  - success_scatter.png       grid of subplots (rows = loop diameter,
                              columns = loop length), mass flow vs. well
                              depth, colored by whether T_prod meets the
                              105 degC district-heating threshold.
  - parallel_coordinates.png  static matplotlib version: every design as one
                              line across well depth, mass flow, loop
                              length, loop diameter, T_prod, and thermal
                              power, colored by thermal power (LCOH isn't
                              available yet, see above).
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

    python find_design.py --well-depth-m 8000 --mass-flow-kg-s 30 \
        --loop-length-m 3500 --loop-diameter-m 0.75

Usage
-----
    cd applications/run_AGS_direct_heat_sweep
    uv run python run_AGS_direct_heat_sweep.py --n-workers 8

    # Regenerate design matrix and re-run all simulations:
    uv run python run_AGS_direct_heat_sweep.py --regenerate --n-workers 8

    # Single-threaded (debugging):
    uv run python run_AGS_direct_heat_sweep.py --n-workers 1 --log-level INFO

    # Fast smoke test (16-design corner-of-hypercube subset, fresh tempdir):
    uv run python run_AGS_direct_heat_sweep.py --smoke --n-workers 2
"""

from __future__ import annotations

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
    """Parse CLI arguments."""
    params = load_params()
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description="tango Triemli direct-heat AGS sweep (depth x mass-flow x loop-length x loop-diameter)",
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
            "Run a tiny 16-design corner-of-hypercube sweep into a fresh OS "
            "tempdir instead of the full 12,870-design grid — for a fast "
            "'does the pipeline still run end to end' check, not real "
            "results. Skips plot.py (not meaningful on 16 designs). Never "
            "touches outputs/ — a new tempdir is created every run."
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
    if args.clean and args.smoke:
        raise ValueError("--clean and --smoke are mutually exclusive")

    if args.clean:
        clean_sweep_dir(args.sweep_dir or DEFAULT_SWEEP_DIR, quiet=args.quiet)
        raise SystemExit(0)

    if args.smoke:
        sweep_dir = args.sweep_dir or Path(tempfile.mkdtemp(prefix="tango_ags_dh_smoke_"))
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
