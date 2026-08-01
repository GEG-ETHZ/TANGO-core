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

Because the legacy system currently has no trustworthy year-by-year
baseline for this design type, we can't do the usual side-by-side numeric
comparison for it right now. Every affected file has been marked so no one
accidentally trusts a bad number in the meantime, and the decision on how
to handle the legacy system's fix is queued in `docs/tango_next_tasks.md`
for when there's time to make that call.

## Where things stand

Unchanged from July's snapshot pending the decision above — see
`docs/tango_next_progress_summary_july_2026.md`'s coverage table and
`docs/tango_next_tasks.md` for current detail. AGS direct-heat remains
implemented and runs correctly in `tango_next` on its own terms (its own
smoke test and internal self-consistency checks pass); what's blocked is
specifically the *old-vs-new numeric comparison*, not `tango_next` itself.

## Immediate next step

Revisit the AGS old-tango bug (`docs/tango_next_tasks.md` §4) and decide how
to proceed before resuming any further AGS parity work. Everything else
queued from July's plan is unaffected and can continue in parallel.
