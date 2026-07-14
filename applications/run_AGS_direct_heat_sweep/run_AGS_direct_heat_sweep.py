"""End-to-end orchestrator for the Triemli AGS direct-heat parameter sweep.

Sweeps well depth (2 – 6.5 km) × mass flow rate (5 – 100 kg/s) over 100 designs
and reports production temperature, specific enthalpy, thermal power, and CAPEX.

Runs generate → sweep → summarize in sequence.  Call individual stage scripts
directly (generate.py, sweep.py, summarize.py) or use DVC for caching.

Usage
-----
    cd applications/run_AGS_direct_heat_sweep
    python run_AGS_direct_heat_sweep.py --n-workers 8

    # Regenerate design matrix and re-run all simulations:
    python run_AGS_direct_heat_sweep.py --regenerate --n-workers 8

    # Single-threaded (debugging):
    python run_AGS_direct_heat_sweep.py --n-workers 1 --log-level INFO

TODO (before re-running this sweep for the Triemli analysis)
------------------------------------------------------------
Context: an earlier version of this sweep accidentally used an EGS-doublet
topology (reservoir node with `permeability`) copy-pasted from
run_EGS_direct_heat_sweep/. That was fixed in the graph/YAML, but the
`outputs/` directory was never regenerated afterward — every existing result
file predates the fix and must be treated as invalid until step 4 below is
re-run.

1. DONE — reconstructed the web app's "AGS - Water-Based (ORC Plant)"
   (AGS_H2O) example as a single runnable YAML:
   examples/AGS_new/AGS_H2O_webapp_native.yml. It is native (not MOOSE) and
   has no reservoir node. Traced the web app's actual request path
   (tango_app/src/Components/SimulationParameters.tsx) and confirmed it
   loads examples/MVP_templates/testcase7.yml as its base config plus a
   fixed parameter_overrides dict — this YAML is that file, not an
   independent reconstruction, so it can't silently drift from the web
   app's real behavior.
   VALIDATED — Chad ran the live web app with default AGS_H2O parameters
   and reported LCOE/CAPEX breakdown/net electricity; our tango_cli run of
   this YAML matches to rounding precision (LCOE 77.74 vs 77.7399 $/kWh,
   total CAPEX $21,426,846 vs $21,426,845.63, net electricity 5.54 vs
   5.5403 kWe, all five CAPEX line items agree). This is the validated
   baseline going forward.
   Known minor discrepancy (not yet resolved, appears immaterial at this
   precision): the web app's atmospheric/surface temperature is 15.15 °C,
   this YAML uses 15.0 °C (288.15 K) — a 0.15 °C gap inherited from
   testcase7.yml itself, not introduced here.

2. Walk the validated ORC config to a direct-heat scenario: replace the ORC
   surface plant with a district-heating heat exchanger (DH.T_out = 50 °C)
   and confirm results are physically sensible.  (triemli_dh_base.yml
   already has a power_plant_graph/DH block doing this, but it was written
   before step 1 was validated — recheck it against the validated baseline
   rather than assuming it's correct.)

3. Reconcile the horizontal loop length: the web app baseline uses 707 m
   (at 2500 m depth), while triemli_dh_base.yml uses 2500 m. Both are
   internally consistent (well_spacing == horizontal well_length in each) —
   pick one as the sweep's reference value and document why.

4. Re-run the depth × flow-rate sweep with the corrected AGS topology and
   reconciled loop length, using `--regenerate` (the existing outputs/ predate
   the topology fix and must not be reused).  Extend the sweep to additional
   axes:
     - number of horizontal loops  (well_pattern_dimens or multiple h_well nodes)
     - horizontal loop length      (horizontal_well.well_length)
     - loop diameter               (horizontal_well.diameter)
   Note: multiple loops should be modelled in parallel (not in series) to
   get correct per-loop pressure drop.  MULTIPLE_UNIT_NODE_OPTIONS
   (src/tango/core/config.py) allows multiple horizontal_well nodes but only
   suppresses a duplicate-node registration error — it does not itself
   establish parallel-flow physics.  Verify the actual graph execution
   semantics before relying on it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import DEFAULT_LOG_LEVEL, DEFAULT_N_WORKERS, DEFAULT_SWEEP_DIR, load_params
from generate import main as generate_main
from summarize import main as summarize_main
from sweep import main as sweep_main


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    params = load_params()
    parser = argparse.ArgumentParser(
        description="Triemli direct-heat doublet sweep (depth × mass-flow, 10×10 grid)",
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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sweep_dir = args.sweep_dir or DEFAULT_SWEEP_DIR

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
    summarize_main(quiet=False, sweep_dir=sweep_dir)  # always print tables at end
