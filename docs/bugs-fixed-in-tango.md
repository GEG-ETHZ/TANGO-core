# Bugs Found and Fixed

A running record of concrete bugs in legacy `src/tango` that `tango`
either avoids by design or has explicitly fixed, relative to the legacy
behavior. Scope is deliberately narrow: this is not a general `tango`
changelog (see `docs/tango_tasks.md` for that) — only bugs that exist
(or existed) in `src/tango` and are confirmed not to recur in `tango`
belong here.

Entries are added only once a bug is fully confirmed against current
`src/tango` code and verified not to recur in `tango`. Each entry
links to the fuller writeup where one exists.

## Overview

`tango` has been built around a small set of deliberate design
concepts. Several of the bugs below were only findable — or only fixable
by construction, not by patching a symptom — because of one of them:

- **object == config** -- code objects/attributes and config (YAML) stay
  in near-1:1 congruence; when one logical config entity has to be split
  across multiple code objects for other reasons, code that aggregates
  back up to that entity has to know about the split explicitly, rather
  than the split silently drifting out of sync with what the config
  actually describes.
- **standalone simulation** -- any component can be built and run in
  isolation, without spinning up the full circuit, which is what makes it
  possible to isolate a single suspect component's behavior directly
  instead of only observing it through a full end-to-end run.
- **(de)serialization** -- every config and every persisted/serialized
  field round-trips through a validated pydantic schema, not a bare,
  stringly-typed dict.
- **finite values as `StrEnum`** -- any parameter with a small, finite set
  of legal values is an explicit, exhaustively-named `StrEnum`, not a
  loosely-scoped flag or a string compared ad hoc.
- **method encapsulation** -- a class only mutates its own state through
  its own methods; external code never assigns a field directly.
- **locked state** -- state variables update once and only once per
  timestep, with an explicit fresh/stale distinction enforced
  structurally (`LockedState`/`snapshot_convergence_state`), not left to
  convention.
- **explicit failure signaling** -- convergence and physical failures
  raise a typed error instead of logging a warning, silently falling
  back, or letting the caller proceed on stale/unconverged state.
- **descriptive variable names** -- a variable or field representing a
  physical quantity gets a full, descriptive name, never a bare
  single/double-letter symbol lifted straight out of a textbook formula.

Bugs below and the design concept (if any) that let them be caught or
fixed by construction rather than by a one-off patch:

