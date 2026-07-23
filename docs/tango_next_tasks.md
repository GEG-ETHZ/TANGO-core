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

## Active: common:/component-block override ambiguity

Started 2026-07-22, triggered by `tests/TemperaturePressureDiscrepancy.md`
(landed via the `dev/make-tango-robust` merge) — a real bug where a
component's own YAML block silently overrides a `common:`-declared value in
`workflows/workflow.py::_build_components`'s merge (`{**shared, **own}`,
`own` always wins), so if only one component redeclares a value that's
supposed to be global/ambient, that component silently diverges from every
other component consuming the same field. An intern is pushing their own fix
for this file; the plan is to implement independently in parallel, then
`git stash`/compare/reconcile once their patch lands (their fix stashed out,
verified, then this fix popped back in and re-checked).

- [x] Implemented 2026-07-22: `surface_temperature`/`surface_pressure` are now
      forbidden in any component's own YAML block (`COMMON_ONLY_KEYS` in
      `workflows/workflow.py`) — `ConfigError` raised if redeclared, forcing
      `common:` as the single source of truth. Updated
      `examples/tango_next/flexible_SF_manual.yml` and
      `examples/tango_next/AGS_direct_heat.yml` to move these two keys from
      `components.surface` into `common:` (previously only declared under
      `components.surface`, which happened to work because of the old
      `components_block.get("surface", ...)` fallback that's now removed).
      Also added a `common.get("surface_pressure", ...)` entry to
      `layout_extras` — previously `surface_pressure` wasn't shared at all,
      only `surface_temperature` was. All tango_next regtests pass
      (`test_old_new_parity`, `test_ags_direct_heat_smoke`, full
      `test_tango_next.py`) after the example-file edits, confirming no
      numeric behavior changed.
      `examples/tango_next/SF_manual_differing_st.yml` (the file that
      demonstrates the bug) needed no change — it targets
      `unit: single_flash`, which isn't registered in `COMPONENT_REGISTRY`
      (`SingleFlashSurface` was deleted, see
      [[project_tango_next_ags_surface_design]]), so it's already skipped
      before reaching the merge logic and never exercises the guard either
      way.
      NOT fixed yet: `tests/test_surface_temp_pressure.py` (repo-root, wrong
      convention path) points at a nonexistent file
      (`examples/SF_manual_differing_stp.yml` — wrong dir, wrong filename)
      and has an unrelated `KeyError` bug in `extract_stp_data` (indexes
      `stp[component][...]` without initializing `stp[component] = {}`
      first). Leaving this for the intern's incoming patch, per Chad.
- [ ] **Same-shaped risk elsewhere, not yet fixed** — found by checking which
      fields are (a) declared as Pydantic fields on 2+ different component
      classes AND (b) plausible to set under `common:`, since that's exactly
      the precondition that made surface_temperature/pressure dangerous.
      Confirmed via grep across `src/tango_next/components/`:
      - `thermal_gradient` — declared on `well/lumped.py` (x3 well variants),
        `well/numerical.py`, `reservoir/lumped.py`.
      - `rock_density`, `rock_cp`, `rock_k` — declared on `well/numerical.py`
        and `reservoir/lumped.py`.
      - `well_spacing` — declared on `reservoir/lumped.py` and
        `surface/graph.py`.
      None of these currently diverge in the checked-in example files (spot
      checked all of `examples/tango_next/*.yml` — no component's own block
      currently sets any of these), so this is a latent footgun, not an
      active bug like surface_temperature/pressure was. Before extending
      `COMMON_ONLY_KEYS` to cover them, need to settle a real question: is
      there ever a legitimate reason for a specific well/reservoir to want a
      locally different `rock_k`/`thermal_gradient` (e.g. geological
      heterogeneity between well locations)? If yes, a hard "common: only"
      ban is wrong for those fields and a different mechanism (e.g. an
      explicit opt-in override syntax, or a warning instead of an error) is
      needed. `surface_temperature`/`surface_pressure` were unambiguous
      (ambient/BC state, never legitimately per-component) which is why they
      got the strict treatment first.
- [x] Reconciled 2026-07-22: the intern's patch (`049fdaa`/merge `123ed39`)
      only fixed `tests/test_surface_temp_pressure.py`'s path/`KeyError` bugs
      and changed its assertion to `!=` — i.e. it documented the divergence
      as accepted behavior rather than fixing `_build_components`. It never
      touched `workflow.py`. Popped this session's stash on top cleanly (no
      conflicts — disjoint files). Additionally found and fixed, mid-review:
      (1) `examples/tango_next/SF_manual_differing_st.yml` used a dead
      `unit: single_flash` (deleted component) so the surface was silently
      skipped by the registry lookup rather than ever exercising the guard —
      fixed to `unit: graph` and ported the `nodes:`/`edges:` topology from
      `flexible_SF_manual.yml` (the file's old flat prev/next-per-node schema
      predates `GraphSurface`). (2) `COMPONENT_REGISTRY` misses were
      warn-and-skip, not an error — masked (1) and would silently drop any
      component with a typo'd `type`/`unit`; changed to raise `ConfigError`
      immediately. (3) Rewrote `test_surface_temp_pressure.py` to assert
      `ConfigError` is raised on divergence, replacing the `!=` assertion.
      Full `tests/regtest` suite (70 passed, 40 xfailed) confirms no
      regression in either `src/tango/` or `tango_next`.

## Active: GraphSurface p_out / pressure-provenance follow-ups

