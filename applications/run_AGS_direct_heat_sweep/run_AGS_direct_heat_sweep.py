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
1. Find the "AGS - Water-Based (ORC Plant)" example in the web app and verify
   that TANGO CLI reproduces its results.  This example likely lives in the
   web app's scenario database — locate it and export/confirm the YAML
   config.  Use it as the validated baseline before any further changes.

2. Walk the validated ORC config to a direct-heat scenario: replace the ORC
   surface plant with a district-heating heat exchanger (DH.T_out = 50 °C)
   and confirm results are physically sensible.

3. Re-run the depth × flow-rate sweep with the corrected AGS topology
   (triemli_dh_base.yml now uses injection_well → horizontal_well →
   production_well with no reservoir).  Extend the sweep to additional axes:
     - number of horizontal loops  (well_pattern_dimens or multiple h_well nodes)
     - horizontal loop length      (horizontal_well.well_length, currently fixed at 2500 m)
     - loop diameter               (horizontal_well.diameter)
   Note: multiple loops should be modelled in parallel (not in series) to
   get correct per-loop pressure drop.  Confirm the right mechanism in old
   tango before wiring this up (MULTIPLE_UNIT_NODE_OPTIONS supports multiple
   horizontal_well nodes but the parallel vs. series semantics need checking).
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