| Bug | Design concept that enabled discovery/fix |
| --- | --- |
| [AGS configs never advance simulated time](#ags-configs-never-advance-simulated-time) | locked state |
| [`== "yes"` string-comparison trap](#-yes-string-comparison-trap) | (de)serialization |
| [`check_fracking` doesn't gate what its name implies](#check_fracking-doesnt-gate-what-its-name-implies) | finite values as `StrEnum` |
| [`fracking_flow` mixes a wellbore diameter into a term that should be a radius](#fracking_flow-mixes-a-wellbore-diameter-into-a-term-that-should-be-a-radius) | descriptive variable names |
| [Non-convergence silently swallowed instead of raised](#non-convergence-silently-swallowed-instead-of-raised) | explicit failure signaling |
| [Convergence loop can commit a result computed from mixed fresh/stale state](#convergence-loop-can-commit-a-result-computed-from-mixed-freshstale-state) | locked state |
| [Old tango's downhole production pump is modeled as perfectly isothermal](#old-tangos-downhole-production-pump-is-modeled-as-perfectly-isothermal) | standalone simulation |
| [`NativeEconomicComponent` double-counted well mobilization cost across split physics sub-components](#nativeeconomiccomponent-double-counted-well-mobilization-cost-across-split-physics-sub-components) | object == config |
| [Auto mass flow rate convergence never re-solves temperature](#auto-mass-flow-rate-convergence-never-re-solves-temperature) | locked state |
| [AGS closed loop has no pump anywhere — circulation runs on thermosiphon effect alone](#ags-closed-loop-has-no-pump-anywhere--circulation-runs-on-thermosiphon-effect-alone) | - |
| [Numerically-marched wells fall one cell short of their declared well_length](#numerically-marched-wells-fall-one-cell-short-of-their-declared-well_length) | - |

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
   (`units/native/well/base.py`'s `_compute_Q_loss`, a Zhang-2011/Ramey-
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
equivalent tango coverage is tracked as open cells in
`docs/TANGO_vision_and_roadmap/README.md`'s example-coverage matrix instead.

`tango` doesn't have this class of bug, for a more specific reason
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
`docs/archive/tango_progress_summary_aug_2026.md`, `docs/tango_tasks.md`
§"AGS sweep parity" and "Open items" sections.

## `== "yes"` string-comparison trap

Several `src/tango` fields (`controlled_power_generation`,
`bypass_processing` in `orchestrators/BC_calculator.py`) gate behavior
with `if value == "yes":` instead of a truthy check. Writing
`controlled_power_generation: True` in YAML silently disables the
feature — PyYAML parses `True` as a Python boolean, and `True == "yes"`
is `False`. Only the literal string `yes` activates these fields.

`tango` avoids this entirely: all boolean fields are proper
booleans checked with `if value:`, enforced by `CONTRIBUTING.md`'s YAML
Style section (YAML configs use Python-style `True`/`False`).

**Avoided by design since:** `735745a` (2026-06-10, "stand up tango
module scaffold") — no specific fix commit exists, since tango never
had this stringly-typed pattern to begin with.

## `check_fracking` doesn't gate what its name implies

`bc_iteration.check_fracking` in `src/tango` only gates the flow-rate cap
(`if mass_rate > fracking_flow(): mass_rate = fracking_flow()`). The
injection-pressure adjustment (`test_p` update) runs regardless of this
flag — two separate fracking mechanisms exist, but only one is labeled a
"fracking check," which reads as controlling both.

`tango` replaces both mechanisms with the explicit `InjectionPolicy`
enum, so there's no separately-named flag whose scope doesn't match its
name.

**Fixed:** `6f66171` (2026-06-12) — "docs + tango: InjectionPolicy
enum, BC iteration design, AI error agent vision."

## `fracking_flow` mixes a wellbore diameter into a term that should be a radius

`src/tango/orchestrators/BC_calculator.py::fracking_flow()` computes the
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

`tango`'s `fluid_utils.fracking_flow()` halves both consistently:
`re = well_spacing / 2.0`, `rw = wellbore_diameter / 2.0`.

**Fixed:** introduced directly in `tango` (no old-tango behavior
carried forward to later correct) as part of `InjectionPolicy.
MANUAL_FRACKING_CHECK`, 2026-08-11 (uncommitted as of 2026-08-12 — update
this hash once committed).

**New TANGO Commandment added** (`CONTRIBUTING.md`): [rule: No opaque short
names for physical quantities](project/contributing.md#rule-descriptive-variable-names) — a bare
`rw`/`re` is exactly what let a diameter and a radius get silently mixed
into the same formula unnoticed; a full name like `wellbore_diameter_m`
vs. `wellbore_radius_m` would have made the mismatch visible at the call
site.

## Non-convergence silently swallowed instead of raised

`src/tango` has this exact pattern in more than one place:

- `orchestrators/native.py`'s `max_itr_reached()` (the direct ancestor of
  `tango`'s T-convergence check — `tango`'s tolerance/iteration
  constants were deliberately matched to
  `CONVERGENCE_CRITERIA["dT_surface"]`/`["max_num_itr"]` here) does
  `logging.warning(...)` and returns `True` to exit the loop when the
  iteration budget is exhausted — no exception, just a log line, and the
  caller proceeds using whatever state the last iteration left behind.
- `orchestrators/BC_calculator.py:288` and `:369` (the `controlled_power_generation`
  mass-rate search — a Hotmaps-only mechanism that targets a thermal power
  output via `mass_rate_test`/`averaged_df`, unrelated to fracking and not
  represented by `InjectionPolicy` at all, per that enum's own docstring)
  are worse still: `if iter_count == max_iterations - 1: mass_rate =
  mass_rate_guess` — not even a warning, just silently using the last,
  unconverged guess.

`tango`'s `SystemBCIteration._converge_injection_T` originally
mirrored this same pattern (`logger.warning(...)` on exhaustion, no
exception). Now `raise`s `ConvergenceError` instead (already existed in
`core/errors.py`, no new exception class needed), so non-convergence is a
hard failure a caller can't silently miss. Audited the rest of
`tango` for the same silent-swallow pattern (`logger.warning`, bare
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
change any specific number: `tango` avoids the whole *class* of it by
construction, not case by case. `SystemBCIteration._converge_injection_T`
snapshots every component's state once per timestep, then restores and
fully re-solves the *entire* circuit — reservoir included — on every
inner iteration, checking convergence only after each complete pass. By
the iteration where convergence is declared, every value used in any
calculation is guaranteed to come from that same, fully current pass —
there is no way for a `tango` component to compute a "final" result
from a mix of this-iteration and prior-iteration state.

**Note on scope**: this is documented here as a real, structurally-avoided
bug class. It was originally checked against `flexible_SF_manual.yml` and
described as leaving "stale" and "current" injection temperature
identical to 6+ decimal places — that description was wrong, and so was
a follow-up estimate (below, for the record) that this bug's effect was
small.

Direct instrumentation of `src/tango`'s live `BC_calculator.py` on
`flexible_SF_manual.yml` (2026-08-28) first showed the outer loop
converges in 2-3 iterations, with the reservoir-facing *injection*
temperature moving only 0.03-0.15 K between the last two iterations at
later timesteps. A sensitivity test against `tango`'s own reservoir
formula (perturbing *injection* temperature by 0.1 K) measured
`dT_out/dT_inj ≈ -0.71` (damping, not amplifying), suggesting this bug
contributes only ~0.02-0.1 K of reservoir-outlet difference — nowhere
near the several-Kelvin gaps observed. **That estimate measured the
wrong quantity.** The reservoir's impedance (pressure) and
depletion-coefficient (temperature) calculations don't read the
*injection* temperature's staleness — they read `self.outlet_fluid`,
i.e. the reservoir's *own* previous output, which old tango's
`process_stream()` uses *before* that same call's `stream_interface()`
overwrites it. Within a single timestep's Gauss-Seidel loop, that means
every iteration (including the final, "converged" one) computes its
result from `self.outlet_fluid` as it stood after the *previous*
iteration — never from the value the current iteration is about to
produce. The quantity that actually gets committed each timestep (and
carried forward to seed the next one) is therefore never a true fixed
point of the reservoir's own formula, no matter how many Gauss-Seidel
iterations run.

This was confirmed exactly, not approximately: feeding `tango`'s
standalone `LumpedReservoir` old tango's *actual* previous-iteration
`outlet_fluid` state (extracted from live instrumentation, one
Gauss-Seidel iteration before old tango's own final/committed iteration
each timestep) as `T_out_prev`/`P_out_prev`, together with that same
final iteration's `(T_inj, P_inj, mass_rate)`, reproduces old tango's
committed `T_out` **and** `P_out` to displayed precision at every one of
8 timesteps:

```text
 t      old_T_out       tn_T_out      diffT        old_P_out       tn_P_out      diffP
 1     463.000000     463.000000   0.000000     47969025.083   47969025.083      0.000
 2     462.999953     462.999953   0.000000     47966319.165   47966319.165      0.000
 3     462.982810     462.982810   0.000000     47964879.775   47964879.775      0.000
 4     461.888600     461.888600   0.000000     47960768.568   47960768.568      0.000
 5     449.447383     449.447383   0.000000     47920329.639   47920329.639      0.000
 6     424.074284     424.074284   0.000000     47814886.130   47814886.130     -0.000
 7     413.708583     413.708583   0.000000     47759702.949   47759702.949     -0.000
 8     409.351072     409.351072   0.000000     47733781.525   47733781.525      0.000
```

This is a complete, exact explanation, not a partial or approximate one:
`tango`'s reservoir formula (coefficients, `_depletion_curve`
piecewise erfc/exp, CoolProp backend/call convention) is bit-identical
to old tango's own — confirmed directly, including a standalone
side-by-side CoolProp property comparison at matched `(P, T)` returning
zero difference to full float64 precision — so once fed the exact state
old tango's own formula actually used, there is *nothing left to
diverge*. The entire several-Kelvin gap between old tango and
`tango` on this case originates here, not from any separate,
undiscovered formula bug and not primarily from the isothermal-pump
issue documented below (whose direct effect on reservoir temperature
was separately isolated and found to be about two orders of magnitude
smaller — see that entry).

**Why the effect is so uneven across timesteps**: the reservoir's outlet
temperature is `T_out = γ(ψ)·ΔT + T_inj`, where `ψ` (cumulative fractional
energy extraction) is exactly the accumulator this staleness perturbs
every timestep, and `γ(ψ)` (`LumpedReservoir._depletion_curve`,
`src/tango/components/reservoir/lumped.py`) is the Adams-2015
depletion curve — a sigmoid that sits flat near 1.0 (no depletion) for
small `ψ`, falls steeply through a "thermal breakthrough" transition,
then flattens onto a lower plateau. Computing `dγ/dψ` directly from
`tango`'s own reservoir at the actual `ψ` this run traces through
shows exactly why the divergence appears where it does and nowhere else:

```text
 t      psi      gamma    dgamma/dpsi   diff(T_out, tango vs old tango)
 1    0.0366    1.0000      -0.0000        -0.000000
 2    0.0732    1.0000      -0.0001        -0.000000
 3    0.1097    0.9998      -0.0212        -0.000123
 4    0.1462    0.9899      -0.9233        -0.026586
 5    0.1837    0.8647      -6.4985        -1.558634
 6    0.2184    0.6019      -4.7430        -4.770431
 7    0.2416    0.5151      -1.8772        -3.551869
 8    0.2609    0.4882      -0.9485        -1.971310
```

The shape of `|dγ/dψ|` — near-zero, then a sharp peak (~6.5, a
65,000×-larger sensitivity than at t=1-2) around t=5, then decaying —
tracks the shape of the observed divergence almost exactly, one step
ahead of it (`ψ` at timestep `t` sets `T_out` at `t`, so a sensitivity
peak at t=5 shows up as maximal *divergence* once it's compounded
through one more step, at t=6). Away from breakthrough, `γ` is
essentially flat, so the one-iteration-stale `outlet_fluid` this bug
introduces every timestep gets multiplied by ~zero and is invisible;
during breakthrough, the identical per-timestep staleness gets
multiplied by a derivative orders of magnitude larger, purely because of
where on the curve the run happens to sit — not because the underlying
staleness itself grew. This is why the earlier isolated `dT_out/dT_inj`
sensitivity test (which perturbs *injection* temperature, an input the
reservoir formula barely uses for anything except this same `ψ`
pathway) still measured meaningful damping at a single perturbation,
while the real bug — a standing, uncorrected offset in `outlet_fluid`
present from the very first timestep's *pressure* channel onward (a
~250 Pa impedance-driven seed at t=1, confirmed to trace to a ~1 MPa gap
between the reservoir's cold-start pressure and its actual
first-iteration output, not any config or CoolProp discrepancy) —
compounds through the accumulator every single step regardless.

**Avoided by design since:** `2ae784e` (2026-08-03) — "refactor(tango):
cascade mark_all_stale(), let reservoir converge with the circuit," the
commit that established `Component.snapshot_convergence_state()`/
`restore_convergence_state()`'s categorical (not per-field) restore. No
single "fix" commit exists in the usual sense — this was tango's
design from when the T-convergence loop was first built, not a
subsequently-discovered-and-patched bug. tango now takes a "snapshot" of the
state of the system at a timestep and iterates injection temperature convergence
on that snapshot, which leads to faster and more accurate convergence
by establishing a true fixed point problem and allowing the implementation of
aitkens accelerator.

## Old tango's downhole production pump is modeled as perfectly isothermal

`src/tango`'s `ProductionWellPump.update_inlet_fluid_state_with_pump()`
(`well/production_well_pump.py`) raises the fluid's pressure by
`_dP_pump` and explicitly holds temperature fixed at the pre-pump value:

```python
def update_inlet_fluid_state_with_pump(self) -> None:
    P = self._inlet_pressure_tmp + self._dP_pump
    T = self.inlet_fluid.T
    self.inlet_fluid.updatePT(P, T)
```

The pump *work* itself is computed correctly and separately (via
`_update_w_pump()`'s own enthalpy-difference calculation, used for power
reporting), but that work is never fed back into the fluid state the
rest of the well/surface circuit sees — the compression is treated as a
free, adiabatic-and-reversible-at-zero-temperature-rise process rather
than a real irreversible one. Any real pump necessarily raises the
fluid's temperature by an amount set by its efficiency: less-than-100%
efficiency work always shows up as extra heat in the fluid, not just as
pressure. Holding `T` fixed silently discards that heat rather than
modeling where it goes.

This is an outright physics error, not a design tradeoff or a documented
simplification — nothing in `src/tango` states or justifies an
isothermal-pump assumption anywhere, and the separately-computed
`_w_pump` value proves the code already has everything it needs (inlet
state, pressure rise, `eta_pump`) to compute the real temperature rise
instead of discarding it.

**Quantified directly** (`tests/regtest/test_old_new_economic_parity.py`,
`flexible_DF_manual.yml`/`hydro_df_electric.yml`): evaluated on the same
natural-march (pre-pump) state, the isentropic-efficiency pump work is
285,318 W vs. 185,975 W for the isothermal formula — a ~53% difference in
pump work for this config, independently corroborated by a direct
CoolProp-derivative estimate at typical wellhead conditions (~400 K)
before the isentropic model existed at all. Switching `tango`'s
pump from a naive hydraulic estimate to old tango's own isothermal
formula (2026-08-10) had already closed the bulk of a much larger LCOE
gap (+16.1%/+11.5% -> -1.1%/-1.0%); switching again to the
isentropic-efficiency model (2026-08-14) reopened a smaller, deliberate
residual gap (LCOE re-measured 2026-08-28 at SF +8.1%, DF +5.9% — the
larger part of that widening is the convergence-loop fix described
above, not this pump change alone).

**Why it matters — and why it's smaller than it first looked**: the
production well's outlet temperature feeds the surface component, so a
first guess was that a warmer isentropic-pump outlet would propagate
through the injection well into a warmer reservoir injection temperature
every timestep, compounding cumulatively into a large, steadily-growing
reservoir-temperature difference the way the entry above's staleness
does. **A direct, isolated test contradicts this.** Monkeypatching
`tango`'s pump model back to old tango's isothermal formula (holding
everything else in `tango` fixed — same config, same
surface/injection-well/reservoir code) and re-running
`hydro_sf_electric.yml` end-to-end shows the isentropic pump's actual,
isolated effect on reservoir temperature is tiny (≲0.02 K, plateauing)
and runs in the *opposite* direction from the naive story:

```text
     pump_T isen   pump_T isot   T_inj isen   T_inj isot   Eext isen   Eext isot
t=6    411.5857      411.1535     353.5208     353.5575    4.284e15    4.283e15
```

The isentropic pump does make the produced fluid warmer at the wellhead
(411.59 K vs. 411.15 K, as expected — it adds real heat). But this
config's surface power plant then extracts *more* energy from that
warmer stream, so the fluid returning down the injection well ends up
*colder*, not warmer (353.52 K vs. 353.56 K) — meaning the isentropic
pump makes `tango`'s reservoir deplete *very slightly faster* than
an isothermal pump would, not slower. This is a real, config-dependent
effect, but it is roughly two orders of magnitude too small to be a
major contributor to the reservoir-temperature gap — see
[Convergence loop can commit a result computed from mixed fresh/stale state](#convergence-loop-can-commit-a-result-computed-from-mixed-freshstale-state)
above, which was proven (by exact reconstruction of old tango's actual
internal state) to be the complete explanation for that gap instead.

What this bug *does* still substantially affect is the pump-power number
itself (quantified above at ~53%), which feeds directly into LCOE
through the parasitic-load and economic calculations — that part of the
original diagnosis holds; it just isn't the reservoir-depletion story.

**Avoided by design since:** `tango`'s
`NumericalProductionWellWithPump.solve()`
(`components/well/numerical.py`) uses a standard isentropic-efficiency
pump model instead — entropy is evaluated at the true inlet state,
enthalpy at the candidate discharge pressure is computed isentropically,
then efficiency-derated to the actual enthalpy rise, then flashed back to
a real outlet temperature (`FluidState.with_PS` / `with_HP`). See that
method's own docstring for the full derivation of why the
isothermal/isentropic gap is temperature-driven (`dH|_S - dH|_T =
T*alpha*V*dP`) and grows as the fluid runs warmer relative to its own
critical point.

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
confirmed by the maintainers (undocumented anywhere in `src/tango` itself;
the field's actual intent — letting cost vary by OUTER/casing diameter
per depth segment, independent of the inner flow diameter physics uses —
is verbal-knowledge-only, not written down anywhere in the repo).

This was initially misdiagnosed (2026-08-10, same day, corrected before
any of the wrong version was committed) as a data-entry bug in the two
example files — on the mistaken assumption `well_length_seq` should equal
`well_length` alone — and "fixed" by changing `[5000.]` to `[4000.]` in
both files. That was wrong and was reverted.

The REAL bug was in `tango`'s own `NativeEconomicComponent`
(`src/tango/components/economic/native.py`), not in old tango or its
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

`tango` doesn't yet have a real `well_length_seq` equivalent
(varying outer/casing diameter by segment) — tracked as a planned,
explicitly-optional future feature in `docs/tango_tasks.md`'s open
items, defaulting to today's single-combined-section behavior when
unspecified.

## Auto mass flow rate convergence never re-solves temperature

`src/tango`'s `FlowRateCalculator.iterator()` (`BC_calculator.py`), under
`mass_rate.type: automatic`, jointly updates injection wellhead pressure
(`test_p += target_p - inj_well.outlet_fluid.P`, a Newton-style step) and
mass rate (`mass_rate = self.fracking_flow()`, a Picard step) every outer
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
viscosity in `fracking_flow()`, and via the whole circuit's stream
solve) — carrying `T` forward uncorrected is silently solving a *different,
easier* problem (a lagged, under-relaxed joint update) rather than the
real one, with no signal that it's happening.

**Confirmed by direct instrumentation (2026-08-13):** traced every outer
iteration's `(test_p, mass_rate, outlet_T)` in both codebases side by side
against `flexible_SF_manual.yml`/`hydro_sf_electric.yml`'s `automatic`/
`AUTO_BOTH` mode. At `max_mass_rate=100` (fracking-driven flow, ~163-180
kg/s, stays comfortably clear of the cap the whole time) both codebases
land on the same fixed point (`test_p` to within 0.026%) — the lagged-T
shortcut happens not to matter there. At `max_mass_rate=150` (fracking-driven
flow hovers close enough to the cap, ~162-178 kg/s, that the constraint is
only marginally active) old tango's loop "converges" in 5 outer iterations
to `test_p ≈ 7.103 MPa`; solving the real, temperature-self-consistent
problem (below) converges — more slowly, 34 iterations, since it's a
strictly harder problem — to `test_p ≈ 7.338 MPa`. A genuine ~3.3%
discrepancy, not rounding noise: ruled out property-derivative
steepening directly (`dρ/dP`, `dρ/dT` both smooth across the whole
349-360 K / 55 MPa operating window, varying <2%) before concluding this
is an algorithmic gap rather than a sensitive-physics artifact.

`tango`'s `SystemBCIteration._converge_injection_both`
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
being patched) — **avoided by design in `tango` since `5a46894`**
(2026-08-12, "feat(tango): implement InjectionPolicy.AUTO_BOTH").
`tests/regtest/test_tango.py::test_auto_both_matches_old_tango_automatic`
deliberately uses `max_mass_rate=100` to stay clear of this gap and assert
a tight (0.1%) parity tolerance; it is not evidence the two codebases
agree in general, only that they agree where old tango's shortcut happens
not to bite.

**Open follow-up:** which of the two converged values is physically
correct hasn't been independently confirmed — `tango`'s slower
answer is consistent with genuinely finding the self-consistent solution,
but that hasn't been verified beyond "old tango never checks, so its
speed isn't evidence of correctness." Aitken's process was added to accelerate `tango`'s T-convergence loop
(`docs/tango_tasks.md`'s injection-T-guess-robustness section); once
that lands, it becomes cheap to confirm the slow crawl has actually
reached its true fixed point rather than just satisfying `self.tolerance`
prematurely.

## AGS closed loop has no pump anywhere — circulation runs on thermosiphon effect alone

`templates/AGS_direct_heat.yml`'s closed loop (`injection_well →
horizontal_well → production_well → surface → back to injection_well`)
had no pressure-adding device anywhere in it: `injection_well`/
`production_well` are both the plain, non-pump well types, and the
surface plant's `power_plant.nodes` was just `inlet (Source) → dh_hx
(SimpleHeatExchanger) → outlet (Sink)` — no `Compressor`, no pump. The
entire loop ran purely on thermosiphon effect (the density difference
between the cold, dense descending injection column and the hot, lighter
ascending production column) minus friction, with nothing mechanical to
fall back on if that natural margin ran thin.

**Confirmed this predates `tango` — it is a genuine `src/tango` gap,
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

**Fixed in `tango`:** every closed fluid loop must have an explicit
circulation-pressure device somewhere in it — a new TANGO Commandment
(`CONTRIBUTING.md`), partially enforced in code:
`workflows/workflow.py::_check_loop_has_pressure_source` raises
`ConfigError` if a config sets `sim_config.injection_mode` (a genuine
closed loop) but has no well component ending in `_with_pump` and no
`power_plant.nodes` entry of type `Compressor`/`Pump`/`PumpOrValve`
anywhere. `AGS_direct_heat.yml`'s `power_plant.nodes` now has
`circulation_control` (`type: PumpOrValve`, `role: net_electric`) between
`dh_hx` and `outlet`, on the cold/injection leg (matching where real
closed-loop AGS systems actually put the surface circulation device —
handling cold, subcooled liquid avoids the cavitation/NPSH risk of
handling fluid already near its flash point, exactly the state the
production wellhead is in).

`type: PumpOrValve` (not a plain `Compressor`) is what actually makes
this fix correct rather than just present: real closed-loop AGS/
Eavor-Loop-style systems get part of their required circulation pressure
for free from thermosiphon effect (the density difference between the
cold descending injection leg and the hot ascending production leg), and
depending on the specific design (depth, loop geometry, mass flow, target
injection pressure) that natural pressure can either exceed or fall short
of what's needed — a device fixed as one type or the other is physically
wrong for whichever regime it doesn't match (a passive throttle can't
raise pressure; a pump forced to accept a pressure it doesn't need would
have to reject work, which no real device does). `GraphSurface` builds
TWO complete TESPy networks for a `PumpOrValve` node — one resolving it
to a passive `Valve`, one to a real `Compressor` (see `_NetworkBundle`/
`_build_bundle`) — and each `solve()` tries the `Valve` network first,
falling back to the `Compressor` network via
`_check_pump_or_valve_validity` whenever the valve network would need to
raise pressure (impossible for a passive device). This models both real
operating regimes correctly and automatically, per design point, with no
manual per-config choice.

No `p_out_megapascals` on `circulation_control` itself, deliberately:
`injection_pressure` already hard-sets the pressure on the network's
final connection (see `GraphSurface.set_injection_pressure`); also
constraining `circulation_control`'s own outlet would be a second,
independent equation pinning the same connection — an over-determined
system, not a more-constrained one (mirrors `hydro_df_electric.yml`'s
`pump1`/`pump2`, which have no `p_out` of their own for the identical
reason). `dh_hx` needed a new `pressure_ratio` spec (a *ratio*, not an
absolute value, since its actual inlet pressure varies enormously by
design point) once it was no longer the last node before the network's
outlet Sink — added generic `pressure_ratio` -> TESPy `pr` support to
`GraphSurface`'s YAML attribute translation for this
(`components/surface/graph.py`).

Also relaxed `GraphSurface.solve()`'s `InvalidPowerStateError` guard,
which unconditionally raised on any negative `net_power_W` — correct for
a topology that expects net electric *generation* (a turbine that should
always beat its own parasitic pumps), wrong for a pure direct-heat
topology with no generator at all, where negative `net_power_W` (a
circulation device with nothing generating alongside it) is the only
possible, entirely correct state. Now only raises when an actual
`Turbine` is present among the `net_electric`-tagged nodes.
`DoubletEconomicComponent._compute_lcoe` needed no changes at all — its
by-product-power term was already hardened for exactly this case (see
"`NativeEconomicComponent` double-counted well mobilization cost..."
entry's neighbor further up this file, and that method's own docstring
referencing "~53/500 designs in the Triemli AGS sweep" with negative net
power).

`_check_loop_has_pressure_source` is deliberately scoped to the WHOLE
workflow, not per-loop, since `tango` has no multi-loop/
grouped-subsystem support yet (see `docs/TANGO_vision_and_roadmap/README.md`'s
"Grouped subsystems" open design question) — there is only ever one
fluid circuit per `Workflow` today, so a whole-workflow check is
equivalent to a per-loop one for now. Revisit once a config can genuinely
contain more than one independent fluid loop (e.g. a future ORC
secondary working-fluid loop).

## Numerically-marched wells fall one cell short of their declared well_length

`src/tango/units/native/well/base.py`'s marching loop
(`for i in range(1, self._num_cells)`, `base.py:161`) sizes its
per-position arrays (`self._P`, `self._h`, `self._T_f`, etc.,
`base.py:395-401`) to `num_cells` entries, with `self._dL = well_length /
num_cells` (`base.py:390`) as the per-step cell length — but index 0 is
the already-known inlet state, so the loop only actually marches
`num_cells - 1` steps. The well's true marched length is
`well_length * (num_cells - 1) / num_cells`, one cell short of the
declared `well_length`. At the default 100 cells that's a ~1% shortfall.

`tango`'s `NumericalWell` (`components/well/numerical.py`) carried
the identical shape forward at first — `cell_length = well_length /
num_cells`, but the march also took only `num_cells - 1` steps.
Confirmed (2026-09-15) as the dominant source of the scheme's slow
pressure-convergence behavior at lower cell counts, bigger than the
marching method's own truncation error — instrumented directly by
checking marched length against declared `well_length` across a range of
`num_cells` values.

**Fixed in `tango` only, left as-is in legacy `src/tango`** (a
deliberate physics divergence, same treatment as the isentropic-vs-
isothermal pump-work difference elsewhere in this file — old-vs-new
parity tolerances already account for it): `NumericalWell` now marches
`num_cells` cells bounded by `num_cells + 1` nodes (node 0 = inlet, node
`num_cells` = outlet), each cell marched exactly once, so
`cell_length = well_length / num_cells` correctly spans the well end to
end. The resulting array-length change (`num_cells + 1`, not
`num_cells`) was flowed through every downstream consumer (state/history
docstrings, `test_injection_well_spatial_history_shape`, the serde
round-trip test, and `demo_hydro_sf_electric.py`'s depth-axis plotting).
Golden snapshots and economic-parity goldens regenerated to match.
