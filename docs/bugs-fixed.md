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
(`update_time_dependent_vars`/`update`/`balanced`) are no-op placeholders.
Result: a multi-timestep AGS run silently repeats the exact same solved
state at every timestep after t=0, with no error of any kind.

Confirmed four independent ways: code inspection, reproducing the same
signature on an unrelated pre-existing "validated" example file, a live
debugger walkthrough of the failure (breakpoints in `utils.py`,
`workflows/native_workflow.py`, and `orchestrators/native.py` confirmed
the wrong class gets instantiated and its no-op method actually executes),
and the raw output data itself (`production_well_T` bit-identical for
every year after year 1).

`tango_next` doesn't have this class of bug — orchestrator selection isn't
a string-collapsing dispatch, and `LockedState` would raise immediately if
a component's `solve()` ever silently skipped updating a field it owns.

Decision (2026-08-03): not fixing this in `src/tango`. AGS/no-reservoir
designs are treated as having no trustworthy legacy baseline for
comparison. Full writeup:
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

## `check_fracing` doesn't gate what its name implies

`bc_iteration.check_fracing` in `src/tango` only gates the flow-rate cap
(`if mass_rate > fracing_flow(): mass_rate = fracing_flow()`). The
injection-pressure adjustment (`test_p` update) runs regardless of this
flag — two separate fracing mechanisms exist, but only one is labeled a
"fracing check," which reads as controlling both.

`tango_next` replaces both mechanisms with the explicit `InjectionPolicy`
enum, so there's no separately-named flag whose scope doesn't match its
name.

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
exception). Fixed 2026-08-04: now `raise`s `ConvergenceError` instead
(already existed in `core/errors.py`, no new exception class needed), so
non-convergence is a hard failure a caller can't silently miss. Audited
the rest of `tango_next` for the same silent-swallow pattern
(`logger.warning`, bare `except`, other max-iteration loops) — this was
the only instance.

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
