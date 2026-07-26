# tango_next: Progress Summary & Forward Plan

*Prepared 2026-07-24. Managerial-level summary — for engineering detail, see
`docs/tango_next_tasks.md` (working task tracker) and
`docs/TANGO_vision_and_roadmap.md` (full technical roadmap).*

## What this covers

`tango_next` is the in-progress rewrite of TANGO's simulation core. The old
implementation (`src/tango/`) remains the validated reference until the
rewrite is proven equivalent; both are maintained side by side during this
transition.

## Accomplished in the past 3 weeks

**Repo health.** Removed legacy packaging/build tooling and dead code,
consolidated license handling, and got CI running a real test subset
reliably. The codebase is materially easier to onboard into and less prone
to silent breakage.

**Correctness guarantees baked into the new architecture.** A recurring
theme this period: finding places where the old system allowed silent,
hard-to-detect bugs (a component quietly using a different value than the
rest of the system for something that should always match, like rock
thermal conductivity), and closing them structurally in `tango_next` rather
than patching around them. Shared physical parameters (rock properties,
surface temperature/pressure) are now enforced by the system's data model
to be identical everywhere they're used — misconfiguration is caught
immediately at setup time instead of producing quietly-wrong results
downstream. Configuration objects are now also locked against accidental
modification once a simulation is built, closing off an entire class of
bugs where results silently stop reflecting the configuration they were
supposedly run with.

**Validated regression testing infrastructure.** Added "golden snapshot"
regression coverage and automated old-vs-new comparison tests, so that
future changes to `tango_next` are automatically checked against both a
known-good baseline and the legacy implementation. This is what lets
development continue at pace without re-litigating correctness by hand
every time.

**AGS (closed-loop) system support.** Ported the AGS direct-heat use case
end-to-end into `tango_next`, including a working parameter-sweep example
demonstrating the new system can reproduce sweep-style analyses (varying a
design parameter across many runs) that were previously only possible in
the old codebase. This is the first fully modern, closed-loop system type
running in the new architecture.

**Documentation caught up to the code.** The technical roadmap and its
diagrams were reconciled with what's actually built, so the roadmap
reflects real state rather than stale planning.

## Where things stand

- `tango_next` can run: flexible single-flash plants (the original
  reference case) and AGS direct-heat systems, both validated against the
  old implementation.
- Still needed before AGS is "done": a power-generation counterpart (needs
  a new turbine/power-plant component that doesn't exist yet in
  `tango_next`), and a small number of edge-case validations.
- Economic modeling (cost/revenue calculations, LCOE/LCOH) has not yet been
  built into `tango_next` — this is a known, scoped gap, not an oversight.
- Optimization tooling (automated design-space search) is planned but not
  started.

## Plan for the next couple of months

1. **Finish AGS parity** — build the missing power-generation component,
   port the electric-generation sweep, and validate both heat and power
   variants against the old codebase.
2. **Broaden system coverage** — fill out the remaining combinations of
   geothermal system type (EGS, CPG, conventional hydrothermal) crossed
   with heat vs. power output, so `tango_next` covers the same range of
   use cases as the legacy system.
3. **Port the wider example library** — roughly 68 previously-validated
   configurations from the old system are queued to be confirmed running
   correctly in `tango_next`.
4. **Design the economics layer** — LCOE/LCOH cost modeling for `tango_next`,
   currently a placeholder.
5. **Build an optimization API** — automated design-space search
   (multi-objective optimization) for `tango_next`, modeled on a proven
   pattern from a sister project, with an explicit design principle that
   the tool will surface tradeoffs to the user rather than silently
   picking a "best" answer on their behalf.
6. **Performance profiling** — once feature coverage stabilizes, profile
   `tango_next` properly and address any real hotspots (deferred
   deliberately — correctness and clarity were prioritized over speed
   during initial development).
7. **Retire the old codebase** — once all configurations are validated
   against `tango_next`, begin removing `src/tango/` and reducing the
   system to a single, modern implementation.

## Bottom line

The past three weeks focused on making the new codebase trustworthy — closing
the specific kinds of silent-failure bugs that made the old system hard to
maintain — and proving that trust with automated regression coverage, not
just on paper. The next phase shifts from foundation-building to breadth:
covering more system types, more examples, and the economic/optimization
features needed for `tango_next` to fully replace the legacy implementation.
