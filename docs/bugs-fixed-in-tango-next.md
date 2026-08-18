# Bugs Found and Fixed

A running record of concrete bugs in legacy `src/tango` that `tango_next`
either avoids by design or has explicitly fixed, relative to the legacy
behavior. Scope is deliberately narrow: this is not a general `tango_next`
changelog (see `docs/tango_next_tasks.md` for that) — only bugs that exist
(or existed) in `src/tango` and are confirmed not to recur in `tango_next`
belong here.

Entries are added only once a bug is fully confirmed against current
`src/tango` code and verified not to recur in `tango_next`. Each entry
links to the fuller writeup where one exists.

## AGS configs never advance simulated time

`src/tango/utils.py::system_name()` collapses any AGS-shaped config
(a `horizontal_well` node with no `reservoir` node) down to the generic
system name `"native"`, which routes to the base `SystemNative`
orchestrator — whose time-marching methods
(`update_time_dependent_vars`/`update`/`balanced`) were no-op placeholders.
Result (pre-2026-08-04): a multi-timestep AGS run silently repeated the
exact same solved state at every timestep after t=0, with no error of any
kind.

Confirmed four independent ways: code inspection, reproducing the same
signature on an unrelated pre-existing "validated" example file, a live
debugger walkthrough of the failure (breakpoints in `utils.py`,
`workflows/native_workflow.py`, and `orchestrators/native.py` confirmed
the wrong class gets instantiated and its no-op method actually executes),
and the raw output data itself (`production_well_T` bit-identical for
every year after year 1).

**Root cause, confirmed to the exact mechanism (2026-08-05).** Two
independent gaps, either one sufficient on its own:

