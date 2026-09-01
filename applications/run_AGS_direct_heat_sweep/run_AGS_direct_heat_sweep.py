"""End-to-end orchestrator for the Triemli AGS direct-heat parameter sweep.

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
!!! DO NOT TRUST MULTI-TIMESTEP RESULTS FROM THIS SWEEP (confirmed 2026-08-01) !!!
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
Every design point here is an AGS config (horizontal_well, no reservoir),
which src/tango/utils.py::system_name() (~line 875-876) silently routes to
the SystemNative orchestrator (src/tango/orchestrators/native.py:14-77) —
its update_time_dependent_vars()/update()/balanced() are literal no-op
placeholders. NOTHING advances between timesteps: every design point's
multi-timestep run repeats the SAME solved state at every timestep after
t=0. Any apparent thermal decline over time in this sweep's output is NOT
REAL PHYSICS. See docs/tango_next_tasks.md's "AGS_direct_heat.yml parity"
entry (section 4) for the full root-cause trace and status. NOT YET FIXED.

Sweeps well depth (2 – 8 km) × mass flow rate (3.5 – 100 kg/s) × horizontal
loop length (707 – 3500 m) × loop diameter (0.2 – 0.75 m) over 6006 designs
and reports production temperature, specific enthalpy, thermal power, and
CAPEX. (Ranges extended 2026-07-15 from the original 6.5 km / 5 kg/s /
2500 m / 0.5 m upper-lower bounds, same step sizes — see common.py.)

Runs generate → sweep → summarize → plot in sequence.  Call individual stage
scripts directly (generate.py, sweep.py, summarize.py, plot.py) or use DVC
for caching.

plot.py writes these to the sweep directory:
  - success_scatter.png       grid of subplots (rows = loop diameter,
                              columns = loop length), mass flow vs. well
                              depth, colored by whether T_prod meets the
                              105 degC district-heating threshold.
  - lcoe_grid.png             same grid layout, with marker shape repeating
                              the success_scatter threshold encoding
                              (o = meets, x = misses) and marker color
                              showing LCOH — designs with LCOH undefined
                              (see sweep.py's LCOE-nulling note) are grey.
  - parallel_coordinates.png  static matplotlib version: every design as one
                              line across well depth, mass flow, loop
                              length, loop diameter, T_prod, thermal power,
                              CAPEX, and LCOH, colored by LCOH.
  - parallel_coordinates.html interactive Plotly version of the same plot —
                              draggable axis brushing/filtering, hover
                              tooltips. Requires the `dev` dependency group
                              (plotly); skipped with a printed note if
                              plotly isn't installed.
  - parallel_coordinates_qualified.html  same as parallel_coordinates.html,
                              pre-filtered to designs meeting the 105 degC
                              threshold and >= 2 MW thermal power (583 of
                              6006) instead of relying on manual axis-drag
                              filtering, with the LCOH colorbar's 5th-95th
                              percentile computed over just that subset so
                              it actually resolves the spread among designs
                              that matter instead of being dominated by the
                              full sweep's much wider range.

Both parallel-coordinates plots include a "Design index" (row_idx) axis, but
Plotly's Parcoords trace has no hover tooltips at all (confirmed via its
attribute list — no hoverinfo/hovertemplate on the trace or on dimensions),
so you can't read an exact row_idx off a line by hovering. Use
find_design.py instead: drag narrow filter ranges on the plot's four input
axes (well depth, mass flow, loop length, loop diameter) until only the
line(s) you care about remain, read (approximate) values off the axes, then:

    python find_design.py --well-depth-m 8000 --mass-flow-kg-s 30 \
        --loop-length-m 3500 --loop-diameter-m 0.75

prints the nearest-matching row(s) (normalized-distance nearest-neighbor,
not exact/tolerance matching — deliberately so it keeps working if this
sweep ever moves from a full-factorial grid to LHS or other continuous
sampling, where "type the exact value" wouldn't make sense) plus each one's
outputs/results/<row_idx>.json path.

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
   hit and the patch applied. examples/AGS_new/AGS_H2O_native_direct_heat.yml
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

4. DONE, with one axis descoped — of the three additional axes the original
   TODO asked for, two are done and the third is explicitly descoped:
     - horizontal loop length      DONE (see item 3)
     - loop diameter               DONE — fourth sweep axis added
       (common.py's LOOP_DIAMETERS_M, currently [0.2, 0.311, 0.41, 0.5, 0.6,
       0.75] m, bracketing the same two real reference points as loop
       length: 0.311 m is triemli_dh_base.yml's original fixed casing
       choice, 0.41 m is the web app's validated value). sweep.py's new
       _apply_loop_diameter() updates horizontal_well.diameter/
       well_diameter_seq only — the vertical wells' diameter is
       intentionally left alone, per the original TODO wording ("loop
       diameter (horizontal_well.diameter)").
     - number of horizontal loops  DESCOPED for now (Chad's call, 2026-07-16).
       Still blocked on unverified parallel-vs-series flow semantics:
       MULTIPLE_UNIT_NODE_OPTIONS (src/tango/core/config.py) allows multiple
       horizontal_well nodes but only suppresses a duplicate-node
       registration error — it does not itself establish parallel-flow
       physics, and multiple loops must be modelled in parallel (not in
       series) for correct per-loop pressure drop. Properly supporting this
       would mean either verifying the orchestrator's actual graph-traversal
       semantics or building the split/merge topology explicitly ourselves
       (N horizontal_well nodes, flow split evenly, merged before the
       production well) — real scope, not a quick sweep-axis addition like
       the other three. Reasoning for descoping rather than blocking on it:
       sweeping loop length and loop diameter already varies the total
       heat-exchange/flow capacity a design can deliver, which is a
       reasonable surrogate for what adding more parallel loops would
       accomplish — the design space isn't fully explored without this axis,
       but it isn't unexplored either.
   Ranges extended again 2026-07-15 (second round): well
   depth 6.5 -> 8 km, mass flow 5 -> 3.5 kg/s floor, loop length 2500 ->
   3500 m, loop diameter 0.5 -> 0.75 m, all keeping the existing step sizes
   (see common.py). This uncovered a real validation failure — see "8000 m
   depth tier needed target_extraction_pressure to scale with depth" in
   NOTES below — now fixed. Full 13 x 11 x 7 x 6 = 6006-design sweep
   re-run with `--regenerate` (2026-07-15): 0 failures, ~4.5 min wall time
   on 8 workers (slower per-design than the previous 2000-design sweep —
   the extended ranges include more numerically demanding combinations,
   not just proportionally more designs). 1003/6006 designs meet the
   T_prod >= 105 degC threshold. summarize.py writes one CSV per (metric,
   loop length, loop diameter) triple (252 files) instead of printing every
   pivot table to the console, since 7 x 6 = 42 combinations is unreadable
   as printed tables.
   Number of horizontal loops remains the one axis from the original TODO
   that's missing — descoped rather than done, see above. This sweep's
   output should be read as covering the loop-length/loop-diameter/depth/
   mass-flow design space, with number-of-loops intentionally out of scope
   for now rather than silently unaddressed.

5. NOT DONE — this whole sweep assumes constant heat demand. Every design
   point runs to steady state at one fixed mass_flow_rate (sweep.py's
   _apply_mass_flow()); thermal_power_kW is a single static number per
   design, not a time series. Real district-heating demand varies
   seasonally (and diurnally), so a design sized for peak thermal_power_kW
   is not the same as a design sized to serve a real annual demand curve
   economically. src/tango/'s HotmapsDispatchDT time-type (see
   src/tango/orchestrators/BC_calculator.py's PowerReader/iterator) is
   *a* precedent for demand-following mass-rate control elsewhere in the
   codebase, but it's tightly coupled to the Hotmaps desktop app's Excel
   export pipeline and is not used here. This needs a lightweight,
   Hotmaps-independent demand-curve mechanism before this sweep's results
   can be read as "what you'd actually build," not just "what the physics
   supports at one operating point." Tracked in
   docs/TANGO_vision_and_roadmap.md's seasonal-heat-demand-variation
   section. Applies equally to applications/run_AGS_sweep/ (the
   power-generation counterpart of this sweep) wherever main_product is
   heat/cogeneration — pure electricity sweeps are less exposed since
   grid dispatch, not a fixed thermal demand curve, is the usual driver
   there.

Notes:
8000 m depth tier needed target_extraction_pressure to scale with depth
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
When the depth axis was extended to 8000 m, every single design at that
depth (462/6006 — exactly 11 flow rates x 7 loop lengths x 6 diameters, a
clean threshold, not scattered numerical noise) failed with the same
ValidationError from SurfaceUnitFlexiblePP.validate_custom()
(src/tango/units/native/surface/flexible_pp.py): the fixed
surface.target_extraction_pressure (7 MPa, inherited unchanged from the
original 2500 m-depth design) was below the saturation pressure at the
estimated plant-inlet temperature at 8000 m (~291 degC -> ~7.55 MPa
saturation pressure). Below that, the fluid would flash to vapor at the
plant inlet — a real physical constraint, not a bug. 7500 m and shallower
were all fine (required pressure there is well under 7 MPa).

Fixed by adding sweep.py's _apply_target_extraction_pressure(): computes
the same plant-inlet-temperature estimate the validator uses
(surface_temperature + depth * thermal_gradient), gets its saturation
pressure via CoolProp, and sets target_extraction_pressure to
max(7 MPa, 1.2 x saturation_pressure). The 7 MPa floor means every depth
that was already valid (<= 7500 m) gets exactly the same
target_extraction_pressure as before this function existed — only the
newly-added 8000 m tier's value actually changes, so none of the other
5544 already-completed designs needed to be (or were) re-run.

Negative LCOE at marginal (T_prod ~ 50-51 degC) designs — nulled, not fixed upstream
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
plot.py's parallel-coordinates plot surfaced 53/500 designs (all clustered
right at the 50 degC DH return temperature — essentially non-functional
loops with almost no useful delta-T) reporting deeply negative LCOE (as low
as -180 $/kWh_th). Root cause: the native economic unit's
Net_thermal_power_Generated_kWe goes negative for these designs — parasitic
pumping load apparently consumes as much or more energy as the loop
delivers, in the economic unit's own accounting — and LCOE = CAPEX /
net_power, so dividing by a negative number flips the sign. A negative
"cost" is nonsensical: these designs aren't cheap, they're not producing a
priced product at all.

Fixed locally in sweep.py's run_single_simulation(): when
net_thermal_power_kW <= 0, LCOE is set to null (None / JSON null) rather
than reporting the native unit's raw (wrong-signed) value. This is a
result-post-processing fix in this application only, not a fix to the
native economic unit itself — src/tango/units/native/economic/economic.py's
LCOE formula still does the same division regardless of caller. Whether
Net_thermal_power_Generated_kWe going negative is itself correct (parasitic
pumping genuinely exceeding delivered heat is physically plausible for a
barely-functional loop) or a sign/accounting bug is unresolved — it sits
alongside the existing "Pump electricity accounting — known inconsistencies
(needs HIL verification)" section in docs/TANGO_vision_and_roadmap.md and
should be investigated together with that, not treated as solved by this
workaround.

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
AGS_H2O_native_direct_heat.yml now runs and produces physically
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
AGS. examples/AGS_new/AGS_H2O_native_direct_heat.yml (this
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
