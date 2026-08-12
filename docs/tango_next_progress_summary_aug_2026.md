# tango_next: Progress Summary & Forward Plan — August 2026

*Prepared 2026-08-01, updated 2026-08-13. Managerial-level summary — for
engineering detail, see `docs/tango_next_tasks.md` (working task tracker)
and `docs/TANGO_vision_and_roadmap.md` (full technical roadmap). Continues
from `docs/tango_next_progress_summary_july_2026.md`.*

## Old system is not actually solving AGS — and proof tango_next doesn't have this bug

While checking `tango_next`'s results for one class of geothermal system
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
surfaced because `tango_next`'s numbers *did* show the expected year-by-year
change, which made the legacy system's flat, unchanging output stand out
by comparison.

**tango_next does not have this problem** — its AGS model already computes the
wellbore cooling correctly, which is exactly how we caught the legacy system's
error in the first place. There's also a structural reason to trust that
this wasn't luck: `tango_next` has a built-in guardrail (`LockedState`) that
requires every value which is supposed to be recomputed each year to actually
get recomputed — if a calculation were ever silently skipped the way it was
in the legacy system, `tango_next` would raise an error immediately instead of
quietly reusing last year's number. That guardrail stayed silent throughout this
investigation, which is exactly the point — its silence is confirmation that a
fresh, real number really was computed for every single year. The legacy system
has no equivalent safeguard anywhere, which is a real part of why this kind of
bug could survive undetected for as long as it did.

Because the legacy system currently has no trustworthy year-by-year baseline
for AGS, we can't do the usual side-by-side numeric comparison. Every affected
file has been marked so no one accidentally trusts a bad number in the
meantime, and the decision on how to handle the legacy system's fix is queued in
`docs/tango_next_tasks.md` for when there's time to make that call.

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
legacy baseline for comparison; `tango_next`'s own internal checks stand
in for that comparison instead. See `docs/tango_next_tasks.md`'s "Open
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

**tango_next avoids this for a more specific reason than "it's built
differently."** It still tracks the same kind of "how much time has
passed" value the legacy system does — that idea wasn't removed. What's
different is that tango_next has no separate, easy-to-forget step for
advancing it. The value gets updated automatically, every time, as an
unavoidable part of the same calculation that uses it — and a generic,
built-in safeguard (not something anyone had to remember to apply to
this specific value) makes sure that if a single year's calculation
needs several internal attempts to settle, only the final, correct
attempt's update actually sticks. There's no way to end up in the
legacy system's situation, where one specific well's "time passed"
tracking was simply never wired up to anything that would advance it.

## Fixed a wrong reservoir initial-pressure formula in tango_next (found while chasing a small numeric mismatch)

We'd been tracking a small, persistent disagreement between old tango and
tango_next on one of our core comparison files — small enough to be
"close enough" for most purposes, but we wanted to understand exactly
why it existed rather than just tolerate it.

The cause: one of tango_next's startup values — an initial guess used
only before a component has been solved for the first time — was
computed with the wrong formula. It borrowed a formula meant for a
different purpose (a safety-ceiling check) instead of the one that
actually represents the reservoir's true starting condition. The two
formulas give noticeably different numbers for this file (about a 12%
difference), and because that startup guess only matters for a single
instant before real data takes over, the mistake was practically
invisible — except that it left behind a tiny seed of a discrepancy
that compounded over time. This is a genuine tango_next defect, not
something inherited from the legacy system. **Fixed and verified**: the
reservoir now computes its true initial pressure the same way old tango
does, and the two systems agree to sub-microkelvin precision once given
the same inputs.

What's left after this fix is a much smaller, well-understood residual,
concentrated at the steepest part of one physics curve both systems
implement identically — the kind of floating-point-level difference
that's inherent to comparing two independently-written codebases, not a
discoverable bug. See `docs/TANGO_vision_and_roadmap.md` for the full
technical detail.

**A related point worth recording on its own merits.** Separately, we
confirmed something about the *old* system that's worth calling a bug in
its own right: old tango's convergence loop can, in principle, declare
"done" and use a cumulative number computed from a stale, one-step-behind
value rather than the fully up-to-date one from that same pass.
tango_next's design rules this out categorically — every value used in
any calculation always comes from the same, fully up-to-date pass, by
construction. See `docs/bugs-fixed-in-tango-next.md`.

## Built a real cost model in tango_next, then a working optimizer on top of it (2026-08-07)

We can now compute a real, defensible levelized cost of energy (LCOE) in
tango_next — not a placeholder — and use it to automatically search for
the best-performing design, rather than only running one scenario at a
time by hand.

This started as a request to build an optimizer that tunes a plant's flow
rate and injection pressure to get the best combination of low cost and
high energy output. Partway in, we hit a real gap: tango_next had no cost
model at all — every existing sweep tool already showed "LCOE: null"
because nothing computed it. Rather than fake the number, we built the
real thing: ported the actual well-cost, permitting, exploration, pipe,
and power-plant cost formulas from the old system into tango_next, wired
up to run automatically once a simulation finishes.

**Verified against the old system, not just self-consistent.** Three of
the five cost categories (permitting, exploration, surface piping) match
the old system's numbers *exactly, to the dollar* — strong confirmation the
formulas were ported correctly, not just plausibly. The other two (well
cost, power-plant equipment cost) don't match as tightly, and we tracked
down exactly why: the old system's own reference file has a data-entry
mistake (a well-length value copy-pasted from the wrong well) that quietly
changes its own cost calculation, and a separate, already-known minor
timing difference between the two systems' physics amplifies through the
power-plant formulas. Neither is a bug in the new cost model — both are
explained, documented, and accounted for with appropriately-sized
tolerances in a new automated test that will catch any future regression.

With a working cost number in hand, we built the optimizer on top of it: a
reusable search tool (using the same genetic-algorithm approach as our
legacy optimization code) that automatically tries different combinations
of flow rate and injection pressure, discards any combination that fails
to run rather than crashing the whole search, and returns the best
tradeoffs between cost and energy output as a ranked set of designs — each
one saved so it can be re-loaded and re-run individually. The example
script for our double-flash plant now runs this search end-to-end and
produces a chart showing the full tradeoff space at a glance.

**A related point worth recording on its own merits.** While tracing one
of the cost formulas, we found that the old system's own well-pump and
turbine cost calculations quietly rely on a sign convention (which
direction "positive" points for a given piece of equipment) that isn't a
fixed physical rule — it depends on which way a particular network happens
to be wired internally. tango_next's plant model wires things the opposite
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

## Built out the full injection-safety control system in tango_next (2026-08-11–13)

A geothermal reservoir can be damaged by injecting fluid into it too
aggressively, in two independent ways: pushing it in at too high a
pressure, or pumping too much fluid into it too fast. tango_next now has a
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
plugs in the diameter instead. tango_next's version uses the correct
value. Full writeup: `docs/bugs-fixed-in-tango-next.md`.

**Two new "auto-pilot" modes remove the guesswork entirely.** Instead of a
person picking a pressure or flow rate and hoping it's safe, tango_next can
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

## Where things stand

Unchanged from July's snapshot pending the decision above — see
`docs/tango_next_progress_summary_july_2026.md`'s coverage table and
`docs/tango_next_tasks.md` for current detail. AGS direct-heat remains
implemented and runs correctly in `tango_next` on its own terms (its own
smoke test and internal self-consistency checks pass); what's blocked is
specifically the *old-vs-new numeric comparison*, not `tango_next` itself.

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
   `docs/tango_next_tasks.md`, no timeline set.

Everything else queued from July's plan is unaffected and can continue in
parallel.
