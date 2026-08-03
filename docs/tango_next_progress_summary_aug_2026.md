# tango_next: Progress Summary & Forward Plan — August 2026

*Prepared 2026-08-01. Managerial-level summary — for engineering detail, see
`docs/tango_next_tasks.md` (working task tracker) and
`docs/TANGO_vision_and_roadmap.md` (full technical roadmap). Continues from
`docs/tango_next_progress_summary_july_2026.md`.*

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

1. Revisit the AGS old-tango bug (`docs/tango_next_tasks.md` §4) and decide
   how to proceed before resuming any further AGS parity work.
2. Wait on Morteza's response regarding the MOOSE integration; if none
   comes, scope the reverse-engineering effort as its own task.

Everything else queued from July's plan is unaffected and can continue in
parallel.