1. `SystemNative.balanced()` (base class) unconditionally `return True`s —
   breakpoint at `orchestrators/native.py`'s `return True` line inside
   `balanced()`, or at `workflows/native_workflow.py:326`
   (`if self.orchestrator.balanced():`) inside `_native_system_iteration`'s
   `while not self.orchestrator.max_itr_reached(count)` loop, confirms it
   returns `True` on the very first pass (`count == 1`) every timestep,
   for every AGS-shaped config. Since the AGS graph is a closed loop
   (`surface → injection_well → horizontal_well → production_well →
   surface`, with the surface's outlet feeding the injection well's inlet
   again on the *next* timestep's single pass), the circuit is solved
   exactly once per timestep with no inner convergence check at all. The
   multi-timestep change this produces (confirmed on
   `examples/AGS_new/AGS_H2O_webapp_native.yml`: `production_well_T` drops
   336.7 K → 331.0 K over the first ~5 of 20 timesteps) is the closed
   loop's own cold-start fixed-point convergence — a numerical artifact of
   the solve order, not simulated physical time.
2. Independently, the wellbore heat-loss physics
   (`units/native/well/base.py`'s `_compute_Q_loss`, an Adams-2015/Ramey-
   style transient-conduction model keyed on dimensionless time `_t_d`)
   never advances for any well under `SystemNative`: `_t_d_old` and
   `time_step` are only ever mutated by `update_dimensionless_time_old()`,
   and nothing calls that method for any well here. Instrumented directly
   (temporarily reverting the placeholders to `pass` for a local,
   uncommitted debugging run, then restoring them): `time_step=0` and
   `t_d_old=0.0` on **all 20** outer-loop passes, for `injection_well`,
   `horizontal_well`, and `production_well` alike — `_t_d` is recomputed
   to the identical value (594.66...) every single timestep. Even the
   sibling `SystemCPGNative` (which *does* call
   `update_dimensionless_time_old()`, and does have real time-marching)
   only calls it for `injection_well`/`production_well` — never for
   `horizontal_well` — so a reservoir-bearing config would still leave the
   horizontal well's own rock-cooling state pinned at "one year of
   extraction" forever.

**Fixed:** `bada742` (2026-08-04) — "harden old-tango placeholders: silent
pass -> loud failure." The no-op `pass` placeholders now
`raise NotImplementedError`, so any multi-timestep run of an AGS-shaped
config fails loudly instead of silently returning wrong numbers —
including `examples/AGS_new/AGS_H2O_webapp_native.yml`, the web app's own
live runtime config. `tests/regtest/test_native.py`'s `testcase6.yml`/
`testcase7.yml` regression cases (the only in-repo tests that exercised
this exact failure mode) were removed 2026-08-05 rather than `xfail`ed,
since old tango isn't being fixed for this (see decision below) — the
equivalent tango_next coverage is tracked as open cells in
`docs/TANGO_vision_and_roadmap.md`'s example-coverage matrix instead.

`tango_next` doesn't have this class of bug, for a more specific reason
than "orchestrator selection isn't a string-collapsing dispatch": its
numerical well component still has a `t_d_old`-equivalent field (same
name, same role) — the field itself wasn't removed. What's different is
that there's no separate, per-unit-type-wireable "advance the old value"
method to forget to call. `solve()` advances `t_d`/`t_d_old` together,
unconditionally, every time it runs; and `SystemBCIteration`'s inner
T-convergence loop (`system_bc_iteration.py`) snapshots every component's
non-frozen persistent field *categorically* (`Component.
snapshot_convergence_state()`/`restore_convergence_state()` — any field
`solve()` mutates and that must survive across timesteps, not a
hand-maintained list) before each of its inner re-solve attempts, so
however many inner iterations a timestep needs, only the final, converged
attempt's advance survives — one real advance per physical timestep,
guaranteed generically rather than per-field. There's no code path
structurally capable of leaving `t_d_old` un-advanced the way
`SystemNative`/`SystemCPGNative` did for `horizontal_well`.

Decision (2026-08-03): not fixing the underlying physics gap in
`src/tango`. AGS/no-reservoir designs are treated as having no
trustworthy legacy baseline for comparison. Full writeup:
`docs/tango_next_progress_summary_aug_2026.md`, `docs/tango_next_tasks.md`
§"AGS sweep parity" and "Open items" sections.

## `== "yes"` string-comparison trap

Several `src/tango` fields (`controlled_power_generation`,
`bypass_processing` in `orchestrators/BC_calculator.py`) gate behavior
with `if value == "yes":` instead of a truthy check. Writing
`controlled_power_generation: True` in YAML silently disables the
feature — PyYAML parses `True` as a Python boolean, and `True == "yes"`
is `False`. Only the literal string `yes` activates these fields.

`tango_next` avoids this entirely: all boolean fields are proper
booleans checked with `if value:`, enforced by `CONTRIBUTING.md`'s YAML
Style section (YAML configs use Python-style `True`/`False`).

**Avoided by design since:** `735745a` (2026-06-10, "stand up tango_next
module scaffold") — no specific fix commit exists, since tango_next never
had this stringly-typed pattern to begin with.

## `check_fracing` doesn't gate what its name implies

`bc_iteration.check_fracing` in `src/tango` only gates the flow-rate cap
(`if mass_rate > fracing_flow(): mass_rate = fracing_flow()`). The
injection-pressure adjustment (`test_p` update) runs regardless of this
flag — two separate fracing mechanisms exist, but only one is labeled a
"fracing check," which reads as controlling both.

`tango_next` replaces both mechanisms with the explicit `InjectionPolicy`
enum, so there's no separately-named flag whose scope doesn't match its
name.

**Fixed:** `6f66171` (2026-06-12) — "docs + tango_next: InjectionPolicy
enum, BC iteration design, AI error agent vision."

## `fracing_flow` mixes a wellbore diameter into a term that should be a radius

`src/tango/orchestrators/BC_calculator.py::fracing_flow()` computes the
flow-induced fracking threshold via the standard Thiem/Darcy steady-state
radial-flow equation, `q = 2πhkΔP / (μ·ln(re/rw))`, where both `re` and `rw`
are radii. Old tango halves `well_spacing` to get `re` (`re =
self.reservoir.specs.well_spacing / 2.0`) but does **not** halve the
wellbore term — `rw = self.inj_well._specs.diameter`, the full diameter.
`diameter` is confirmed elsewhere in old tango
(`units/native/well/base.py`, e.g. `0.25·π·diameter²` for cross-sectional
area, `epsilon / diameter` for relative roughness) to be a genuine full
diameter, not a radius stored under a misleading name — and the method's
own docstring labels the term "\\(r_w\\): Wellbore radius (m)" while the
code assigns it the diameter. `ln(re/rw)` therefore mixes a true radius
with a true diameter, which is off by a flat `-ln(2)` relative to the
correct radius-only form — not one of the legitimate alternate Darcy forms
(e.g. `ln(2·re/D)`), which stay internally consistent by keeping both
terms in the same units.

`tango_next`'s `fluid_utils.fracking_flow()` halves both consistently:
`re = well_spacing / 2.0`, `rw = wellbore_diameter / 2.0`.

**Fixed:** introduced directly in `tango_next` (no old-tango behavior
carried forward to later correct) as part of `InjectionPolicy.
MANUAL_FRACKING_CHECK`, 2026-08-11 (uncommitted as of 2026-08-12 — update
this hash once committed).

## Non-convergence silently swallowed instead of raised

`src/tango` has this exact pattern in more than one place:

- `orchestrators/native.py`'s `max_itr_reached()` (the direct ancestor of
  `tango_next`'s T-convergence check — `tango_next`'s tolerance/iteration
  constants were deliberately matched to
  `CONVERGENCE_CRITERIA["dT_surface"]`/`["max_num_itr"]` here) does
  `logging.warning(...)` and returns `True` to exit the loop when the
  iteration budget is exhausted — no exception, just a log line, and the
  caller proceeds using whatever state the last iteration left behind.
- `orchestrators/BC_calculator.py:288` and `:369` (the `controlled_power_generation`
  mass-rate search — a Hotmaps-only mechanism that targets a thermal power
  output via `mass_rate_test`/`averaged_df`, unrelated to fracing and not
  represented by `InjectionPolicy` at all, per that enum's own docstring)
  are worse still: `if iter_count == max_iterations - 1: mass_rate =
  mass_rate_guess` — not even a warning, just silently using the last,
  unconverged guess.

`tango_next`'s `SystemBCIteration._converge_injection_T` originally
mirrored this same pattern (`logger.warning(...)` on exhaustion, no
exception). Now `raise`s `ConvergenceError` instead (already existed in
`core/errors.py`, no new exception class needed), so non-convergence is a
hard failure a caller can't silently miss. Audited the rest of
`tango_next` for the same silent-swallow pattern (`logger.warning`, bare
`except`, other max-iteration loops) — this was the only instance.

**Fixed:** `62b1d8d` (2026-08-04) — "fix(system_bc_iteration): raise
ConvergenceError instead of warning on T-loop exhaustion, parameterize
max iterations."

## Convergence loop can commit a result computed from mixed fresh/stale state

`src/tango`'s `FlowRateCalculator.iterator()` (`BC_calculator.py`) mutates
`reservoir._energy_extracted` (a cumulative, timestep-persistent quantity)
on every outer iteration, via `reservoir.py`'s `update_energy_extracted()`
— but the injection temperature that calculation uses is read from
whatever the *previous* iteration's surface solve left in `outlet_fluid`,
not the current iteration's own converged value (surface is solved *after*
the reservoir within each iteration, so the reservoir is always one step
behind it). Since the outer loop's convergence check only tests
`test_p`/`mass_rate`/`inlet_p` — not this specific quantity — it can
declare "converged" and commit `_energy_extracted` computed from an
injection temperature that's one iteration stale relative to what the
same pass just finished computing.

This is a real structural defect regardless of whether it happens to
change any specific number: `tango_next` avoids the whole *class* of it by
construction, not case by case. `SystemBCIteration._converge_injection_T`
snapshots every component's state once per timestep, then restores and
fully re-solves the *entire* circuit — reservoir included — on every
inner iteration, checking convergence only after each complete pass. By
the iteration where convergence is declared, every value used in any
calculation is guaranteed to come from that same, fully current pass —
there is no way for a `tango_next` component to compute a "final" result
from a mix of this-iteration and prior-iteration state.

**Note on scope**: this is documented here as a real, structurally-avoided
bug class, checked directly against `flexible_SF_manual.yml` — injection
temperature stabilizes within 1-2 iterations there, so "stale" and
"current" are identical to 6+ decimal places, meaning this specific bug
class doesn't measurably affect that comparison. It's recorded here for
what it structurally prevents, not as an explanation tied to any one
observed number.

**Avoided by design since:** `2ae784e` (2026-08-03) — "refactor(tango_next):
cascade mark_all_stale(), let reservoir converge with the circuit," the
commit that established `Component.snapshot_convergence_state()`/
`restore_convergence_state()`'s categorical (not per-field) restore. No
single "fix" commit exists in the usual sense — this was tango_next's
design from when the T-convergence loop was first built, not a
subsequently-discovered-and-patched bug.

## `NativeEconomicComponent` double-counted well mobilization cost across split physics sub-components

`src/tango`'s well-cost model (`wells.py`'s gengeo formula) has a fixed
per-well mobilization term (`+275300`, before PPI/multiplier scaling) that
applies once per *well*, not once per physics sub-component. A well split
into multiple physics components for other reasons — e.g. `hydro_df_electric.yml`'s
production well is modeled as `production_well_lower` (4000 m) +
`production_well_upper` (1000 m, carries the downhole pump) — is still
ONE well for costing purposes. Old tango's own reference files reflect
this correctly: `flexible_SF_manual.yml`/`flexible_DF_manual.yml`'s
`production_well.well_length_seq: [5000.]` is the COMBINED total depth
(4000 + 1000), applied through the gengeo formula as a single section —
confirmed with Chad directly (undocumented anywhere in `src/tango` itself;
the field's actual intent — letting cost vary by OUTER/casing diameter
per depth segment, independent of the inner flow diameter physics uses —
is verbal-knowledge-only, not written down anywhere in the repo).

