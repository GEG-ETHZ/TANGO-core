# tango_next granular task tracker

Working-level task list for `tango_next` porting/parity work. This is the
detailed, frequently-updated companion to `docs/TANGO_vision_and_roadmap.md`
— reconcile the two periodically (when a section here is fully done, fold a
one-line summary into the vision doc's Phase 3 task list and prune the
detail from here). The vision doc is the durable, Confluence-bound
narrative; this file is scratch-adjacent but checked in, for tracking
in-flight multi-step work across sessions.

## Active: AGS sweep parity (heat + power)

Started 2026-07-22. Scope: get both AGS sweep apps (direct-heat and the new
power-generation counterpart) verified in old tango, fully ported to
`tango_next` under `applications/tango_next/run_AGS_sweep/`, compared
against old tango, and locked in with golden-snapshot regression coverage.

### 1. Demand-profile documentation for the thermal AGS sweep
- [x] Document that `run_AGS_direct_heat_sweep` assumes constant heat
      demand, not a real seasonal/dispatch curve — done 2026-07-21:
      `applications/run_AGS_direct_heat_sweep/run_AGS_direct_heat_sweep.py`
      docstring item 5, cross-referenced from
      `docs/TANGO_vision_and_roadmap.md`'s "Seasonal heat-demand variation"
      section (also cross-references `run_AGS_sweep/`).
- [ ] Revisit once the seasonal-demand-mechanism design (vision doc,
      same section) is actually built — re-check whether the AGS sweep
      apps should adopt it, or whether that's genuinely a separate,
      later effort (dispatch/time-series sweeps vs. steady-state design
      sweeps are different tools).

### 2. Verify both AGS sweeps run correctly in old tango
- [ ] `run_AGS_direct_heat_sweep`: last full 6006-design run was
      2026-07-15. Re-run (or at least spot-check a representative subset)
      to confirm nothing in `src/tango/` has regressed it since.
- [ ] `run_AGS_sweep` (new, electric): only smoke-tested at a single
      design point (base YAML) plus one pipeline row (row 0) so far. Run a
      broader subset spanning the depth/mass-flow/loop extremes before
      trusting the full grid — the direct-heat sweep's 8000 m depth-tier
      failure (`target_extraction_pressure` too low) is a precedent for
      edge-of-range failures that a single design point won't catch.

### 3. Port both to `tango_next` under `applications/tango_next/run_AGS_sweep/`
- [ ] **Blocking gap**: `tango_next` has no ORC / power-plant component yet
      (`grep -rli orc src/tango_next/` → nothing). The direct-heat port
      only needed `GraphSurface` + a `SimpleHeatExchanger` node, which
      already existed. The power port needs either a new dedicated ORC
      component, or a `GraphSurface` subgraph (turbine/condenser/pump) that
      reproduces what `native_ORC` builds internally. Scope this as its
      own design discussion before writing YAML.
- [ ] Decide app structure: one shared `tango_next` sweep pipeline
      parameterized by product (heat/electricity), or two directories
      mirroring old tango's split. Leaning toward shared, since the
      well/loop topology and all four sweep axes are identical between the
      two old-tango apps and only the surface block differs — avoids
      duplicating the generate/sweep/summarize/plot pipeline twice.
- [ ] Wire the four sweep axes (depth, mass-flow, loop-length,
      loop-diameter) through `tango_next`'s YAML-mutation pattern,
      matching old tango's `sweep.py` `_apply_*` functions.
- [ ] `examples/tango_next/AGS_direct_heat.yml` already exists (single
      design point, not the swept version) — decide whether the new sweep
      app reuses/generalizes it or the sweep pipeline generates its own
      per-design YAML from a template the way old tango's does.

### 4. Compare tango_next vs. old tango, close/explain discrepancies
- [ ] `AGS_direct_heat.yml` is currently NOT in `test_old_new_parity.py`'s
      `PARITY_CASES` at all — it only has a standalone smoke test
      (`test_ags_direct_heat_smoke` in `test_tango_next.py`) asserting
      positive net thermal power, no actual old-vs-new numeric comparison.
      Add it as a real `ParityCase` first, before worrying about
      sweep-level comparison.
- [ ] Add an equivalent parity case for the power variant once its
      `tango_next` port exists.
- [ ] Decide comparison scope: full 6006-point sweep-vs-sweep comparison
      is expensive and probably unnecessary. Proposal: single-point parity
      (already the pattern) plus a small hand-picked set spanning the
      depth range (e.g. shallow/mid/8000 m-edge-case), not the full grid —
      revisit only if that surfaces something that needs denser sampling.
- [ ] Investigate and either fix or document (with tolerance/rationale,
      matching the existing `ParityCase` tolerance-with-notes pattern) any
      discrepancy found beyond old-vs-new tolerance.

### 5. Golden-snapshot regression coverage
- [ ] `tests/regtest/golden_tango_next/` currently only has
      `flexible_SF_manual.json`. Add golden snapshots for the AGS
      direct-heat case (once added to `PARITY_CASES`, step 4) and the AGS
      power case, via `tools/update_tango_next_golden.py`, only after
      their outputs are trusted (i.e., after step 4's discrepancies are
      resolved/explained — a golden snapshot locks in whatever's there,
      good or bad).

## Backlog (queued, not yet started)

- LCOE/LCOH economic-component design work for `tango_next` — paused
  2026-07-21 before reading any `src/tango/units/native/economic/*.py`
  source. Relevant to AGS sweep work since old tango's sweep scripts both
  read CAPEX/LCOE off `economic._results`.
- Seasonal/variable heat-demand mechanism design (see vision doc's
  "Seasonal heat-demand variation" section) — the real fix for task 1's
  gap, not yet designed.
- `tango_next` example coverage matrix (AGS/EGS/CPG/Hydrothermal ×
  heat/power) — vision doc, Phase 3. AGS row is closest to complete once
  this effort lands.
- Broader old-tango example porting (58 confirmed-PASS + ~10
  confirmed-fine-just-slow per `REPO_CLEANUP_AUDIT.md`) — vision doc,
  Phase 3.
- Profiling `tango_next` once it stabilizes — vision doc, Phase 3.
