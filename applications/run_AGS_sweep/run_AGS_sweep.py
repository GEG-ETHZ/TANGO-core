"""End-to-end orchestrator for the Triemli AGS power-generation (ORC) parameter sweep.

Sweeps well depth (2 – 8 km) × mass flow rate (3.5 – 100 kg/s) × horizontal
loop length (707 – 3500 m) × loop diameter (0.2 – 0.75 m) over 6006 designs
— the same four-axis design space as the sibling direct-heat sweep
(applications/run_AGS_direct_heat_sweep/) — but with the AGS closed loop
feeding an ORC power plant (surface unit: native_ORC) instead of a
district-heating heat exchanger. Outputs and economics are
electricity-focused: production temperature, net electric power (after
parasitic pumping/generator loads), CAPEX, and LCOE priced on electricity
(main_product left at its native default of 'electricity', rather than
'heat' as in the direct-heat sweep).

The ORC surface-plant parameters (condensation_pressure_offset, eta_turbine,
refrigerant, ORC_opt_mode) are taken verbatim from the validated ORC
baseline in examples/AGS_new/AGS_H2O_webapp_native.yml — see
triemli_power_base.yml's header for the full provenance note.

Runs generate → sweep → summarize → plot in sequence. Call individual stage
scripts directly (generate.py, sweep.py, summarize.py, plot.py) or use DVC
for caching.

plot.py writes these to the sweep directory:
  - success_scatter.png       grid of subplots (rows = loop diameter,
                              columns = loop length), mass flow vs. well
                              depth, colored by whether the design is a net
                              electricity producer (net_electric_power_kW > 0).
  - lcoe_grid.png             same grid layout, with marker shape repeating
                              the success_scatter qualification encoding
                              (o = net producer, x = net consumer or 0) and
                              marker color showing LCOE — designs with LCOE
                              undefined (see sweep.py's LCOE-nulling note)
                              are grey.
  - parallel_coordinates.png  static matplotlib version: every design as one
                              line across well depth, mass flow, loop
                              length, loop diameter, T_prod, net electric
                              power, CAPEX, and LCOE, colored by LCOE.
  - parallel_coordinates.html interactive Plotly version of the same plot —
                              draggable axis brushing/filtering, hover
                              tooltips. Requires the `dev` dependency group
                              (plotly); skipped with a printed note if
                              plotly isn't installed.
  - parallel_coordinates_qualified.html  same as parallel_coordinates.html,
                              pre-filtered to designs that are net
                              electricity producers, with the LCOE
                              colorbar's 5th-95th percentile computed over
                              just that subset so it actually resolves the
                              spread among designs that matter instead of
                              being dominated by the full sweep's much wider
                              range.

Both parallel-coordinates plots include a "Design index" (row_idx) axis, but
Plotly's Parcoords trace has no hover tooltips at all, so you can't read an
exact row_idx off a line by hovering. Use find_design.py instead: drag
narrow filter ranges on the plot's four input axes (well depth, mass flow,
loop length, loop diameter) until only the line(s) you care about remain,
read (approximate) values off the axes, then:

    python find_design.py --well-depth-m 8000 --mass-flow-kg-s 30 \
        --loop-length-m 3500 --loop-diameter-m 0.75

prints the nearest-matching row(s) plus each one's
outputs/results/<row_idx>.json path.

Usage
-----
    cd applications/run_AGS_sweep
    python run_AGS_sweep.py --n-workers 8

    # Regenerate design matrix and re-run all simulations:
    python run_AGS_sweep.py --regenerate --n-workers 8

    # Single-threaded (debugging):
    python run_AGS_sweep.py --n-workers 1 --log-level INFO

Relationship to applications/run_AGS_direct_heat_sweep/
---------------------------------------------------------
This app is the electricity-generation counterpart of
applications/run_AGS_direct_heat_sweep/ — same AGS well topology, same four
sweep axes (see common.py), same pipeline stages, differing only in the
surface plant (native_ORC vs. native_flexible) and in which economic
metrics are reported (net electric power / LCOE vs. net thermal power /
LCOH).

The direct-heat sweep's docstring flags (as item 5, added 2026-07-21) that
its results assume a constant, single operating point per design rather
than a real seasonal demand curve — real district-heating demand varies
seasonally and diurnally, so sizing for one steady-state thermal_power_kW
doesn't reflect what you'd size to serve an actual annual demand curve
economically. That gap applies less directly here: this is pure
electricity generation, and grid dispatch economics (spot prices, capacity
markets, curtailment), not a fixed thermal demand curve, is the usual
driver for sizing a real power plant. Still, it's worth flagging as a
relevant open question if this app is ever extended toward cogeneration
(main_product handling both heat and electricity from the same design),
where a demand-curve-aware sizing mechanism would become directly relevant
again.
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
        description="Triemli AGS power-generation (ORC) sweep (depth × mass-flow × loop-length × loop-diameter)",
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
            "tempdir instead of the full 6006-design grid — for a fast 'does "
            "the pipeline still run end to end' check, not real results. "
            "Skips plot.py (not meaningful on 16 designs). Never touches "
            "outputs/ — a new tempdir is created every run."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.smoke:
        sweep_dir = args.sweep_dir or Path(tempfile.mkdtemp(prefix="tango_ags_orc_smoke_"))
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
