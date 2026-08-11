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

## Non-convergence silently swallowed instead of raised

`src/tango` has this exact pattern in more than one place:

- `orchestrators/native.py`'s `max_itr_reached()` (the direct ancestor of
  `tango_next`'s T-convergence check — `tango_next`'s tolerance/iteration
  constants were deliberately matched to
  `CONVERGENCE_CRITERIA["dT_surface"]`/`["max_num_itr"]` here) does
  `logging.warning(...)` and returns `True` to exit the loop when the
  iteration budget is exhausted — no exception, just a log line, and the
  caller proceeds using whatever state the last iteration left behind.
- `orchestrators/BC_calculator.py:288` and `:369` (the `AUTO_FLOW`/
  `AUTO_BOTH`-style mass-rate fracing loops) are worse still: `if
  iter_count == max_iterations - 1: mass_rate = mass_rate_guess` — not
  even a warning, just silently using the last, unconverged guess.

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
