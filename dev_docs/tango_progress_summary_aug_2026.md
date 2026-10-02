# tango: Progress Summary & Forward Plan — August 2026

*Prepared 2026-08-01, updated 2026-08-14. Managerial-level summary — for
engineering detail, see `dev_docs/tango_tasks.md` (working task tracker)
and `dev_docs/TANGO_vision_and_roadmap/README.md` (full technical roadmap). Continues
from `dev_docs/tango_progress_summary_july_2026.md`.*

## Old system is not actually solving AGS — and proof tango doesn't have this bug

While checking `tango`'s results for one class of geothermal system
(AGS — a sealed, closed-loop design with no reservoir) against the legacy
system's numbers, we found that the **legacy system silently stops
simulating change over time** for this design. It should model 25 years of
gradual wellbore cooling; instead, after the first year it just repeats
that same single result for every remaining year, with no error or warning
of any kind. Every downstream number computed from a multi-year AGS run in
the old system today — cooling trend, heat delivered over time — is
therefore not real.

This kind of bug is exactly the hard-to-catch kind: the output looks
completely normal (a single year of realistic-looking numbers), it just
never updates after that. Nothing about running it looks broken. It only
surfaced because `tango`'s numbers *did* show the expected year-by-year
change, which made the legacy system's flat, unchanging output stand out
by comparison.

**tango does not have this problem** — its AGS model already computes the
wellbore cooling correctly, which is exactly how we caught the legacy system's
error in the first place. There's also a structural reason to trust that
this wasn't luck: `tango` has a built-in guardrail (`LockedState`) that
requires every value which is supposed to be recomputed each year to actually
get recomputed — if a calculation were ever silently skipped the way it was
in the legacy system, `tango` would raise an error immediately instead of
quietly reusing last year's number. That guardrail stayed silent throughout this
investigation, which is exactly the point — its silence is confirmation that a
fresh, real number really was computed for every single year. The legacy system
has no equivalent safeguard anywhere, which is a real part of why this kind of
bug could survive undetected for as long as it did.

Because the legacy system currently has no trustworthy year-by-year baseline
for AGS, we can't do the usual side-by-side numeric comparison. Every affected
file has been marked so no one accidentally trusts a bad number in the
meantime, and the decision on how to handle the legacy system's fix is queued in
`dev_docs/tango_tasks.md` for when there's time to make that call.

### Confirmed via debugger: AGS configs get routed to the no-op placeholder engine (2026-08-04)

To remove any remaining doubt, we stepped through an actual run of the
affected example in a debugger and watched the failure happen in real
time, one line at a time, rather than relying only on code inspection:

1. The system-selection logic reads the config's surface-unit type
   (`'native_flexible'`) and, specifically because this design has no
   reservoir, collapses that down to the generic `'native'` before
   deciding which internal engine to use.
2. That collapsed name gets used to pick the engine — and it picks the
   generic placeholder engine (which does nothing year-to-year) instead
   of the real one this design should get.
3. We watched the placeholder engine's "do nothing" step execute, in the
   debugger, exactly where the real yearly-update calculation should have
   run instead.
4. We then ran the same file end-to-end and printed its year-by-year
   result column directly: the first year gives a real, distinct number
   (320.88...), and every year after that repeats the exact same number
   (333.07...) verbatim, all the way through year 25 — the file-level
   proof matching what the debugger showed line-by-line.

This is now confirmed four independent ways: code inspection, a second
unrelated "validated" file showing the same signature, a live debugger
walkthrough of the exact failure, and the raw output data itself. There
is no remaining ambiguity about whether this bug is real.

**Decision made 2026-08-03**: we are not fixing this in the legacy
system. AGS/no-reservoir designs are treated as having no trustworthy
legacy baseline for comparison; `tango`'s own internal checks stand
in for that comparison instead. See `dev_docs/tango_tasks.md`'s "Open
items — tracked, not scheduled" section.

### Hardened the silent AGS failure into a loud one; root cause is a fake convergence check plus a frozen heat-loss clock (2026-08-04/05)

