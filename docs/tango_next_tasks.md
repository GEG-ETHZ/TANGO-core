# tango_next granular task tracker

**END OF DAY 2026-07-24 (later today, after the AGS sweep demo below)**:
Chad wants help preparing a markdown file summarizing, at a managerial
level, the high-level objectives accomplished in the past 3 weeks plus
plans for the next couple months. Not started — flagging so it isn't
forgotten across the commit/compact about to happen.

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

### 3a. IMMEDIATE NEXT — small demo sweep, not the full port below
Decided 2026-07-24, to be built same day (after a commit/compact of the
`Common`/`to_dict()` refactor work). Scope is deliberately much smaller than
task 3 below: get `examples/tango_next/AGS_direct_heat.yml` (already exists,
already unblocked — no ORC gap, since it's direct-heat) running through a
minimal sweep script that demonstrates the dict-modify-then-reinstantiate
pattern from this session's `Common`/`Workflow.to_dict()` work, end to end,
on a real example — not the full generate/sweep/summarize/plot pipeline
matching old tango's apps (that's task 3 below, still blocked/deferred).
Requirement: **at least one swept parameter must live in `common:`** (e.g.
`rock_k` or `thermal_gradient`), specifically to exercise the shared-`Common`
reference architecture, not just component-local fields — the whole point is
demonstrating today's work, not just any parameter sweep. Pattern:
`cfg = base_wf.to_dict(); cfg["common"][...] = x; Workflow(cfg).run()`, per
`Workflow`'s class docstring.

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
- [ ] **`AGS_direct_heat.yml` parity — scoped 2026-07-23, bigger than it
      looks, NOT started.** Currently NOT in `test_old_new_parity.py`'s
      `PARITY_CASES` at all — only has a standalone smoke test
      (`test_ags_direct_heat_smoke` in `test_tango_next.py`) asserting
      positive net thermal power, no actual old-vs-new numeric comparison.
      This isn't a one-line registry addition — three real pieces of work:
      1. **No old-tango file lives under `examples/`.** The only old-tango
         counterpart is `applications/run_AGS_direct_heat_sweep/
         triemli_dh_base.yml` (a sweep-app file, params overwritten per
         design point by `sweep.py`). `_run_old_tango`'s path handling
         (`EXAMPLES_OLD / case.old_yml`) assumes everything lives under
         `examples/` — need to add a static single-point copy there first
         (matching `examples/AGS_new/`'s "validated reference point" pattern),
         with `well_length`/`mass_rate`/etc. fixed to match
         `examples/tango_next/AGS_direct_heat.yml`'s actual values (3000 m
         vertical, 707 m horizontal, 30 kg/s).
      2. **The comparison harness (`_run_old_tango`/`_run_tango_next` in
         `test_old_new_parity.py`) is hardcoded to the SF/DOUBLET topology**
         — fixed keys `reservoir_T`, `production_well_pump_T`,
         `turbine_power_real`. AGS direct-heat has no reservoir at all
         (sealed closed loop), a single `production_well` (not the
         lower/upper split), and no turbine — it's a district-heating heat
         exchanger (`dh_hx` in tango_next, `DH` node in old tango), so
         "gross power" isn't the right comparable quantity; thermal power
         delivered is. `ParityCase`'s tolerance fields (`res_T_atol`,
         `prod_T_atol`, `power_rtol`) are similarly SF-shaped and don't fit.
         Needs either a topology-aware branch in the harness or a second,
         parallel comparison path for no-reservoir/thermal-only cases.
      3. **Old tango's per-timestep thermal-power result key isn't
         confirmed.** `native_workflow.py` builds per-timestep result keys
         as `f"{component_name}_Q"` (mirrors `_P` for power, e.g. the
         existing `turbine_power_real`-style lookups). The DH heat
         exchanger's node name in `triemli_dh_base.yml`'s
         `power_plant_graph` is `DH`, so the key is very likely `DH_Q` in
         `workflow.results` — not yet verified by actually running it and
         inspecting the dict.
      Chad's call 2026-07-23: scope it here, don't build yet — pick up when
      there's room for a real (not "quick") task.
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
- [x] **`thermal_gradient`/`rock_density`/`rock_cp`/`rock_k` — fixed
      2026-07-23.** Chad's call: unlike the general "same-shaped risk"
      question below, these four are unambiguous (should always match
      between every well and the reservoir — no legitimate per-component
      override), so they got the same treatment as
      `surface_temperature`/`surface_pressure`, plus one more layer:
      1. Added to `COMMON_ONLY_KEYS` (`workflows/workflow.py`) — config-time
         guard, same as before.
      2. **New**: also marked `Field(frozen=True)` on these fields (plus
         `surface_temperature`/`surface_pressure`, closing that original gap
         too) across `well/lumped.py` (all 3 well variants),
         `well/numerical.py`, `reservoir/lumped.py`, `surface/base.py`.
         Verified empirically (Pydantic v2, this repo's exact version) that
         per-field `frozen=True` (a) raises `ValidationError` on
         post-construction mutation (`well.rock_k = x`), (b) does NOT
         require model-level `validate_assignment=True`, (c) has zero
         measurable cost on sibling mutable fields (confirmed
         `surface.injection_pressure`, which `SystemBCIteration` reassigns
         every BC-iteration pass, is untouched). This closes a real gap (1)
         alone didn't: (1) only guards how a `Workflow` is *built* from
         YAML — it says nothing about code that mutates an already-built
         live component directly (e.g. a sweep script reusing objects
         instead of rebuilding).
      3. Confirmed (and documented, in `COMMON_ONLY_KEYS`'s comment block)
         that `frozen=True` does NOT block the *intended* uses: (a)
         standalone component construction/reconstruction via
         `model_dump()`/`from_dict()` (unaffected — frozen only guards
         post-construction assignment, not construction itself; matches
         `tests/unit/test_serde_roundtrip.py`'s existing pattern), and (b)
         `component.model_copy(update={...})` on a standalone component
         (deliberately bypasses Pydantic validation by design — the correct
         tool for e.g. sweeping a single standalone well's `rock_k`, since a
         standalone well has no sibling component to diverge from).
      4. Locked in with 3 new tests in `test_tango_next.py`:
         `test_common_only_rejects_well_shared_rock_param_override`,
         `test_common_only_rejects_reservoir_shared_rock_param_override`,
         `test_frozen_shared_rock_param_rejects_runtime_mutation`. Full
         `tests/regtest` suite: 80 passed / 40 xfailed (up from 75 — this
         plus the serialization tests below), no regressions.
      5. **Follow-on, also built 2026-07-23**: the fix surfaced a real gap
         while discussing sweep workflows — `Workflow` had no public,
         documented way to get a config dict back out of an already-built
         instance (only the private `self._config`), which is exactly what
         you need to do a *Workflow-level* sweep (as opposed to a
         standalone-component one) without either relying on a private
         attribute or holding onto the original raw dict yourself. Added
         `Workflow.to_dict()` (fresh `deepcopy`, safe regardless of how
         the `Workflow` was built), plus `from_str()`/`to_str()`/`to_file()`
         alongside the existing `from_file()` — modeled on fastsim-core's
         `SerdeAPI` trait pattern (see
         [[project_phase2_architecture_lessons]]). 5 new round-trip tests
         in `test_tango_next.py` (`test_workflow_to_config_*`,
         `test_workflow_from_str_to_str_roundtrip`,
         `test_workflow_to_file_from_file_roundtrip`,
         `test_workflow_sweep_pattern_does_not_mutate_base`), the last one
         using `tmp_path` per Chad's ask. Recommended sweep pattern, now
         documented in `Workflow`'s class docstring:
         `cfg = base_wf.to_dict(); cfg["common"][...] = x; Workflow(cfg)`.
- [x] **SUPERSEDED 2026-07-23 — replaced the guard-list approach above with a
      structural one.** After the `Field(frozen=True)`/`COMMON_ONLY_KEYS`
      work above, Chad flagged (rightly) that old tango's `CommonSpecs`
      dataclass precedent isn't a model to imitate (sloppy code around it),
      and that `well/reservoir/surface` holding independent COPIES of
      shared values — even guarded — is weaker than making divergence
      structurally impossible. Landed:
      1. **`core/specs.py`** (new file — moved here from `workflows/specs.py`
         since `components/` needs to import it too, and `workflows →
         components` is the established dependency direction, not the
         reverse): `Common`, `Layout`, `SimConfig` — real Pydantic schemas
         (`extra="forbid"`, whole-model `frozen=True`) for the `common:`/
         `layout:`/`sim_config:` YAML blocks, previously all
         `dict[str, Any]` with zero validation. Named without the `*Specs`
         suffix deliberately (Chad: "I don't even want to see `CommonSpecs`
         because the code around that was sloppy").
      2. **Components now hold `common: Common`** (a single field) instead
         of 6 independent `rock_k`/`rock_density`/`rock_cp`/
         `thermal_gradient`/`surface_temperature`/`surface_pressure` fields
         each — across `well/lumped.py` (×3), `well/numerical.py`,
         `reservoir/lumped.py`, `surface/base.py`. `fluid_name` moved in
         too (was common-sourced but never got the `COMMON_ONLY_KEYS`
         treatment — a real inconsistency this closed as a side effect).
         Verified empirically (this repo's exact Pydantic v2 version):
         passing the same `Common` instance into multiple components'
         constructors gives a genuine shared reference
         (`well.common is reservoir.common is shared` → `True`) — Pydantic
         does not copy nested model fields on construction. `_build_components`
         (`workflows/workflow.py`) now constructs ONE `Common` and hands
         the same reference to every component that declares the field.
      3. **`COMMON_ONLY_KEYS` and per-field `Field(frozen=True)` are gone
         entirely** — no longer needed. A component's own YAML block
         setting `rock_k` is now rejected as an ordinary unknown-key error
         (the component doesn't declare that field name anymore, only
         `common`), not a special-cased guard list. `Common` itself is
         frozen at the model level, so `well.common.rock_k = x` still
         raises — ONE check instead of six, and it protects every
         component sharing that instance at once, not just the one you
         happened to touch. Also explicitly guard against a component's own
         block setting `common` directly (same rejection, `ConfigError`).
      4. **Scope decision, explicit**: `well_spacing` (layout) and
         `dt_years` (sim_config) were NOT given the same shared-reference
         treatment — components still get individually-threaded values for
         those two, unchanged from before. Chad's call when offered the
         choice ("Common only, for now") — see the still-open item below.
      5. **`Workflow.to_dict()`/`to_str()`/`to_file()` fully rewritten —
         `self._config` deleted entirely.** This was the actual point of
         all of the above, surfaced when Chad pushed back hard on the
         earlier `to_dict()` (which returned `deepcopy(self._config)`, a
         cached copy of construction-time input): proved empirically that
         mutating a live, non-frozen field (e.g.
         `surface.injection_pressure = x`) was NOT reflected in
         `to_dict()`'s output — a real, silent staleness bug, directly
         analogous to `src/tango/`'s `specs.org`/`raw_specs` pattern (found
         in `flexible_pp.py:55,62` — confirms this was an old-tango
         carryover, not a `tango_next`-native design). Chad's stated
         reasons (verbatim, worth keeping): wants the YAML schema fully
         documented with "no guesswork"; worried people would edit a
         retained `_config`-like object thinking it had effect and it
         didn't; worried people would mutate live objects thinking it
         propagated back to a cached dict and it didn't; and if `to_dict()`
         could return either the object's real state or a cached dict with
         no way to tell which (or whether they'd drifted apart), that's
         irreducibly ambiguous. Fix: `Workflow` now retains `self._common`/
         `self._layout`/`self._sim_config` (the validated, frozen,
         canonical instances — never mutated after `__init__`) plus
         `self.title` (plain passthrough) and `self._economic_raw` (one
         deliberate, clearly-labeled exception — see next item). `to_dict()`
         reconstructs fresh on every call: `common:`/`layout:`/`sim_config:`
         from those retained instances' `model_dump()`, `components:` from
         each LIVE component's own `model_dump()` (inherently live —
         Pydantic has no caching to go stale) plus its `type`/`unit`
         routing key recovered via a reverse lookup into
         `COMPONENT_REGISTRY` (checked: every registry value is a distinct
         class, so this is unambiguous). Verified the original bug is
         actually fixed: mutating `surface.injection_pressure` after
         construction now shows up in `to_dict()` immediately, every time.
      6. **Two dump-format bugs found and fixed along the way**:
         (a) `model_dump(mode="json")` converts `LockedState`'s "not yet
         computed" `float('nan')` sentinel to `None` (not valid JSON),
         which then fails to reload — switched to plain `model_dump()`
         (NaN survives; `yaml.safe_dump`/`safe_load` round-trip it fine via
         the `.nan` tag) plus a small `_yaml_safe()` recursive helper that
         normalizes the one thing plain `model_dump()` leaves unsafe for
         YAML (`Enum` members — `InjectionPolicy`, `FrictionModel`,
         `HeatTransferModel`) to their plain `.value` string. Confirmed with
         Chad this isn't introducing JSON as a format anywhere — YAML stays
         the only serde format end to end; `mode="json"` was just Pydantic's
         (confusingly-named) "give me plain-Python-safe types" dump flag.
         (b) Comparing pre-solve `to_dict()` output via dict `==` spuriously
         fails even between two genuinely-identical Workflows, because
         `float('nan') != float('nan')` under IEEE-754 — not a real bug.
         Chad's fix (better than my first attempt, which just ran the
         simulation first to dodge it): compare the two `to_str()` YAML
         **strings** directly instead of parsed dicts — `.nan` serializes
         to the identical text either way, so string equality sidesteps
         the issue at the root without needing to solve anything first.
      7. **`economic:` — deliberate, labeled exception, not swept up in
         "everything has a schema."** No `EconomicComponent` reads it yet
         (Phase 2 placeholder — confirmed via grep, genuinely unwired, not
         just unused-by-convention). Rather than invent a schema for fields
         nothing consumes (risks getting the shape wrong, redoing it once
         the real component lands) or silently drop the block on round-trip,
         it's retained verbatim/unvalidated as `self._economic_raw` purely
         so `to_dict()` doesn't lose it — explicitly documented as a
         temporary passthrough to remove once a real economic schema
         exists. Matches the one class of exception Chad said was
         acceptable, citing fastsim's `Option<...>`-then-`Some(...)`
         pattern for derived fields (`eff_interp_at_max_input` in
         fastsim-core's `electric_machine.rs`) — a handful of clearly-labeled
         exceptions is fine; an undocumented, ambiguous cache is not.
      8. **`brine_density` and `well_pattern`/`well_pattern_dimens` —
         confirmed dead, handled differently.** `brine_density` (present in
         every example file's `common:` block) is consumed by nothing in
         `tango_next`, and isn't in old tango's `CommonSpecs` either —
         genuinely dead cruft, now rejected by `Common`'s `extra="forbid"`;
         removed from all 3 `examples/tango_next/*.yml` files.
         `well_pattern`/`well_pattern_dimens` are ALSO currently unused, but
         kept as declared-but-inert fields on `Layout` (not deleted) since
         there's a real forward-looking reason (`reservoir/lumped.py`'s
         "TODO (Phase 2): add 5-spot and inverted-5-spot impedance
         variants") — different treatment for a different reason, not an
         oversight.
      9. Tests: rewrote every test that referenced the old
         `COMMON_ONLY_KEYS`/per-field-frozen mechanism to match the new
         structural one (`test_component_own_block_rejects_shared_rock_param`,
         `test_component_own_block_rejects_common_object`,
         `test_components_share_one_common_instance_by_reference` — proves
         shared identity via `id()`, `test_frozen_common_rejects_runtime_mutation`);
         rewrote the `to_dict()` round-trip tests (dropped the
         now-semantically-wrong "equals raw source YAML" check — `to_dict()`
         legitimately includes more than hand-authored input now, e.g.
         `NumericalWell`'s derived `T_r`/`cell_length`; replaced with a
         representative-input-values check plus the string-comparison
         round-trip tests above); added
         `test_workflow_to_dict_reflects_live_mutation_not_a_stale_cache` as
         the direct regression test for the bug that started all of this.
         Full `tests/regtest` suite green throughout (confirmed at each
         step); `mypy src/tango_next/` clean; `ruff` clean.
- [ ] **NEXT SESSION — Chad wants to understand the shared-reference
      mechanics more deeply before this is considered settled.** Raised
      2026-07-23 at the very end of a long session ("brain is smoking"),
      explicitly deferred — do not just answer inline next time, treat as
      the first real discussion of the new session. Three questions, verbatim:
      1. For sweeps: do we change the source `Common` value, or can we
         mutate ANY reference to it (e.g. `some_well.common`) and have that
         propagate back to every other component sharing it? (Answer is
         "neither, exactly" — `Common` is frozen, so no live mutation
         propagates anywhere; sweeps rebuild fresh per design point via
         `Workflow.to_dict()` — but this needs to be walked through
         carefully with concrete examples, not just asserted.)
      2. How robust is this reference-sharing mechanism, really? (Worth
         covering: what happens on `model_copy()` — verified earlier this
         session it does NOT preserve the shared reference the same way,
         see the `model_copy(update=...)` discussion; what happens under
         (de)serialization round-trips — does `from_dict()` on a full
         `Workflow` config reconstruct ONE shared `Common` or accidentally
         give each component its own copy again? This wasn't explicitly
         re-verified after the `to_dict()`/`_config` rewrite — should
         confirm `Workflow(wf.to_dict())` still gives every component the
         SAME `common` object, not just equal ones.)
      3. Chad's intuition is that Python reference semantics here would
         NOT translate directly to Rust (fastsim-core is Rust) — wants this
         explained explicitly: `Rc<RefCell<Common>>`/`Arc<Mutex<Common>>`
         vs. Python's default pass-by-object-reference, why Rust's ownership
         model wouldn't let multiple structs hold an unsynchronized shared
         mutable reference the way Python just did, and what the Rust
         equivalent of "shared, effectively-immutable-in-practice state"
         actually looks like (interior mutability patterns, or just Rc
         without RefCell since Common is conceptually frozen anyway).
- [ ] **`well_spacing` — separate, NOT yet decided** — declared on
      `reservoir/lumped.py` and `surface/graph.py`. Explicitly discussed
      2026-07-23 as "less obvious" than the rock/thermal fields — Chad
      wanted to fix the unambiguous ones first and come back to this one.
      Not yet resolved: is there a legitimate reason `well_spacing` could
      differ between the reservoir's impedance calc and the surface's
      injector-to-producer pipe-run length? (They're both nominally "the
      same physical distance" today, but conceptually one is a reservoir
      hydraulics parameter and the other is a surface piping length, which
      is a weaker coupling than "the rock is the same rock.")
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
      `Component.from_dict()`) — no `.run()`/TESPy solve needed to
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
- Speculative long-horizon architecture thinking (Modelica-family tooling,
  e.g. Rumoca, as a possible eventual replacement foundation for TESPy's
  causal-solve approach) — `docs/long_term_architecture_exploration.md`,
  started 2026-07-24. Explicitly parked, not planned; not blocking
  anything above.
- **pymoo optimization API for `tango_next`** — see the vision doc's Phase 3
  task list (2026-07-24). Not started; modeled on fastsim's `pymoo_api.py`.

  **`src/tango/optimizerr.py` review (2026-07-24)** — read in full (1229
  lines) before answering whether it's worth reusing. Verdict: the overall
  shape (`Optimizer` → `BaseOptimizer` → `{SOOOptimizer, MOOOptimizer}`,
  each defining a pymoo `Problem` and wiring `minimize()`) is a reasonable
  scaffold, similar in spirit to fastsim's `ModelObjectives`/
  `CalibrationProblem` split — but the plumbing inside has real problems,
  not just style complaints:
  - **`set_parameter()` (line 232) uses `exec(f"{param_path} = {value}")`,
    and `objective_func()` (line 134) uses `eval(target)`** to read/write
    arbitrary attribute paths built from string templates
    (`parameter_mappings.py`'s `VARIABLE_PARAMETER_MAPPING`). This is a
    genuine anti-pattern, not just ugly: no type checking, no useful error
    location, and a real (if currently low-probability, since the string
    templates are developer-authored, not user input) code-injection shape
    if that ever changes. fastsim's `pymoo_api.py` solves the identical
    problem — set a parameter by name, extract an objective by name —
    with plain `Callable` functions operating directly on a dict (see
    `new_cab_length_m`/`get_mod_soc` in `cal_bev.py`). That's the pattern
    to actually follow, not `optimizerr.py`.
  - **Broad `except Exception: print(...); return inf`** (lines 143-149,
    252-257, 277-282) swallows real bugs during optimization and silently
    treats them as "bad but valid" objective values — matches the
    silent-failure-mode pattern already flagged as a `src/tango/`
    anti-pattern elsewhere (see `project_src_tango_gotchas` memory).
  - **Sign-convention handling for maximize-vs-minimize looks tangled
    and worth distrusting, not just distasteful**: `objective_func`
    (lines 136-139) negates based on `target_type` with DIFFERENT logic
    for the single- vs. multi-objective case, and then `SOOOptimizer`
    separately negates again unconditionally (`out["F"] = -1 *
    self.objective_func(x)`, line 640). Two negation layers with
    different conditions in different files is exactly the shape of bug
    that produces a wrong-but-plausible-looking optimum. Did not fully
    trace whether it's actually wrong — flagging as needs-verification-
    before-trusting, not confirmed-broken.
  - Plotting/logging (`plot_results`, `print_results`,
    `plot_hypervolume_igd`) is hardcoded to write PNGs/log files to
    `os.getcwd()` unconditionally — no separation between the
    optimization logic and its side effects, no way to run headless or
    under test without touching disk.
  - Real DRY violation between `SOOOptimizer`/`MOOOptimizer` (algorithm
    selection, variable range/type extraction, result printing are
    largely copy-pasted with small variations).

  **What IS worth keeping, conceptually** (not necessarily the code
  as-written): the Achievement Scalarizing Function (ASF) and
  pseudo-weights Pareto-front final-solution-selection logic
  (`_select_asf_solution`/`_select_pseudo_weights_solution`,
  `calculate_asf`/`calculate_pseudo_weights`, lines 999-1229) is real,
  non-trivial domain logic — picking one representative solution off a
  multi-objective Pareto front is a genuine need pymoo doesn't solve for
  you, and ASF/pseudo-weights are legitimate, well-known MOO
  decision-making techniques. Worth reimplementing cleanly (dict-based,
  no eval/exec, proper tests) rather than inventing a different selection
  method from scratch. Handling both SOO and MOO with a sensible dispatch
  on objective count, and supporting both integer and float variables,
  is also reasonable scope to carry forward.

  **Bottom line**: not "garbage" outright — the architecture shape and
  the Pareto-selection math are worth keeping conceptually — but the
  parameter-setting/objective-extraction mechanism (eval/exec) is a real
  problem to leave behind entirely, not a style nitpick, and fastsim's
  `pymoo_api.py` is the actual pattern to follow instead.
