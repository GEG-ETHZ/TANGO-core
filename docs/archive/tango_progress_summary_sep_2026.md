# tango: Progress Summary & Forward Plan — September 2026

*Prepared 2026-09-16. Covers September 1–16 only — a partial month, not a
full period like the July/August summaries. Managerial-level summary — for
engineering detail, see `docs/tango_tasks.md` (working task tracker)
and `docs/TANGO_vision_and_roadmap/README.md` (full technical roadmap). Continues
from `docs/tango_progress_summary_aug_2026.md`.*

## Resolved the surrogate optimizer's accuracy problem: a smoother statistical model, not more data, was the fix (2026-08-31–09-01)

August's surrogate-accelerated optimizer (10x faster than a full
real-simulation search, but untrustworthy at the edges of its predicted
tradeoff curve — see last month's summary) got picked back up here, in
the order already agreed on: try a smoother statistical model before
reaching for anything more complicated.

**First try — Gaussian Process Regression — ran fast and looked accurate
by its own internal metrics, but failed the same real-world test as
before.** Cross-validation looked excellent (99.85%/99.54% variance
explained for cost/power), and the whole pipeline ran about 5.3x faster
than a full real-simulation search. But once its predicted tradeoff
designs were checked against real simulation, its cost predictions were
off by as much as 35% in exactly the region the optimizer favored — only
3 of 43 predicted "good" designs survived that check, almost exactly
the same failure mode as August's first attempt.

**Second try — a small neural network — fixed it.** Trained in about 15
seconds (versus the Gaussian Process's ~36 minutes) on a real 5000-design
cluster run, and held up far better exactly where it matters: at the edge
of the tradeoff curve, cost predictions were typically off by only 1.4%
(worst case 4.3%), versus the Gaussian Process's typical 9.8% (worst case
35%). 12 of 45 predicted-good designs survived the real-simulation check,
up from 3 — still not everything the search claimed, but four times
better, and enough to make the tool's output usable rather than
misleading. The small neural network is now the default; the Gaussian
Process remains available as a reference option, documented as such
rather than presented as the default choice.

## Found and fixed a real physics bug in AGS while adding a production-temperature requirement to the optimizer (2026-09-04)

Extended the AGS (closed-loop) optimizer with a real requirement that
matches how we already judge these designs elsewhere: the fluid coming
out of the production well has to reach at least 105°C to be useful,
not just physically survive the loop. Running that new requirement on a
real cluster search initially found **zero valid designs at all** — an
immediate signal something was wrong, since single hand-picked designs
had cleared that bar before.

Tracing why turned up a genuine, previously unnoticed bug in how a
well's own rock temperature is calculated whenever that well starts
below the surface partway down another well segment (the horizontal AGS
loop is exactly this case — it starts 5,500 m down). The calculation
had been using the well's own flow-path length as if it were an absolute
depth below the surface, instead of adding the two together — for a
wellhead sitting deep underground, this silently modeled that entire
segment as if it started at the surface. **The AGS loop was being modeled
as a heat sink losing energy toward ~11°C outside air, instead of a heat
source gaining energy from ~200°C hot rock at its actual depth** — exactly
backwards, and exactly why the new temperature requirement found nothing
valid. Fixed: the same best-case design that reached 92.7°C before the
fix now correctly reaches 136.6°C. A smaller version of the same bug was
quietly present in every stacked-pump-well configuration too, with a much
smaller effect (~1% shift in a couple of cost/output numbers) — fixed
there as well, and all affected regression tests were updated with the
corrected reference numbers.

**Separately, once the physics bug was fixed, the search still found
nothing valid — a second, unrelated bug in how the optimizer scores
failed designs.** A design that failed to run at all (crashed) was being
scored as if it violated the new temperature requirement by only a tiny
amount — smaller, in fact, than the penalty for a design that ran
successfully but simply wasn't warm enough. The optimizer was
mathematically better off crashing than trying. Fixed so a crashed design
is always scored as strictly worse than any design that actually ran,
regardless of how the specific requirement is scaled. After both fixes,
the optimizer's search reliably moves toward real, physically simulated
designs instead of stalling. Also measured and widened the search's depth
range to give the requirement room to be satisfied by more than a single
knife-edge point, so there's an actual tradeoff curve to search, not one
exact corner.

