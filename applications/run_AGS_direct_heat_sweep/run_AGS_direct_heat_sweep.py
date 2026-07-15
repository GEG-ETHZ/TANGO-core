"""End-to-end orchestrator for the Triemli AGS direct-heat parameter sweep.

Sweeps well depth (2 – 6.5 km) × mass flow rate (5 – 100 kg/s) × horizontal loop
length (707 – 2500 m) over 500 designs and reports production temperature,
specific enthalpy, thermal power, and CAPEX.

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

2. DONE — see "Direct-heat AGS validator fix" in NOTES below for the bug this
   hit and the patch applied. examples/AGS_new/AGS_H2O_webapp_native_direct_heat.yml
   is a minimal walk from the validated ORC baseline (topology/well
   params/mass-flow untouched, only the surface node swapped to
   native_flexible + a Source -> SimpleHeatExchanger(DH_component) -> Sink
   power_plant_graph, per the proven pattern in examples/flexible_heat.yml).
   Results are physically sensible: steady-state production at 60.3 degC,
   DH heat exchanger drops it to the configured 50 degC return, net thermal
   power 194.4 kWth, LCOH ~2.18 $/kWh_th (vs. the ORC baseline's 5.5 kWe /
   LCOE 77.7 $/kWh_e — direct heat is far more economical here, as expected,
   since it skips Carnot losses).

3. DONE (by making it moot) — the web app baseline uses a 707 m loop, while
   triemli_dh_base.yml used a fixed 2500 m. Rather than pick one "correct"
   constant, loop length is now a third sweep axis (see common.py's
   LOOP_LENGTHS_M): [707, 1000, 1500, 2000, 2500] m, bracketing both prior
   values. sweep.py's new _apply_loop_length() updates
   horizontal_well.well_length/well_length_seq and schedule.well_spacing
   together (both must match by convention — see the "Inconsistent
   well_spacing and horizontal_well length" warning in horizontal_well.py).

4. PARTIALLY ADDRESSED — full 10 x 10 x 5 = 500-design sweep re-run with `--regenerate`
   (2026-07-15): 0 failures, ~24 s wall time on 8 workers. 25/500 designs
   meet the T_prod >= 105 degC threshold, spanning all 5 loop lengths and
   depths >= 5000 m — confirming the loop-length axis is doing real work,
   not just adding runtime. summarize.py now writes one CSV per (metric,
   loop length) pair, since a flat 2-D pivot can't show all three axes at
   once.
   STILL MISSING, not just deferred polish — the original TODO asked for
   three additional axes and this only delivered one:
     - horizontal loop length      DONE (see item 3)
     - loop diameter               NOT DONE — would be a straightforward
       fourth axis (horizontal_well.diameter), no known blockers.
     - number of horizontal loops  NOT DONE — blocked on unverified
       parallel-vs-series flow semantics. MULTIPLE_UNIT_NODE_OPTIONS
       (src/tango/core/config.py) allows multiple horizontal_well nodes but
       only suppresses a duplicate-node registration error — it does not
       itself establish parallel-flow physics, and multiple loops must be
       modelled in parallel (not in series) for correct per-loop pressure
       drop. Verify the actual graph execution semantics before adding this
       axis.
   Do not treat this sweep's output as covering the full design space the
   TODO originally called for until loop diameter and loop count are
   addressed (or explicitly descoped by Chad).

Notes
-----
Direct-heat AGS validator fix
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`SurfaceUnitFlexiblePP.validate_custom()`
(src/tango/units/native/surface/flexible_pp.py) unconditionally did:

    te_pp_in_est = (specs["surface"]["surface_temperature"]
                    + specs["reservoir"]["reservoir_depth"] * specs["props"]["thermal_gradient"])

to sanity-bound `target_extraction_pressure`. This assumes an EGS/doublet
topology with a `reservoir` node. AGS has no reservoir, so every
`native_flexible` (direct-heat) config on an AGS graph used to crash with
`KeyError: 'reservoir'` at unit construction, before any simulation ran.

This wasn't specific to the new baseline in this application:
`triemli_dh_base.yml` — believed fixed after the earlier topology
correction — hit the identical crash and had never actually completed a
run. The direct-heat path here was broken independent of, and in addition
to, the permeability/topology bug documented above.

`reservoir_depth` in that formula stands in for "the depth at which the
working fluid reaches its hottest point before returning to surface." For
AGS that's the depth of the horizontal loop, i.e. `horizontal_well.wellhead_depth`
— despite the name, this is NOT the depth of the surface wellhead (0 m); in
this codebase's convention it's the depth below surface at which the
horizontal segment begins (see horizontal_well.py's identical
`T0 + h * dTdz` usage at line 53, where `h = self._specs.wellhead_depth`).
That naming is confusing on its own terms (a "wellhead" is conventionally
surface equipment) independent of the reservoir/no-reservoir question, and
is a good example of the kind of ambiguity `tango_next` should design away
(see docs/TANGO_vision_and_roadmap.md).

Fixed in `flexible_pp.py`: `validate_custom()` now branches on whichever of
`reservoir` / `horizontal_well` is present in specs to get this depth,
instead of hardcoding `reservoir`. This is a pragmatic patch, not an
architectural fix — the surface-unit code still has no general concept of
"the subsurface component upstream of the surface plant," only two
hardcoded node names. Confirmed working: examples/AGS_new/
AGS_H2O_webapp_native_direct_heat.yml now runs and produces physically
sensible results (steady-state production 60.3 degC, DH exchanger to the
configured 50 degC return, net thermal power 194.4 kWth, LCOH ~2.18
$/kWh_th).

No AGS + direct-heat example exists anywhere, in tango-core or the web app
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Checked exhaustively (2026-07-15): every AGS example under examples/
(AGS_new/, Martin_AGS/, EGC2025/, testcase6/7/8.yml, MVP_templates/) pairs
AGS with an ORC or CO2 power-cycle surface plant, never native_flexible/DH.
Every web app template that uses native_flexible + DH_component
(flexible_heat.ts, flexible_CPG_inverted_native.ts,
flexible_SF_cogeneration_e.ts) is a reservoir-based EGS/CPG topology, never
AGS. examples/AGS_new/AGS_H2O_webapp_native_direct_heat.yml (this
application) is the first working example of this combination, unblocked
by the validator fix described above.

Why none of the existing AGS examples were a good starting point
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
This isn't one mistake — the whole AGS example set in this repo has accumulated
inconsistencies characteristic of lacking a consistently enforced code style for
a maintainable, re-runnable reference config:
  - examples/AGS_new/H2O_1b.yml (the MOOSE-coupled example) hardcodes
    absolute paths to a former contributor's machine
    (/Users/morteza/Documents/projects/...) — not runnable as-is by anyone
    else.
  - The web app's own AGS_H2O template (tango_app/src/config/templates/) is
    split across two files (AGS_H2O.ts, presets.ts) that don't fully agree
    with each other or with the base YAML the app actually loads
    (examples/MVP_templates/testcase7.yml) — the only reason this was
    caught was tracing the live request path end-to-end rather than trusting
    the template source.
  - The AGS direct-heat sweep this application performs was originally
    built (commit 6496f82) as a copy-paste of the EGS doublet sweep,
    carrying over a `reservoir` node with a literal `permeability` value —
    physically meaningless for a sealed AGS loop — which is how invalid
    results ended up in a real client presentation before this was caught.
  - The `native_flexible` surface unit (this NOTES section, above) was
    apparently only ever exercised against reservoir-based topologies;
    nothing in its test suite or examples caught that it can't run without
    one.
None of this was introduced by this work; it predates it and reflects the
repo's broader history of single-use, paper-driven configs rather than a
maintained reference set.

Why we patched native instead of waiting for tango_next
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
tango_next was explicitly designed to avoid this kind of topology-shaped
ambiguity (see docs/TANGO_vision_and_roadmap.md), and building this case
there instead of patching native's validator was considered. Decided
against it for now: tango_next doesn't yet have direct-heat/district-heating
surface plant support built at all, so doing this there means building that
first, which risks blocking the Triemli deliverable on a bigger lift than
the timeline allows. The native patch above is pragmatic, not
architectural, and is intentionally scoped as small as possible; the
vision-doc note ensures tango_next does this properly (per-component depth
estimate, not a hardcoded node-name lookup) when that work happens.

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