We changed the legacy system so this bug can no longer hide. Where it
used to just do nothing and move on, it now stops the run immediately
with a clear error the moment a multi-year AGS simulation tries to
advance past its first year. This isn't a fix for the underlying physics
gap — that decision from 2026-08-03 stands — it just means nobody can
accidentally trust a silently-wrong number from this class of config
again. One real consequence: the web app's own live AGS (water) config
is affected by this same bug and now fails loudly too, instead of quietly
returning numbers that were never real. The two automated tests that
only existed to check this exact broken behavior were removed, since
keeping them around no longer serves a purpose — the legacy system isn't
being fixed for this case, so there's nothing left for those tests to
guard.

While hardening this, we also pinned down *exactly* why it happens, in
more precise terms than before. There are two separate reasons the
legacy system never advances time here, either one enough by itself:

1. The part of the code that's supposed to check "has this year's
   calculation settled down yet?" for this design always just says "yes,
   immediately" — without ever actually checking anything. Since this
   design's simulated wells/surface form a closed loop (each one feeds
   the next, in a circle), that means the whole loop only ever gets
   solved once per year, with no chance to settle. What looks like a
   changing number for the first several years is actually just that
   one-pass loop settling into a stable operating point on its own — the
   same way repeatedly restarting a calculation from its own last answer
   converges — not real years passing.
2. Separately, and just as important: the piece of physics that's
   supposed to track how much the surrounding rock has cooled from years
   of continuous heat extraction never gets told a year has passed. We
   confirmed this directly by temporarily re-enabling the broken
   behavior on a local, throwaway copy, instrumenting it, and watching
   the internal "how much time has passed" value: across all 20 years of
   a real run, for every one of the three wells involved, it never once
   changed. It's fixed forever at "one year's worth of extraction,"
   which is also why, once the loop settles into its stable operating
   point (point 1, above), the output just goes flat — not because 19
   more years of gradual cooling happened and then leveled off, but
   because those 19 years were never simulated in the first place.

**tango avoids this for a more specific reason than "it's built
differently."** It still tracks the same kind of "how much time has
passed" value the legacy system does — that idea wasn't removed. What's
different is that tango has no separate, easy-to-forget step for
advancing it. The value gets updated automatically, every time, as an
unavoidable part of the same calculation that uses it — and a generic,
built-in safeguard (not something anyone had to remember to apply to
this specific value) makes sure that if a single year's calculation
needs several internal attempts to settle, only the final, correct
attempt's update actually sticks. There's no way to end up in the
legacy system's situation, where one specific well's "time passed"
tracking was simply never wired up to anything that would advance it.

## Fixed a wrong reservoir initial-pressure formula in tango (found while chasing a small numeric mismatch)

We'd been tracking a small, persistent disagreement between old tango and
tango on one of our core comparison files — small enough to be
"close enough" for most purposes, but we wanted to understand exactly
why it existed rather than just tolerate it.

The cause: one of tango's startup values — an initial guess used
only before a component has been solved for the first time — was
computed with the wrong formula. It borrowed a formula meant for a
different purpose (a safety-ceiling check) instead of the one that
actually represents the reservoir's true starting condition. The two
formulas give noticeably different numbers for this file (about a 12%
difference), and because that startup guess only matters for a single
instant before real data takes over, the mistake was practically
invisible — except that it left behind a tiny seed of a discrepancy
that compounded over time. This is a genuine tango defect, not
something inherited from the legacy system. **Fixed and verified**: the
reservoir now computes its true initial pressure the same way old tango
does, and the two systems agree to sub-microkelvin precision once given
the same inputs.

What's left after this fix is a much smaller, well-understood residual,
concentrated at the steepest part of one physics curve both systems
implement identically — the kind of floating-point-level difference
that's inherent to comparing two independently-written codebases, not a
discoverable bug. See `dev_docs/TANGO_vision_and_roadmap/README.md` for the full
technical detail.

**A related point worth recording on its own merits.** Separately, we
confirmed something about the *old* system that's worth calling a bug in
its own right: old tango's convergence loop can, in principle, declare
"done" and use a cumulative number computed from a stale, one-step-behind
value rather than the fully up-to-date one from that same pass.
tango's design rules this out categorically — every value used in
any calculation always comes from the same, fully up-to-date pass, by
construction. See `dev_docs/bugs-fixed-in-tango.md`.