## Fixed a well-discretization shortfall and made resolution scale with well length (2026-09-15/16)

Found that every numerically-marched well was consistently modeling
slightly less than its own declared length — about 1% short at the
default resolution — because of an off-by-one in how the march was set
up (it took one fewer step than the number of segments it was dividing
the well into). This was the dominant source of slow-converging accuracy
at lower resolutions, bigger than the marching method's own inherent
approximation error. Fixed, with every downstream consumer (history
arrays, tests, plotting) updated to match.

Separately, every well configuration had been using the same fixed
number of calculation segments (100) regardless of how long the well
actually is — over-resolving short wells and under-resolving long ones.
Wells now automatically pick a segment count that keeps the resolution
per segment consistent (based on an existing convergence study), while
still allowing a manual override for cases that need one (e.g. a
resolution-sensitivity sweep).

## Performance: found and fixed the single biggest runtime hotspot (2026-09-15/16)

Profiling a representative example showed a single fluid-property
calculation call accounting for roughly a third of total runtime.
Switching that calculation (and, separately, the equivalent one inside
the surface-plant network solver) to a pre-tabulated, interpolation-based
mode of the same underlying fluid-property library cuts that hotspot's
own time roughly in half, and total run time by up to ~18% on the
fluid-property side alone and roughly 2x on runs that spend significant
time in the surface-plant solver (measured: 1.33s→0.65s and
2.64s→1.20s on two representative examples, averaged over 5 runs each).
Accuracy impact is negligible — confirmed against the full existing test
suite, with only a small, deliberately-widened numerical tolerance needed
to absorb harmless run-to-run jitter the tabulation method introduces.

## Investigated what it would take to open-source the wellbore model (2026-09-16)

Started scoping a request to release the wellbore simulation code as a
standalone open-source package (parallel to how we've previously released
other simulation tools). Found that the wellbore code is not actually
separable from the broader shared simulation foundation it's built on —
it depends on 9 of that foundation's 14 modules (fluid properties, state
management, numerical solvers, physics correlations), and that same
foundation is shared by the surface-plant and reservoir code too. Since
there's now interest in open-sourcing all three, not just the wellbore
model, the real decision is whether to open-source the shared foundation
itself as its own package (avoiding a permanent, drifting fork of the
same code) or to hold off. Scoped and handed to Chad's manager as a
decision point; not yet resolved. See `docs/tango_tasks.md` for
the underlying dependency audit if needed.

## Smaller items worth noting

- **Optimizer usability**: every optimizer's output file now labels each
  column as a decision variable, an active search objective, or a
  reported-but-not-searched-on value (e.g. cost breakdown), and every
  plot axis now shows a proper labeled unit instead of a raw internal
  name.
- **A related scoring bug fix**: a CoolProp fluid-property failure inside
  the surface-plant solver could previously crash an entire optimization
  run outright; it's now caught and treated as one failed design, the
  same way other physically-infeasible designs already are.
- Removed lingering references to the codebase this rewrite superseded
  from code and docs, and added two new contribution guidelines
  (descriptive variable names; a documented mapping from past bugs to
  the design principles meant to prevent their recurrence).
- Backlogged a longer-term idea: making economic (cost) calculations a
  responsibility of each component (well, surface, reservoir) rather than
  one large, centralized economic component — flagged for later, not
  started, and relevant to the open-source scoping above.

## Where things stand

No change to the heat/power coverage table from August — see
`docs/tango_progress_summary_aug_2026.md`. This period's work was
concentrated on making existing capabilities (the AGS optimizer, the
surrogate-accelerated search, well physics accuracy, runtime performance)
more correct and more trustworthy, not on adding new system-type coverage.

## Immediate next steps

1. Decide, with Chad's manager, whether to open-source the shared
   simulation foundation alongside the wellbore/surface/reservoir models,
   or hold the release — see the open-source scoping section above.
2. Continue building out the AGS optimizer now that its production-
   temperature constraint is physically meaningful (bug fixed) and
   correctly scored (scoring bug fixed) — a real, usable pareto front is
   now achievable where before the search found nothing valid at all.
3. Everything queued from August's plan not superseded above (the MOOSE
   integration follow-up, the deferred "back off flow rate" injection
   mode, etc.) is unaffected and continues in parallel — see
   `docs/tango_tasks.md`.