This was initially misdiagnosed (2026-08-10, same day, corrected before
any of the wrong version was committed) as a data-entry bug in the two
example files — on the mistaken assumption `well_length_seq` should equal
`well_length` alone — and "fixed" by changing `[5000.]` to `[4000.]` in
both files. That was wrong and was reverted.

The REAL bug was in `tango_next`'s own `NativeEconomicComponent`
(`src/tango_next/components/economic/native.py`), not in old tango or its
example files: it combined production-side well components by summing
each one's INDEPENDENTLY-costed gengeo-formula result — i.e. costing
`production_well_lower` (4000 m) and `production_well_upper` (1000 m) as
two separate wells, each paying its own `+275300` mobilization fee, and
each squared independently in the formula's `0.105*L²` term
(`4000² + 1000² = 17,000,000` vs. the correct combined
`5000² = 25,000,000` — the formula is NOT linear in length, so this isn't
just a double-counted constant, it changes the quadratic term's
contribution too).

**Fixed** (uncommitted as of 2026-08-10 — update this hash once
committed): `NativeEconomicComponent._compute_well_capex`/new helper
`_combined_production_length_and_diameter` now sum every production-side
`WellComponent`'s length into ONE total depth and cost it through the
gengeo formula exactly once, matching old tango's actual (correct)
design. Verified: `CAPEX_well` now matches old tango to the exact digit
(`36,506,133.65678038`) for both `flexible_SF_manual.yml` and
`flexible_DF_manual.yml` — previously it was off by design, whichever
direction the (wrong) example-file edit happened to push it.