## Economic model and multi-objective optimizer (MOO) (2026-08-07, extended 2026-08-12)

We can now compute a real, defensible levelized cost of energy (LCOE) in
tango — not a placeholder — and feed it into a real multi-objective
optimizer that maps out the full range of cost-vs-output tradeoffs across
many designs at once, rather than only running one scenario at a time by
hand. Built on the same underlying search algorithm family as our legacy
optimizer, but not a like-for-like port — several real gaps and one real
bug turned up along the way, covered below.

**What it can do.**

- Searches over any number of tunable inputs at once — three for our
  double-flash example today (flow rate, injection pressure, and the
  surface plant's minimum required inlet pressure), up from two
  originally, with no ceiling on adding more.
- **Parallelization and HPC runs — verified, not just designed for.**
  Scales across every core on a single machine the same way the legacy
  optimizer does, but now also runs as a real unattended job on Euler:
  submit it, and it automatically sizes its own worker count to whatever
  CPU allocation the cluster actually granted that job, no hand-editing
  required. Tested end-to-end against a real (simulated) cluster
  submission, not just locally. The legacy optimizer has no equivalent
  cluster job wired up anywhere in this codebase today.

**Features that make it easier to use and more robust.**

- Saves its progress after every single generation, not just at the end
  — if a long unattended run gets killed or crashes partway (a real risk
  on a shared cluster with time limits), whatever it found up to that
  point is already safely on disk, not lost.
- Can pick up and warm-start from a previous run's results instead of
  always starting from scratch — useful for resuming or extending a run
  that was cut short.
- Every design on the full tradeoff set is saved as its own ready-to-run
  file, not just numbers in a log — any one of them can be reloaded and
  re-run individually, and the choice of "which one do we actually
  build" is left to a person looking at the real tradeoff. The legacy
  optimizer computes the same kind of full tradeoff set internally, but
  then collapses it down to a single "recommended" design via a scoring
  formula, discarding data that a human could use to downselect a best
  design.
- Every setting behind a given run is tracked in a version-controlled,
  repeatable pipeline — the same one already used for our large sweep
  runs elsewhere in this codebase — so a months-old result can be
  reproduced exactly. The legacy optimizer has no equivalent pipeline
  around it today.
- **Distinguishes "this design doesn't work" from "our own code is
  broken."** The legacy optimizer treats any failure at all — for any
  reason whatsoever — the same way: logged as "failed," and the search
  moves on. Fine when the failure is a genuine physical one (e.g. a
  candidate design would damage the reservoir); dangerous when it's
  actually a bug in the setup code, since a long unattended search could
  spend hours quietly recording every design as "failed" without ever
  surfacing that something upstream is broken. This optimizer only treats
  three specific, known physical failure modes that way — anything else
  stops the run immediately and loudly instead of getting absorbed.

**Design that makes it harder to misuse.** Both the legacy optimizer's tunable
inputs *and* its user-defined limits are wired up by feeding a complicated,
thinly documented, arcane string of Python code, built from a translated
parameter name, straight into Python's own `eval` — extending it to a new input,
measured outcome, or limit means trusting a piece of free-form, code-executing
text at runtime. This optimizer's equivalent is a small, fixed-shape function
for each one instead — "given the current settings, change exactly this one
thing" or "given a finished run, read exactly this one number" — composable and
extensible without ever executing arbitrary code, and without needing to touch
the search engine itself to add a new one.

**Cost model verified against the old system, not just self-consistent.**
Three of the five cost categories (permitting, exploration, surface
piping) match the old system's numbers *exactly, to the dollar* — strong
confirmation the formulas were ported correctly, not just plausibly. The
other two (well cost, power-plant equipment cost) don't match as tightly,
and we tracked down exactly why: the old system's own reference file has
a data-entry mistake (a well-length value copy-pasted from the wrong
well) that quietly changes its own cost calculation, and a separate,
already-known minor timing difference between the two systems' physics
amplifies through the power-plant formulas. Neither is a bug in the new
cost model — both are explained, documented, and accounted for with
appropriately-sized tolerances in a new automated test that will catch
any future regression.

**A related point worth recording on its own merits.** While tracing one
of the cost formulas, we found that the old system's own well-pump and
turbine cost calculations quietly rely on a sign convention (which
direction "positive" points for a given piece of equipment) that isn't a
fixed physical rule — it depends on which way a particular network happens
to be wired internally. tango's plant model wires things the opposite
way for pumps, which would have silently zeroed out or corrupted those
costs if we'd copied the old formulas literally. We caught this by testing
against real numbers rather than assuming the old formulas would transfer
as-is, and used a more robust approach (based on the size of the value,
not its sign) that gives the identical answer for the old system and the
correct answer for ours.

## Also found: the MOOSE-coupled examples can't currently be run by anyone but their original author

Separately, while checking whether any other simulation approach shared the
AGS problem above, we found that every example using the MOOSE external solver
(roughly 55 configurations) has hardcoded file paths pointing to one specific
person's personal computer — Morteza. At least one of the physics input files
these configurations need doesn't appear to be saved anywhere in our repository
at all. No documentation of how our code talks to MOOSE was left behind, so
getting this running again will mean reverse-engineering it from scratch unless
he's able to help.

I've reached out to Morteza by email and Slack to ask for help getting this
running and for any documentation he might have. If he doesn't respond, we
should plan on treating this as a rebuild rather than a quick fix.

*How our own code is supposed to connect to MOOSE* is effectively a black box
today: no setup instructions, no internal documentation, hardcoded to a machine
we no longer have access to, and (per an earlier repo audit) some of the
required input data may be missing entirely.

## Built out the full injection-safety control system in tango (2026-08-11–13)

A geothermal reservoir can be damaged by injecting fluid into it too
aggressively, in two independent ways: pushing it in at too high a
pressure, or pumping too much fluid into it too fast. tango now has a
complete, tested system for controlling this — five distinct modes, all
implemented and verified, where before there was only the simplest one.

The two check-only modes now genuinely check. The plainest mode
(fixed pressure, fixed flow rate, no safety check at all) already worked.
We built its safety-checking twin: same fixed values, but now it actively
compares the result against both danger thresholds every time step and
stops the run immediately if either is crossed, rather than continuing on
with a result that may have damaged the reservoir. While building this, we
found and fixed a genuine bug in the *old* system's own threshold formula:
one of its two safety-limit calculations quietly used a well's full width
where the underlying physics equation calls for its half-width (radius),
which skews the computed limit — confirmed by the fact that the old
system's own formula labels the value "radius" while the code beside it
plugs in the diameter instead. tango's version uses the correct
value. Full writeup: `dev_docs/bugs-fixed-in-tango.md`.

**Two new "auto-pilot" modes remove the guesswork entirely.** Instead of a
person picking a pressure or flow rate and hoping it's safe, tango can
now automatically search for the exact value that lands right at the
safety limit — as close to the reservoir's real capacity as possible
without exceeding it, with no manual tuning required. One mode does this
for pressure (flow rate stays fixed), the other for flow rate (pressure
stays fixed), each converging to the right answer in just a handful of
steps.

**The fourth, most advanced mode does both at once — and is the one we
could actually verify head-to-head against the old system's numbers,**
because it's the only one of the four with a real equivalent there.
Matched old tango to within 0.026% — a tiny, expected floating-point-level
difference, not a discrepancy. We also deliberately went looking for where
that agreement might break down, and found something worth recording
honestly rather than glossing over: push the flow rate closer to a
separately-known "edge" where the underlying physics model itself starts
becoming numerically delicate (already documented, unrelated to this
work), and the two systems' agreement visibly loosens — from 0.026% to
about 3.3%. We confirmed this isn't a new mistake in either system (the
underlying formulas still match exactly); it's the expected consequence of
being near that edge, where tiny, ordinarily-invisible numerical
differences get magnified. Documented plainly so nobody mistakes it for a
regression later.

