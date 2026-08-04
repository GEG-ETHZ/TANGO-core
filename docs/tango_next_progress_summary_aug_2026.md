# tango_next: Progress Summary & Forward Plan — August 2026

*Prepared 2026-08-01, updated 2026-08-04. Managerial-level summary — for
engineering detail, see `docs/tango_next_tasks.md` (working task tracker)
and `docs/TANGO_vision_and_roadmap.md` (full technical roadmap). Continues
from `docs/tango_next_progress_summary_july_2026.md`.*

## A real bug found in the old system — and proof tango_next doesn't have it

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

**tango_next does not have this problem** — its AGS model already computes
the wellbore cooling correctly, which is exactly how we caught the legacy
system's error in the first place. Confirmed thoroughly before writing this
up (traced the exact cause, reproduced it on an unrelated file that had
already been "validated," and checked it live in a running simulation) —
this isn't a guess.

There's also a structural reason to trust that this wasn't luck: `tango_next`
has a built-in guardrail (`LockedState`) that requires every value which is
supposed to be recomputed each year to actually get recomputed — if a
calculation were ever silently skipped the way it was in the legacy system,
`tango_next` would raise an error immediately instead of quietly reusing
last year's number. That guardrail stayed silent throughout this
investigation, which is exactly the point — its silence is confirmation
that a fresh, real number really was computed for every single year. The
legacy system has no equivalent safeguard anywhere, which is a real part of
why this kind of bug could survive undetected for as long as it did.

Because the legacy system currently has no trustworthy year-by-year
baseline for this design type, we can't do the usual side-by-side numeric
comparison for it right now. Every affected file has been marked so no one
accidentally trusts a bad number in the meantime, and the decision on how
to handle the legacy system's fix is queued in `docs/tango_next_tasks.md`
for when there's time to make that call.

### Further confirmed 2026-08-04 — watched it happen live, step by step

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

## Found and fixed a real tango_next bug while investigating a small numeric mismatch

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
construction. See `docs/bugs-fixed.md`.

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
2. Wait on Morteza's response regarding the MOOSE integration; if none
   comes, scope the reverse-engineering effort as its own task.
3. ~~Fix the reservoir startup-value bug and re-confirm~~ — done 2026-08-04:
   fixed and verified (see above).

Everything else queued from July's plan is unaffected and can continue in
parallel.