Started 2026-07-22 out of a deep-dive into where `GraphSurface`'s TESPy
network states are solved vs. imposed — see
`docs/diagrams/src/graph_surface_state_provenance.drawio` (node-by-node
breakdown for `flexible_SF_manual.yml`) and the vision doc's new
"`GraphSurface`'s fixed `p_out` values" section (justification for why fixed
flash/condensing pressure is a legitimate modeling choice, not a shortcut).
All three items below are intentionally **not started** — captured so the
reasoning doesn't have to be re-derived next session.

- [ ] **Think through the `dh_hx` pressure-DOF case carefully before touching
      it.** Unlike the SF plant's condenser, `AGS_direct_heat.yml`'s `dh_hx`
      has no `p_out` field at all — checked TESPy's `SimpleHeatExchanger`
      mandatory constraints directly (`mass_flow_func`, `fluid_func`,
      `energy_balance_func` only, no pressure relation), so `dh_hx`'s inlet
      and outlet pressures are each independently pinned elsewhere (inlet by
      the well-minus-pipe-friction calc, outlet by `injection_pressure`) with
      zero relationship enforced between them by the component itself. This
      is a sharper version of the fixed-`p_out` risk, not the same pattern —
      there's no `p_out` value to even inspect when reviewing the YAML. Left
      alone for now; needs real thought (not a quick fix) before deciding
      whether the right answer is a validation check, a required `p_out`,
      or something else.
- [x] **Port `src/tango/`'s pressure-monotonicity validation — done 2026-07-23.**
      Added `GraphSurface._validate_pressure_monotonicity()`
      (`components/surface/graph.py`), called from `init()` right after
      `node_cfgs`/`edge_cfgs` are parsed (pure YAML-config check, no TESPy
      objects needed). Same algorithm as `flexible_pp.py`'s
      `validate_pressure_monotonicity()`: walk upstream from every node with
      a fixed `p_out_megapascals`, stopping at pressure-increasing nodes
      (`Compressor` — `tango_next` has no separate `Pump` type, pumps are
      `type: Compressor`), raise `ConfigError` if a downstream `p_out`
      exceeds an upstream one. Verified: (a) raises correctly on a
      deliberately-sabotaged copy of `flexible_SF_manual.yml` (turbine
      `p_out` bumped above valve's); (b) no false positive on
      `pump`/`pump2` — confirmed they're simply absent from the check's
      `p_out_values` dict since they don't declare `p_out_megapascals`
      explicitly (their pressure is solved via `Merge`'s equality
      constraint, as expected); (c) full `tests/regtest` suite still 70
      passed / 40 xfailed, no regressions. Locked in with two permanent
      tests in `tests/regtest/test_tango_next.py`
      (`test_pressure_monotonicity_passes_on_valid_config`,
      `test_pressure_monotonicity_rejects_rising_pressure`) built on a new
      reusable `sf_manual_config` fixture (fresh parsed dict of
      `flexible_SF_manual.yml`, safe to mutate per-test) — the failing case
      mutates a live config dict to push the turbine's `p_out` above the
      valve's, then constructs a real `Workflow` from it and asserts
      `ConfigError`. Both run in under half a second since `Workflow(cfg)`
      construction alone triggers `GraphSurface.init()` (via
      `Component.from_config()`) — no `.run()`/TESPy solve needed to
      exercise the check.
      **Known gap, not addressed by this port** (documented in the method's
      own docstring so it's visible from the code, not just this file): it
      only traces nodes that explicitly declare `p_out_megapascals`, so it
      does NOT catch `AGS_direct_heat.yml`'s `dh_hx` case (no `p_out` field
      at all — see the still-open item above) or anything else where
      pressure is implicit rather than declared.
- [x] **Add unit comments to every `p_out`/pressure-bearing key in every
      `tango_next` TESPy-graph YAML file — done 2026-07-23.** Checked all 3
      `examples/tango_next/*.yml` files with `power_plant` blocks
      (`flexible_SF_manual.yml`, `AGS_direct_heat.yml`,
      `SF_manual_differing_st.yml`). `p_out_megapascals`/`T_out` already had
      unit comments (added when these files were first written/ported — not
      actually missing). The real gap was `efficiency:` (7 occurrences) and
      `vapor_mass_fraction_out:` (2 occurrences) having no unit/scale note at
      all — added `# dimensionless [0-1] — TESPy eta_s (isentropic
      efficiency)` and `# dimensionless [0-1] — TESPy vapor quality x (0 =
      saturated liquid, 1 = saturated vapor)` respectively. Full
      `test_old_new_parity`/`test_tango_next.py`/
      `test_surface_temp_pressure.py` suite still green after — comment-only
      diff, confirmed via `git diff`.
- [ ] **Same gap exists much more widely in `src/tango/`'s old-format
      examples — separate, bigger task, explicitly deferred.** Spot-checked
      `examples/flexible_SF_manual.yml`/`flexible_ORC_manual.yml`: `p_out:`
      values (e.g. `p_out: 0.5`, `p_out: 0.05`) have zero unit comments
      anywhere. `grep -rln "power_plant_graph:" examples/` (excluding
      `tango_next/`) turns up **60+ files** — a real gap, but not "easy," so
      explicitly not swept today (Chad's call, 2026-07-23, when offered a
      3-way scope choice). If picked up later: same treatment as above
      (`p_out` is bar per `flexible_pp.py`'s `Network(p_unit="bar", ...)`),
      but budget it as its own task, not a quick add-on.

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