All five modes now have automated tests confirming they behave correctly,
and the full existing test suite still passes — nothing else broke.

**Deliberately deferred, not forgotten:** the most advanced mode's
"official" design goal — if the target flow rate makes no pressure
achievable, back off the flow rate until one is — is more sophisticated
than what the old system actually does (which is simpler: drive both
values toward their limits and just apply a flat cap). We built the
simpler, verifiable version first on purpose, to get the real numeric
comparison above; the fuller version remains a tracked backlog item, not
abandoned.

## Fixed how the production-well pump reaches its target pressure — and tango's corrected pump power now runs ~53% above the legacy system's own number, for a real, understood reason (2026-08-14)

In `tango`, every one of our production wells that needs a surface
pump (to guarantee a minimum delivery pressure at the plant) had been
computing that pump's required boost with a shortcut: run the well's own
friction/heat-loss calculation first, using the *un-boosted* pressure the
whole way, then assume that whatever shortfall showed up at the far end
(the gap between that natural result and the actual target) could simply
be added, unchanged, right at the pump's own discharge. That shortcut
quietly assumes the rest of the pipe between the pump and the surface
doesn't care how hard the pump pushes — but boosting the pump's discharge
pressure changes the fluid's density the whole way up that pipe, which
changes the friction loss too, especially for a fluid like supercritical
CO₂ whose density is highly sensitive to pressure near its critical
point. The old shortcut ignored that entirely.