`tango_next` doesn't yet have a real `well_length_seq` equivalent
(varying outer/casing diameter by segment) — tracked as a planned,
explicitly-optional future feature in `docs/tango_next_tasks.md`'s open
items, defaulting to today's single-combined-section behavior when
unspecified.

## Auto mass flow rate convergence never re-solves temperature

`src/tango`'s `FlowRateCalculator.iterator()` (`BC_calculator.py`), under
`mass_rate.type: automatic`, jointly updates injection wellhead pressure
(`test_p += target_p - inj_well.outlet_fluid.P`, a Newton-style step) and
mass rate (`mass_rate = self.fracing_flow()`, a Picard step) every outer
iteration — but injection temperature is never independently re-solved
for the new `(test_p, mass_rate)` pair. Instead, `T` is read straight from
`self.surface.outlet_fluid.T`, i.e. whatever the *previous* outer
iteration's single forward pass happened to leave it at. The outer loop's
own convergence check (`iterator()`'s `rel_tol_test_p`/`rel_tol_mass_rate`/
`rel_tol_inlet_p`, tolerance `1e-4`) never tests whether temperature is
actually self-consistent with the pressure/mass-rate pair it just
converged — it can and does declare "converged" while `T` is still
catching up.

This is wrong, not a reasonable time-saving shortcut: a genuine
fixed-point solution requires every state variable that depends on the
others to be simultaneously self-consistent. Pressure and mass rate both
change every iteration, and temperature depends on both (via density and
viscosity in `fracing_flow()`, and via the whole circuit's stream
solve) — carrying `T` forward uncorrected is silently solving a *different,
easier* problem (a lagged, under-relaxed joint update) rather than the
real one, with no signal that it's happening.