**We replaced the shortcut with a real iterative solve.** Instead of
computing the boost once and hoping it lands close enough, `tango`
now guesses a candidate boost, re-runs the well's own physics from that
boosted starting point, checks where it actually lands relative to the
target, and refines the guess — repeating with a genuine convergence
check (not a fixed number of tries) until it lands within a tight,
sub-1-Pascal tolerance. This is a small, well-understood piece of applied
math (the secant method) doing real work here, not decoration.

**While rebuilding this properly, we also fixed a separate, larger
assumption — one the legacy system carries too, not just an internal
`tango` shortcut.** The pump's own energy cost had been calculated
assuming the compression happens at *constant temperature* —
mathematically convenient, but not what a real pump does. A real pump
does its work fast enough that the fluid has no time to exchange heat
with its surroundings; the textbook-correct assumption is a compression
that conserves entropy (with a pump-efficiency penalty applied on top),
not one that holds temperature fixed. We confirmed the legacy system's
own downhole-pump code makes the exact same constant-temperature
assumption explicitly (it raises the fluid's pressure while literally
passing in the *same* temperature value it had beforehand), so this
isn't tango fixing its own mistake — it's tango moving past a
simplification the legacy system has always carried. We swapped in the
correct (entropy-conserving) model.

**What actually drives the gap between the two models is temperature,
not pressure.** It's tempting to assume the constant-temperature
shortcut breaks down because this fluid is at high pressure, but we
checked this directly rather than assuming it, and that's not it: at
this well's real operating temperature (~125°C), the two models
diverge by the same ~1.5x whether the absolute pressure is low or
matches the real well (a few MPa to ~7 MPa); held at the same pressures
but at room temperature instead, the gap nearly disappears (~1.07x).
The underlying thermodynamics (``dH|entropy − dH|temperature =
T·α·V·dP``, where α is how much the fluid expands per degree of
heating) says the gap should grow with temperature, and specifically
with how close that temperature runs to the fluid's own critical
point — which is also why this matters even more for a fluid like
supercritical CO₂ operating near its own critical point than it does
for this design.

**The consequence is bigger than the legacy system's own number, and we
traced it against the legacy system directly before accepting it — not
just against tango's own prior output.** For one of our two
benchmark designs, we pulled the legacy system's actual computed pump
power from a live run and compared it to tango's corrected value, at
the same final timestep of the same 20-year run: 187,161 W (legacy) vs.
285,598 W (tango) — **~53% higher**, not merely a change relative to
what tango itself used to output. We isolated which of the two
changes above actually causes it (the temperature assumption, not the
friction-recalculation piece, which contributes under 0.1% by comparison
for this design), and independently verified the underlying physics: at
representative conditions from this well, the entropy-conserving
enthalpy rise is genuinely **1.5x** the constant-temperature one — a
first-principles thermodynamic fact about compressing this fluid, not an
artifact of the code change. This pushed our overall cost figure (LCOE)
for that design up by a few percent versus the old, less correct number
— a real, understood, and now-documented shift against the legacy
system, not unexplained drift. Every test that compares our numbers
against the legacy system's own pump model was updated with the actual
traced numbers recorded inline, specifically so this doesn't get
mistaken for a regression later.