**Confirmed by direct instrumentation (2026-08-13):** traced every outer
iteration's `(test_p, mass_rate, outlet_T)` in both codebases side by side
against `flexible_SF_manual.yml`/`hydro_sf_electric.yml`'s `automatic`/
`AUTO_BOTH` mode. At `max_mass_rate=100` (fracing-driven flow, ~163-180
kg/s, stays comfortably clear of the cap the whole time) both codebases
land on the same fixed point (`test_p` to within 0.026%) — the lagged-T
shortcut happens not to matter there. At `max_mass_rate=150` (fracing-driven
flow hovers close enough to the cap, ~162-178 kg/s, that the constraint is
only marginally active) old tango's loop "converges" in 5 outer iterations
to `test_p ≈ 7.103 MPa`; solving the real, temperature-self-consistent
problem (below) converges — more slowly, 34 iterations, since it's a
strictly harder problem — to `test_p ≈ 7.338 MPa`. A genuine ~3.3%
discrepancy, not rounding noise: ruled out property-derivative
steepening directly (`dρ/dP`, `dρ/dT` both smooth across the whole
349-360 K / 55 MPa operating window, varying <2%) before concluding this
is an algorithmic gap rather than a sensitive-physics artifact.

`tango_next`'s `SystemBCIteration._converge_injection_both`
(`orchestrators/system_bc_iteration.py`) calls `_converge_injection_T`
every single outer iteration: restore the entire circuit to its
start-of-timestep snapshot, fully re-solve, and iterate until injection
temperature itself stabilizes (`_DT_SURFACE_TOL`) — *before* computing the
pressure residual or the new `fracking_flow()` estimate. The outer Picard
step therefore operates on the true composed map
`p → T*(p) → outlet.P(T*(p))`, not an approximation of it. This is the
same structural guarantee already documented in "Convergence loop can
commit a result computed from mixed fresh/stale state" above — this entry
is a second, independently-discovered instance of that same bug class,
this time affecting the auto-mass-rate/pressure solve rather than
cumulative energy extraction.

**Not fixed in old tango** (established policy: legacy numerics aren't
being patched) — **avoided by design in `tango_next` since `5a46894`**
(2026-08-12, "feat(tango_next): implement InjectionPolicy.AUTO_BOTH").
`tests/regtest/test_tango_next.py::test_auto_both_matches_old_tango_automatic`
deliberately uses `max_mass_rate=100` to stay clear of this gap and assert
a tight (0.1%) parity tolerance; it is not evidence the two codebases
agree in general, only that they agree where old tango's shortcut happens
not to bite.