All existing tests pass with the corrected model in place.

## Gave the AGS closed loop a real circulation pump, and caught it the way a well-designed system should: by finding the actual physical edge case, not by guessing (2026-08-17/18)

Optimizing `tango`'s AGS direct-heat model (well depth, loop length,
loop diameter, well diameter, injection pressure, mass flow rate — a real
NSGA2 search, not a hand-picked design point) turned up something worth
paying attention to on its own terms: every one of 45 pareto-optimal
designs converged to (or right against) the same tight corner of the
search space — shortest loop, smallest diameter, highest flow, deepest
well allowed. That's exactly the kind of result that's easy to wave away
as "the optimizer likes extreme values," so we didn't wave it away —
we opened up the actual pressure profile at that converged design instead
of guessing. The production wellhead was delivering only 29,493 Pa, and
the working fluid's own saturation pressure at that delivered temperature
was 29,472 Pa — a margin of 21.6 Pa, **0.07%**. The optimizer hadn't found
a shortcut; it had found the true edge of physical feasibility and parked
right on top of it, because nothing in the model gave it a reason to stop
sooner.

**What that traced back to:** this closed loop (injection well → horizontal
loop → production well → surface → back to injection) had no pump
anywhere in it — not downhole, not at the surface. It ran entirely on
thermosiphon effect (the buoyancy created by the density difference
between the cold descending leg and the hot ascending leg) minus friction,
with nothing mechanical to fall back on. That's a real, physically
meaningful gap, not a modeling nicety — and it's one `tango` is now
positioned to close cleanly precisely because of the architecture
decisions already in place: `GraphSurface`'s generic, YAML-driven node
graph meant adding a real circulation pump was a config change (one new
`Compressor` node) plus one small, principled extension to the surface
component's attribute-translation layer (a `pressure_ratio` spec, needed
by the heat exchanger now that it isn't the last node before the network
outlet) — not a rewrite. The pump was placed on the cold, post-heat-exchanger
leg deliberately: pumping fluid that's already near its flash point (like
the production wellhead here) risks cavitation, so real closed-loop
AGS-style systems put their surface circulation pump on the cold leg too.

**Checked whether this was a `tango` porting gap before calling it
one — it wasn't.** The legacy Triemli AGS config
(`applications/run_AGS_direct_heat_sweep/triemli_dh_base.yml`) has the
identical shape: a bare `Source → SimpleHeatExchanger → Sink` surface
plant, no pump. It sets a `production_well.eta_pump` value that looks
like a pump setting at a glance, but the legacy registry only reads that
field for a different, unused unit type — the field is dead config there,
confirmed directly against `src/tango/units/registry.py` and
`production_well.py`. `tango` isn't fixing something it broke; it's
improving on a gap the legacy system always had, using an architecture
that made the improvement cheap once the gap was actually found.

**Turned the finding into a standing rule, not a one-off patch.** Added a
new TANGO Commandment (`CONTRIBUTING.md`): every closed fluid loop needs
an explicit pump or compressor somewhere in it. Backed that with a real,
automatic check (`Workflow`'s construction now rejects any closed-loop
config with no pump anywhere, well-side or surface-side) rather than
leaving it as a documentation-only rule someone has to remember — the
exact category of mistake this whole investigation started from. Also
relaxed a check that was too narrowly scoped to electric topologies
(`GraphSurface` was rejecting any negative net electric power
unconditionally, which is correct when a turbine should always outproduce
its own parasitic pumps, but wrong for a pure direct-heat plant that has
no generator at all and *should* show negative net power once its own
circulation pump is accounted for) — now scoped to only fire when a real
generator is actually present. Full technical writeup, including the
exact numbers and code paths: `dev_docs/bugs-fixed-in-tango.md`.