**Open follow-up:** which of the two converged values is physically
correct hasn't been independently confirmed — `tango_next`'s slower
answer is consistent with genuinely finding the self-consistent solution,
but that hasn't been verified beyond "old tango never checks, so its
speed isn't evidence of correctness." An intern is implementing Aitken's
process to accelerate `tango_next`'s T-convergence loop
(`docs/tango_next_tasks.md`'s injection-T-guess-robustness section); once
that lands, it becomes cheap to confirm the slow crawl has actually
reached its true fixed point rather than just satisfying `self.tolerance`
prematurely.

## AGS closed loop has no pump anywhere — circulation runs on thermosiphon effect alone

`examples/tango_next/AGS_direct_heat.yml`'s closed loop (`injection_well →
horizontal_well → production_well → surface → back to injection_well`)
had no pressure-adding device anywhere in it: `injection_well`/
`production_well` are both the plain, non-pump well types, and the
surface plant's `power_plant.nodes` was just `inlet (Source) → dh_hx
(SimpleHeatExchanger) → outlet (Sink)` — no `Compressor`, no pump. The
entire loop ran purely on thermosiphon effect (the density difference
between the cold, dense descending injection column and the hot, lighter
ascending production column) minus friction, with nothing mechanical to
fall back on if that natural margin ran thin.

**Confirmed this predates `tango_next` — it is a genuine `src/tango` gap,
not a porting regression (2026-08-17).** Old tango's own
`applications/run_AGS_direct_heat_sweep/triemli_dh_base.yml` has the
identical shape: `power_plant_graph.nodes` is `inlet (Source) → DH
(SimpleHeatExchanger) → outlet (Sink)`, no pump node at all. That file
*does* set `production_well.eta_pump: 0.75`, which looks at first glance
like a pump is configured — but it isn't: old tango's own registry
(`src/tango/units/registry.py`) only reads `eta_pump` for the separate
`production_well_pump` unit type (`ProductionWellPumpUnitNative`), and
this config declares `type: 'production_well'` (the plain
`ProductionWellUnitNative`, which never reads `eta_pump` at all — checked
directly in `src/tango/units/native/well/production_well.py`). The field
is dead, unused config — old tango's Triemli AGS model has never had a
working pump anywhere, on either the well side or the surface side.

**Implications, confirmed by direct experiment, not assumed:** built
`opt_AGS_direct_heat.py` (a pymoo NSGA2 search over well depth/loop
length/loop diameter/vertical well diameter/injection pressure/mass flow
rate) against the pump-less model and ran it for real. NSGA2 converged
every one of its 45 pareto designs to (or right against) the same design
corner: `loop_length_m`/`loop_diameter_m` pinned exactly at their floors,
`mass_rate_kg_per_s` pinned exactly at its ceiling, `depth_m` clustered
against its own ceiling. Reading the actual pressure profile at that
converged optimum: `injection_well` outlet ~78.0 MPa (the ~8000 m
descent's hydrostatic gain), `production_well` outlet only 29,493 Pa —
essentially the *entire* hydrostatic gain lost climbing back up, with
friction eating what little was left. Checked that delivered pressure
against the fluid's own saturation pressure at the delivered temperature
(68.7°C): **29,472 Pa — a margin of 21.6 Pa, 0.07%.** NSGA2 hadn't found
"these parameters are free to push to their bounds" (an earlier, wrong
hypothesis floated and retracted the same session, once tested directly)
— it had found the cheapest design that stays *just* above flashing to
vapor, because CAPEX cost pressure (smaller/shorter/higher-flow is
cheaper) had nothing else to push against. A razor's-edge mathematical
optimum, not a physically realistic operating point: real closed-loop
AGS/Eavor-Loop-style systems use thermosiphon effect to *reduce* required
pumping power, not eliminate the pump entirely — running a real wellhead
at 0.07% above its flash point is not something an actual operator would
ever accept as a safety margin.

**Fixed in `tango_next` (2026-08-18):** added a real circulation pump —
`AGS_direct_heat.yml`'s `power_plant.nodes` now has `circ_pump`
(`type: Compressor`, `role: net_electric`) between `dh_hx` and `outlet`,
on the cold/injection leg (matching where real closed-loop AGS systems
actually put the surface circulation pump — pumping cold, subcooled
liquid avoids the cavitation/NPSH risk of pumping fluid already near its
flash point, exactly the state the production wellhead is in). No
`p_out_megapascals` on `circ_pump` itself, deliberately: `injection_pressure`
already hard-sets the pressure on the network's final connection (see
`GraphSurface.set_injection_pressure`); also constraining `circ_pump`'s
own outlet would be a second, independent equation pinning the same
connection — an over-determined system, not a more-constrained one
(mirrors `hydro_df_electric.yml`'s `pump1`/`pump2`, which have no `p_out`
of their own for the identical reason). `dh_hx` needed a new
`pressure_ratio` spec (a *ratio*, not an absolute value, since its actual
inlet pressure varies enormously by design point) once it was no longer
the last node before the network's outlet Sink — added generic
`pressure_ratio` -> TESPy `pr` support to `GraphSurface`'s YAML attribute
translation for this (`components/surface/graph.py`).

Also relaxed `GraphSurface.solve()`'s `InvalidPowerStateError` guard,
which unconditionally raised on any negative `net_power_W` — correct for
a topology that expects net electric *generation* (a turbine that should
always beat its own parasitic pumps), wrong for a pure direct-heat
topology with no generator at all, where negative `net_power_W` (a
circulation pump with nothing generating alongside it) is the only
possible, entirely correct state. Now only raises when an actual
`Turbine` is present among the `net_electric`-tagged nodes.
`DoubletEconomicComponent._compute_lcoe` needed no changes at all — its
by-product-power term was already hardened for exactly this case (see
"`NativeEconomicComponent` double-counted well mobilization cost..."
entry's neighbor further up this file, and that method's own docstring
referencing "~53/500 designs in the Triemli AGS sweep" with negative net
power).

**New TANGO Commandment added** (`CONTRIBUTING.md`): every closed fluid
loop must have an explicit pump/compressor somewhere in it. Partially
enforced in code: `workflows/workflow.py::_check_loop_has_pressure_source`
raises `ConfigError` if a config sets `sim_config.injection_mode` (a
genuine closed loop) but has no well component ending in `_with_pump` and
no `power_plant.nodes` entry of type `Compressor`/`Pump` anywhere.
Deliberately scoped to the WHOLE workflow, not per-loop, since
`tango_next` has no multi-loop/grouped-subsystem support yet (see
`docs/TANGO_vision_and_roadmap.md`'s "Grouped subsystems" open design
question) — there is only ever one fluid circuit per `Workflow` today, so
a whole-workflow check is equivalent to a per-loop one for now. Revisit
once a config can genuinely contain more than one independent fluid loop
(e.g. a future ORC secondary working-fluid loop).