## Built a surrogate-model-accelerated optimizer — 10x faster, but not yet trustworthy on its own (2026-08-19)

Running our real multi-objective optimizer end-to-end is slow, because
every candidate design it evaluates is a full physics simulation. We built
an alternative pipeline that instead runs a modest number of real
simulations up front, trains a fast statistical stand-in (a "surrogate")
to predict each design's outputs from its inputs, and runs the
computationally expensive search against that fast stand-in instead —
only falling back to the real simulation to validate whatever the search
comes up with at the end.

**The speed win is real and confirmed on a real cluster run, not just in
theory:** the full surrogate-based pipeline completed in about 29 minutes
versus roughly 5.3 hours for the equivalent real-simulation-only search —
close to 10x faster end to end, on a genuine 2000-design Euler run, not a
toy example. The part of the surrogate pipeline that had to do the most
work was actually still the "collect real training data" step, not the
search itself, which came almost for free once the surrogate was trained.

**One specific improvement worked exactly as intended: a separate check
that filters out designs the surrogate would have wrongly called valid.**
Before adding it, only about a quarter of the tradeoff designs the
surrogate-based search returned actually held up as real, physically valid
designs once checked against the real simulation. After adding it, 100% of
returned designs check out as genuinely valid — confirmed against real
simulation, not just self-reported by the surrogate.

**But the headline result isn't usable as-is yet, and we said so plainly
rather than reporting the encouraging numbers alone.** Once we re-checked
the returned tradeoff set using each design's real (not
surrogate-predicted) outputs, a set that looked like 41 distinct,
attractive tradeoff options collapsed down to just 3 genuinely different
designs — the rest were near-duplicates that only looked distinct because
of small, systematic errors in the surrogate's predictions. The 3 designs
that survived also only covered a narrow slice of the real tradeoff range
found by the slower, real-simulation-only search — an entire higher-cost,
higher-output region of the tradeoff curve was missing. Our working
explanation, not yet confirmed: the specific statistical model we used
first tends to produce predictions that are flat across small ranges of
input rather than smoothly varying, which can fool the search into
thinking it's found many distinct good designs within one of those flat
patches when it's really just found tiny, meaningless variations on one
design.

**Decision, made deliberately rather than pushing ahead:** paused here to
try a smoother statistical model first (see below for how that played
out), rather than accepting a result we already knew wasn't trustworthy.
Continued into September — see
`dev_docs/tango_progress_summary_sep_2026.md`.

## Where things stand

Unchanged from July's snapshot pending the decision above — see
`dev_docs/tango_progress_summary_july_2026.md`'s coverage table and
`dev_docs/tango_tasks.md` for current detail. AGS direct-heat remains
implemented and runs correctly in `tango` on its own terms (its own
smoke test and internal self-consistency checks pass); what's blocked is
specifically the *old-vs-new numeric comparison*, not `tango` itself.

## Immediate next steps

1. ~~Revisit the AGS old-tango bug and decide how to proceed~~ — decided
   2026-08-03: not fixing the legacy system for this. Closed.
   ~~Harden the silent failure into a loud one and confirm the exact
   mechanism~~ — done 2026-08-04/05 (see above).
2. Wait on Morteza's response regarding the MOOSE integration; if none
   comes, scope the reverse-engineering effort as its own task.
3. ~~Fix the reservoir startup-value bug and re-confirm~~ — done 2026-08-04:
   fixed and verified (see above).
4. ~~Build out the remaining injection-safety modes (auto-pilot pressure,
   auto-pilot flow rate, and the combined mode)~~ — done 2026-08-11–13, all
   five modes implemented and tested (see above). Remaining, not urgent:
   the combined mode's fuller "back off flow rate until a pressure is
   achievable" design, deliberately deferred — tracked in
   `dev_docs/tango_tasks.md`, no timeline set.
5. ~~Replace the production-well pump's one-shot pressure correction with
   a real iterative solve, and fix its constant-temperature assumption~~ —
   done 2026-08-14 (see above).

Everything else queued from July's plan is unaffected and can continue in
parallel.
