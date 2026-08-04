# tango_next granular task tracker

Working-level task list for `tango_next` porting/parity work. This is the
detailed, frequently-updated companion to `docs/TANGO_vision_and_roadmap.md`
— reconcile the two periodically (when a section here is fully done, fold a
one-line summary into the vision doc's Phase 3 task list and prune the
detail from here). The vision doc is the durable, Confluence-bound
narrative; this file is scratch-adjacent but checked in, for tracking
in-flight multi-step work across sessions.

## Next session priorities (set 2026-08-03)

Top of the queue for the next session, in order:

1. **Injection-wellhead inlet-temperature guess robustness.** Right now a
   bad user-supplied guess can crash the solver outright even when the
   rest of the system is physically valid, despite the fact that we
   already iterate on injection temperature. Plan (Chad's, shared with
   coworkers on Slack 2026-08-03): on a solver failure from a bad guess,
   retry with a lower guess closer to surface/ambient temperature; if it
   would need to go *below* surface temperature to get a working first
   iteration, fail outright (that's a genuinely invalid case, not a bad
   guess). This also means the user should be able to leave the initial
   guess blank entirely and let tango_next pick one — consistent with the
   idea floated earlier this session that ~65% of the way from reservoir
   temperature to ambient is a good default starting guess. When the pivot
   fires (retrying with a lower guess after a bad-guess solver failure),
   don't fail silently — log a `WARNING` (or similar) so it's visible that
   an automatic correction happened, even though it's not an error.
   Implementation lives in `SystemBCIteration._converge_injection_T` /
   `run_timestep`'s `MANUAL` branch (`orchestrators/system_bc_iteration.py`).

   Additional items folded into this same area of work, agreed 2026-08-04:
   - **DONE 2026-08-04 — non-convergence must raise, not warn.**
     `_converge_injection_T`'s `for...else` now `raise`s `ConvergenceError`
     (already existed in `core/errors.py`, no new exception class needed)
     instead of `logger.warning(...)` when `max_inner_iterations` is
     exhausted without converging — previously the loop silently returned
     and the caller used the unconverged state as if it were final.
     Audited the rest of `tango_next` for the same silent-swallow pattern
     (`logger.warning`, bare `except`, other max-iteration loops) — this
     was the only instance; nothing else needed the same fix. Full test
     suite re-run clean (121 passed, 40 xfailed, matches baseline).
   - **DONE 2026-08-04 — `max_inner_iterations` is now a constructor
     parameter** on `SystemBCIteration` (default `DEFAULT_MAX_INNER_ITER =
     20`, same value as before), replacing the hardcoded module-level
     `_MAX_INNER_ITER` constant, so it can be tuned per-case instead of
     requiring a code edit.
   - **Retain the per-timestep injection-temperature convergence history**
     (each iteration's guess, not just the latest) so its behavior can be
     inspected — e.g. to diagnose slow/oscillating convergence, and to
     inform the Newton/secant-acceleration work below. Wipe it at the
     start of each new timestep, so it's just a plain in-memory list
     inspectable with a debugger — no need for a formal `LockedState`/
     `history` mechanism for this, per-timestep debugger visibility is
     good enough.
   - **Newton/secant acceleration of the T-convergence loop is still
     under discussion, not decided** — see the "On Newton's method for
     faster convergence" discussion (2026-08-04 session): replace plain
     Picard substitution with a secant-style extrapolation using the last
     two `(guess, residual)` pairs, mirroring old tango's
     `utils.py::newton()` (already used by `SystemCPGNative.update()` for
     its own outer pressure loop). Chad wants to think this through
     further before committing — **do not implement until he explicitly
     revisits this**, flagged so it isn't silently implemented or
     silently dropped.
   - **CPG dependency, flagged 2026-08-04**: the current production-pump
     boost (`LumpedProductionWellWithPump.solve()`,
     `components/well/lumped.py:310-321`) computes `pump_dp` directly
     (no iteration) by treating the fluid as effectively incompressible
     through the pump — density is evaluated once from inlet conditions
     and held constant across the pressure boost. This is a reasonable
     placeholder for water/brine but **will not hold for CPG**, where the
     working fluid (CO2) is likely supercritical and has strong,
     nonlinear density sensitivity to pressure right in that regime — the
     constant-density assumption breaks down exactly where CPG needs it
     most. **The real iterative pump-solve (already sketched in this
     file's "Planned: inner pump loop" docstring section, lines ~65-82)
     must be implemented before any CPG case can be trusted**, not just
     as a nice-to-have physics upgrade. Treat this as a hard prerequisite
     for CPG parity/validation work, not an independent backlog item.
2. **Flesh out `InjectionPolicy` variants** (today only `MANUAL` is fully
   implemented; see `docs/tango_next_t_convergence.md` for how `MANUAL`'s
   convergence loop works as the reference case).
3. **Implement the `pymoo_api` concept** (optimizer-facing API, per
   `optimizerr.py`/`function_evaluator.py` prior art in old tango).

**Explicit non-goal:** do **not** fix the old-tango AGS
`system_name()`/no-time-marching bug (see "Open items — tracked, not
scheduled" below) — old tango is not being patched.

## Open items — tracked, not scheduled

Real, still-open items that are deliberately **not** being worked next
session. Kept here so they don't get silently dropped or re-discovered
from scratch.

- **Old-tango AGS no-time-marching bug** (`system_name()` routing in
  `src/tango/utils.py` sends AGS-shaped configs to a no-op `SystemNative`,
  so old tango never advances time for AGS configs). Confirmed real,
  three independent ways. **Decision: not fixing old tango for this.**
  tango_next itself is unaffected; this only blocks using old tango as an
  AGS transient reference.
- **MOOSE/MOSKito integration** — ~55 configs unrunnable, hardcoded to a
  former contributor's (Morteza's) machine, no docs left. Blocked on his
  response to outreach. Backlog.
- **No genuine "modest disparity" old-vs-new parity case found yet** — SF/
  EGS/double-flash sweeps all came back "good" agreement. CPG/ORC
  topologies and edge-of-sweep-range points haven't been checked.
- **AGS sweep-vs-sweep comparison** (old tango vs. tango_next, full sweep)
  — blocked on getting all tango_next sweep scripts DVC-consistent with
  `--clean` flags first; not actioned.
- **Debugger walkthrough** (half done) — blocked on re-tracing
  `hydro_double_flash_electric_exec_flow.drawio`'s T-convergence section
  against the new mechanism; `docs/tango_next_t_convergence.md` now
  explains the mechanism itself, but the exec-flow diagram's nodes still
  need re-tracing, not just a warning box.
- Three "Active" threads below (AGS sweep parity port, `common:`/
  component-block override ambiguity, `GraphSurface` p_out/pressure-
  provenance follow-ups) — see their sections for status.
- Untracked repo-root files (`CLAUDE.md`, `deployment_analysis_questions.md`,
  `tango_diagramming_workflow.md`) — left as-is; could be `.gitignore`d
  instead of tracked, still an open call.

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

### 3a. DONE 2026-07-24 — small demo sweep, not the full port below
Built as `examples/tango_next/sweep_demo_AGS_direct_heat.py`. Sweeps
`common.rock_k` (deliberately a `common:` field, not component-local) over
`[1.5, 2.1, 3.0, 4.0]` W/(m·K) against `AGS_direct_heat.yml`, using exactly
the `cfg = base_wf.to_dict(); cfg["common"]["rock_k"] = x; Workflow(cfg).run()`
pattern from `Workflow`'s class docstring. Reports final-timestep
`surface.history.net_thermal_W` per value (monotonically increasing with
rock_k, as expected — more conductive rock delivers more heat to the fluid);
asserts each rebuilt Workflow's three well components all see the new
`rock_k` via their shared `common` reference, and that `base_wf` itself is
never mutated (`base_wf.to_dict()["common"]["rock_k"]` still reads 2.1 after
the sweep). Verified: `rock_k=2.1` mid-sweep row matches a fresh unswept run
of the same YAML exactly (110,149.68 W). Ruff clean. The recurring TESPy
`pr`/`zeta` bound warnings from `dh_hx` are pre-existing baseline noise from
this example (confirmed present on an unswept run too), not introduced by
the sweep.

Deliberately NOT the full generate/sweep/summarize/plot pipeline matching
old tango's apps — that's task 3 below, still blocked/deferred.

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
- [ ] **`AGS_direct_heat.yml` parity — scoped 2026-07-23, picked up
      2026-07-31, BLOCKED on a discovered old-tango bug (not a tango_next
      problem).** Of the three pieces originally scoped, the first two are
      actually done; the third uncovered something bigger than "confirm a
      result key."
      1. **DONE 2026-07-31** — static single-point old-tango reference file
         added at `examples/AGS_direct_heat.yml` (copied from
         `applications/run_AGS_direct_heat_sweep/triemli_dh_base.yml`, the
         two sweep-placeholder fields — `horizontal_well.well_length` and
         `schedule.well_spacing` — fixed from `2500.` to `707.` to match
         `examples/tango_next/AGS_direct_heat.yml`'s reference point exactly:
         3000 m vertical wells, 707 m horizontal loop, 30 kg/s, 25 timesteps).
      2. **Result keys confirmed by actually running old tango**, not
         guessed: production well outlet T is `production_well_T` (K) — via
         `REPORT_SETTINGS["production_well"] = "outlet_fluid"`
         (`core/config.py`) feeding `append_results`'s `f"{unit_name}_{attr}"`
         convention. Heat delivered is `DH_heat_transfer_real` — **not**
         `DH_Q` as originally guessed; it comes from `parse_results_flexible`
         (`utils.py:1105-1115`) reading `component.Q.val` under the key
         `f"{component_name}_heat_transfer"`, then `append_results` on that
         bare float picks up `.real`/`.imag`. Despite the source comment
         saying "Heat transfer in kW," the value's actual magnitude (checked
         by hand: `mass_rate × Δh` from the printed inlet/outlet enthalpy
         table matches the raw number, e.g. `-382461` ≈ `-382.47 kW`
         computed in **W**, not `-382461` kW) confirms it's already in W —
         the comment is wrong, don't scale by 1000.
      3. **BLOCKING DISCOVERY — old tango never advances wellbore transient
         state for AGS (horizontal-well, no-reservoir) configs, at all,
         for the entire run.** Ran the new static file: `production_well_T`
         and `DH_heat_transfer_real` are bit-identical across all 24
         timesteps after t=0 (a separate, differently-signed t=0
         cold-start/init-pass artifact). Suspected a config mistake first,
         so cross-checked against the pre-existing, previously-"validated"
         `examples/AGS_new/AGS_H2O_webapp_native_direct_heat.yml` (20
         timesteps, unrelated to anything touched today) — **same exact
         signature**: `production_well_T` frozen at `333.0700731379618` for
         19 straight timesteps after t=0. Confirmed systemic, not a mistake
         in the new file.

         **Root cause, verified three independent ways (static trace,
         cross-check against an unrelated pre-existing file, AND live
         runtime introspection of the actual instantiated class — not just
         read from source):**
         `src/tango/utils.py::system_name()` (bug condition at line 898,
         confirmed by direct grep — line numbers shift as comments are
         added, always re-grep before citing): `if "horizontal_well" in
         unit_types and "reservoir" not in unit_types: sys_name =
         sys_name.split("_")[0]`. For our AGS config this collapses
         `sys_name` from `"native_flexible"` (set by the surface node) down
         to plain `"native"`. `SYSTEM_OPTIONS["native"]`
         (`units/registry.py:31`) maps to the *base* `SystemNative` class
         (`orchestrators/native.py:14`), whose `balanced()`/
         `update_time_dependent_vars()`/`update()` (lines 67/76/83) are
         literal `return True`/`pass`/`pass` placeholders — real
         time-marching (`t_d` advancement, BC-iteration) only exists in the
         `SystemCPGNative`/`SystemORCNative` subclasses, which this routing
         never reaches. **Confirmed live**: `runner.tango.workflow.sys_name
         == "native"` and `type(runner.tango.workflow.orchestrator) is
         SystemNative` (not a subclass), with
         `inspect.getsource(type(...).update_time_dependent_vars)` printing
         exactly the base class's `pass` body — no override in the MRO gets
         reached. So for any config with a horizontal well and no
         reservoir, **nothing ever advances between timesteps** — the
         "25-year simulation" is the same single solved state repeated 24
         times. This explains both the flatness and the ~3× magnitude gap
         vs. tango_next (382 kW old, flat, vs. tango_next's real transient
         declining 142.7 kW → 110.1 kW over the run) — it isn't a tunable
         numerical deviation, old tango simply has no valid transient
         reference for this topology to compare against.

         **All affected files now carry an explicit in-file warning**
         (added 2026-08-01, not yet fixed): `system_name()`'s docstring and
         the `SystemNative` class docstring in the two files above; every
         old-tango config with `horizontal_well` + no `reservoir` —
         `examples/AGS_direct_heat.yml`, `examples/AGS_new/
         AGS_H2O_webapp_native.yml`, `examples/AGS_new/
         AGS_H2O_webapp_native_direct_heat.yml`, `examples/testcase{6,7,8}.yml`,
         `examples/MVP_templates/testcase{6,7}.yml`,
         `applications/run_AGS_direct_heat_sweep/triemli_dh_base.yml`,
         `applications/run_AGS_sweep/triemli_power_base.yml`; and the four
         sweep-orchestration scripts that run them (`run_AGS_direct_heat_sweep
         .py`/`sweep.py` and `run_AGS_sweep.py`/`sweep.py` in their
         respective `applications/` dirs). `applications/run_EGS_direct_heat_sweep/`
         is NOT affected — checked, it has a `reservoir` node, so it doesn't
         hit this branch.

         Minor, unrelated bug noticed along the way (cosmetic only, not the
         cause of the above, also now flagged in-file):
         `horizontal_well.py`'s consistency check (line 104, re-grep before
         citing) — `if np.abs(well_spacing - horizontal_well.well_length) <
         1e-5: logging.warning("Inconsistent...")` — triggers when the two
         values *match* (small difference), the opposite of what the
         message says; harmless (log-only), not investigated further.

         **Not fixed, not decided how to proceed** — this is old tango's own
         legacy behavior, out of scope to silently patch without sign-off.
         Options to weigh next session: (a) treat AGS direct-heat as having
         no valid old-tango transient reference, and rely on tango_next's
         own smoke test (`test_ags_direct_heat_smoke`) + golden-snapshot
         self-consistency instead of an old-vs-new comparison; (b) fix
         `system_name()`'s AGS routing in old tango so it actually
         time-marches, then re-run this comparison for real; (c) something
         else. Chad's call, not started.
      Comparison harness (`_run_old_tango`/`_run_tango_next` in
      `test_old_new_parity.py` being hardcoded to the SF/DOUBLET topology)
      still needs the parallel no-reservoir/thermal-only path described in
      the original scoping — deferred behind the blocker above, no point
      building it against a reference that can't validate anything yet.
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
      10. **DONE 2026-07-24 — extended `Field(frozen=True)` from `Common`
          to every genuine config field on every `Component` subclass.**
          Chad's ask: could Pydantic enforce that nothing be modified
          directly at all? Answer landed on: not model-wide (would break
          `init()`/`solve()`, which legitimately reassign several plain,
          non-`LockedState` fields as part of running the simulation, not
          config drift), but per-field, splitting each component's fields
          into two buckets:
          - **Frozen (config, set once at construction)**: `component_idx`/
            `save_interval` (base `Component`); `prev`/`next`/`well_length`/
            `diameter`/`pipe_roughness` (`WellComponent`); `prev`/`next`/
            `reservoir_depth`/`thickness`/`permeability`/`porosity`/
            `hydro_static_pressure`/`over_pressure_percentage`
            (`ReservoirComponent`); `prev`/`next`/`common`/`pipe_diameter`/
            `pipe_roughness`/`approach_temperature`/`target_extraction_pressure`
            (`SurfaceComponent`); `common` on every well/reservoir class;
            `dt_years`/`num_cells`/`wellhead_depth`/`gravity_scale_factor`/
            `friction_model`/`heat_transfer_model`/`angle_from_vert_deg`
            (`NumericalWell`); `pump_efficiency`/
            `pump_target_pressure_megapascals` (`LumpedProductionWellPump`);
            `dt_years`/`well_spacing`/`well_eff_diameter`/
            `net_to_gross_ratio` (`LumpedReservoir`); `power_plant`/
            `well_spacing`/`record_node_detail` (`GraphSurface`);
            `project_maturity`/`discount_rate`/`main_product`
            (`EconomicComponent`, unwired but done for consistency).
          - **Deliberately left mutable**: `inlet`/`outlet` (reassigned every
            solve by the orchestrator); `state`/`history` (container never
            reassigned, only its internal fields mutate);
            `SurfaceComponent.injection_pressure` (the BC-iteration guess,
            reassigned every convergence pass by `SystemBCIteration`); a
            handful of subclass-specific plain-float "derived, recomputed
            each call" fields that are NOT `LockedState`-wrapped —
            `NumericalWell.cell_length`/`relative_roughness`/
            `cross_sectional_area`/`t_scaling_factor`/`T_r`/`t_d_old` (set
            by `init()`, `t_d_old` also reassigned every `solve()`) and
            `LumpedReservoir.T_initial`/`rock_volume`/`rock_C_v`/`p1`/`p2`/
            `p3`/`energy_extracted` (reassigned by
            `_recompute_depletion_coeffs()`/`solve()` every timestep).
          Verified safe by grepping the whole `src/tango_next/` tree for
          direct reassignment of every frozen-candidate field name before
          touching anything — the only hits were `inlet`/`outlet`/
          `injection_pressure`/`save_interval` (comparison, not assignment)
          and the orchestrator's own unrelated `dt_years` attribute. Added
          `test_frozen_component_config_rejects_runtime_mutation`
          (`tests/regtest/test_tango_next.py`) alongside the existing
          `test_frozen_common_rejects_runtime_mutation`. Full
          `tests/regtest`+`tests/unit` suite green (36 passed, 1 xfailed);
          `mypy src/`, `ruff check`, `ruff format --check` all clean;
          `examples/tango_next/sweep_demo_AGS_direct_heat.py` re-run and
          confirmed byte-identical output to before this change.
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

- **DONE 2026-08 — `mark_all_stale()` cascaded from the orchestrator, not
  called by each component locally.** Previously every component's
  `solve()` called `self.state.mark_all_stale()` as its own first line
  (`core/locked_state.py`'s docstring even shrugged that either "the
  orchestrator (or the component itself)" could do it). Replaced with one
  generic `Component.mark_all_stale()` (walks the component's own
  attributes for anything exposing `mark_all_stale()`, today just `state`)
  that the orchestrator now calls immediately before every `solve()`
  invocation — all 4 call sites across `system_direct.py` and
  `system_bc_iteration.py`'s BC-convergence loop. Exposed a real ordering
  bug: `LumpedReservoir.solve()` read its own previous-timestep outlet via
  `get_fresh()` as its first action, relying on `mark_all_stale()`
  happening later in the same call — fixed to use `get_stale()`, the
  canonical `LockedState` pattern for this. Two unit tests updated
  (`test_serde_roundtrip.py`) that called `.solve()` directly more than
  once without an intervening `mark_all_stale()` — now a documented part
  of `Component`'s calling contract.
- **DONE 2026-08 — Reservoir no longer frozen during injection-temperature
  convergence.** `SystemBCIteration._converge_injection_T` used to skip
  the reservoir's `solve()` entirely for the whole T-convergence inner
  loop (its outlet cached and replayed unchanged), only re-solving it once
  afterward ("Pass 2"). Traced the actual single-flash surface topology
  (`flexible_SF_manual.yml`) and confirmed this was physically wrong: the
  condenser branch's own outlet *state* (T/P/enthalpy) is a hard pinned
  BC, but the mass flow through it isn't — the separator's flash fraction
  depends on the actual wellhead-fed inlet enthalpy, so both branches
  carry wellhead effects into the merge (the liquid branch through its
  state, the condenser branch through its mass weight) — freezing
  the reservoir was producing a self-inconsistent answer, not just an
  approximation. Also verified against old tango's actual convergence
  loop (`BC_calculator.py::FlowRateCalculator.iterator()`, confirmed live
  via `SystemExternal`) that it re-solves the reservoir every outer
  iteration, not twice.

  Replaced with a generic snapshot/restore mechanism
  (`Component.snapshot_convergence_state()`/`restore_convergence_state()`,
  scoped to non-frozen fields excluding `inlet`/`outlet`/`state`/
  `history`) used uniformly by every component in the circuit, reservoir
  included — restored fresh before every iteration. Collapses the old
  main-pass/T-loop/Pass-2 structure into one uniform loop with no
  special-casing. See the annotated diagram published this session for
  the full mechanism (linked from the warning box added to
  `docs/diagrams/src/tango_next/hydro_double_flash_electric_exec_flow.drawio`,
  since that diagram's T-convergence section now describes the old
  mechanism).

  Regenerated the golden snapshot for `flexible_SF_manual.yml` (genuine
  physics change) and re-measured old-vs-new agreement: tightened as
  expected (reservoir T max delta 0.214→0.172 K, prod T 0.190→0.160 K,
  gross power 0.36%→0.26%) but didn't vanish — old tango's loop also
  converges injection *pressure* together with temperature, which
  tango_next's `MANUAL` policy still treats as a fixed given (see "Open
  Design Questions" → extraction pressure note in the vision doc for the
  related, still-open policy question).
- **DONE 2026-08-03 — T-convergence explainer pulled into the TANGO docs
  proper.** The mechanism (reservoir/production-well/surface-plant
  circuit, the snapshot/restore convergence loop, why the reservoir must
  be re-solved every iteration) previously only existed as a Claude
  Artifact page. Now checked into the repo: `docs/tango_next_t_convergence.md`
  (renders natively on GitLab, embeds two SVGs via standard markdown image
  syntax), backed by an editable `.drawio` source
  (`docs/diagrams/src/tango_next/t_convergence.drawio`, two pages —
  "Circuit" and "Convergence loop") with matching exported SVGs under
  `docs/diagrams/img/tango_next/`. The warning box in
  `hydro_double_flash_electric_exec_flow.drawio` now points at the new doc
  instead of the Artifact URL. Embeds PNG, not SVG (GitLab refuses to
  render locally-hosted SVGs inline for security reasons and falls back to
  a plain link) — the markdown doc's `.png`s and the checked-in `.svg`s
  are both true draw.io CLI exports of the `.drawio` source
  (`/Applications/draw.io.app/Contents/MacOS/draw.io --export --format
  {svg,png} --page-index N`, 1-indexed), not hand-authored, so re-running
  that export after any `.drawio` edit keeps all three in sync — don't
  hand-edit the `.svg`/`.png` files directly.
- **DONE 2026-07-27 — TODOs in `applications/run_AGS_direct_heat_sweep/sweep.py`
  resolved.** Traced the DH heat exchanger's `T_out` and confirmed it's a hard
  TESPy connection constraint (not an effectiveness/NTU model), so the live
  `surf_unit.outlet_fluid.T` read is always exactly correct given a converged
  solve — kept as the live read (self-verifying) rather than hardcoding the
  `DH_RETURN_TEMP_K` fallback, with the reasoning documented in both
  `sweep.py` and `triemli_dh_base.yml`. Same day: dropped the poorly-provenanced
  707 m loop-length value and extended that axis to 8 km to match well depth's
  max, mirrored into `applications/tango_next/run_AGS_direct_heat_sweep/common.py`'s
  matching axis.
- **DONE 2026-07-29 — DVC pipeline + `--clean` flag + SLURM sbatch script
  added to every sweep app.** All 7 apps (`run_AGS_direct_heat_sweep`,
  `run_AGS_sweep`, `run_EGS_direct_heat_sweep`, `run_flexible_DF_manual_sweep`,
  and the three `tango_next/` ports) now have: a `dvc.yaml` mirroring the DF
  app's stage structure (generate → sweep → clean → summarize[→ plot], one
  pipeline per app directory, not a unified cross-app pipeline); a `--clean`
  CLI flag on the orchestrator script (`clean_sweep_dir()` in `common.py`
  empties the sweep dir except `.gitignore` — deliberately not tracking
  individual filenames, since those drift as `summarize.py`/`plot.py` change);
  and a single-node SLURM `sbatch` job script mirroring
  `run_flexible_DF_manual_sweep_job.sh`'s existing pattern (n_workers derived
  from `$SLURM_CPUS_PER_TASK`, written into `params.yaml`, then `dvc repro`).
  Multi-node array sharding was explicitly descoped (Chad's call,
  2026-07-29) — single-node only for now. Also added `print_dt()` (alias for
  the pre-existing `print_datetime()` in `src/tango/utils.py`) to the start
  of every orchestrator's `__main__` block, so SLURM job logs show actual
  run-start wall-clock time (queue wait time isn't otherwise visible in the
  log).
  Of the three open design questions from the original discussion, only the
  first was actually resolved by this pass; the other two are still open
  and deliberately deferred, not silently dropped:
  1. **RESOLVED — `outputs/results` is tracked as a whole DVC `out`
     directory in every app**, matching the DF precedent, for consistency
     across all 7 apps. Simpler than a two-tier (aggregate-only +
     per-design-scratch) scheme, at the cost of slower `dvc repro`/`dvc
     status` on the larger grid sweeps (AGS direct-heat's 12,870-design
     grid) — acceptable for now, revisit if that becomes a real bottleneck.
  2. **STILL OPEN — `src/tango_next` isn't tracked as a dependency, and that matters more
     here than it did for old tango.** The DF app's `dvc.yaml` has a comment
     explicitly waving this off as "burdensome to hash" — a reasonable
     tradeoff for old tango, which is stable. `tango_next` is not: this
     week alone, `LumpedReservoir.solve()` and `GraphSurface.init()` both
     changed in ways that silently change sweep output for anything using
     them (see "Resolved Design Decisions"/this file's AGS sweep parity
     section above). Without `src/tango_next` as a dependency, DVC can't
     catch an engine-level regression the way a pipeline like this is
     supposed to. Consider a lighter-weight proxy (a params entry pinning
     the current git commit hash of `src/tango_next`, or depending on just
     the specific subpackages actually touched — `components/`,
     `orchestrators/`, `workflows/`) rather than either ignoring it
     (matches old tango's tradeoff, but riskier here) or hashing the whole
     tree every run.
  3. **STILL OPEN — no standardized metrics output across the three completed ports yet.**
     The double-flash port's `summarize.py` writes a real `summary.yaml`
     (mean/std/percentiles) DVC could track as a `metrics:` output; the
     AGS/EGS direct-heat ports only print pivot tables and write CSVs — no
     single YAML/JSON summary to diff across commits. Decide whether all
     three (four, eventually) should get a consistent small metrics file
     (success/fail counts, thermal-power percentiles, count meeting the
     105 degC threshold, etc.) before wiring in `dvc metrics diff`.
- **DONE 2026-07-30 — thorough review of how subsurface and surface
  components are told what fluid is being passed around, both risks
  confirmed real and fixed.** Flagged earlier the same day as a quick pass;
  a full read of every call site confirmed both concrete risks were
  genuine, not just theoretical:
  1. **Confirmed**: `components/reservoir/lumped.py`, both lumped wells
     (`well/lumped.py`), and `GraphSurface`'s pipe-hydraulics
     (`surface/graph.py`) all called `fluid_utils.water_density`/
     `water_viscosity`/`water_enthalpy`/`water_cp`, which were hardcoded
     against a single module-level `CoolProp.AbstractState("HEOS", "Water")`
     — none of them took a fluid name argument at all. A non-water
     `common.fluid_name` (e.g. an EGS/CO2 design) would silently compute
     every physical property as if it were water.
  2. **Confirmed**: the inlet→outlet `fluid_name` copy-through was
     byte-identical in every component, plus a second orchestrator-level
     copy in `SystemDirect._wire_one_stream`/`SystemBCIteration` — two
     redundant layers of the same fact, both unvalidated, both drift-prone,
     neither ever actually needed since every fluid-consuming component
     already holds a reference to the Workflow's single shared `Common`
     instance (`core/specs.py`).
  Also found, not previously flagged: `GraphSurface.solve()` passed TESPy a
  genuine `fluid={name: 1}` dict (so TESPy really did solve with the
  declared fluid's own EOS) while the pipe-friction calc wrapping it used
  the hardcoded-water `fluid_utils` calls regardless — two different
  property backends for nominally the same fluid, no cross-check between
  them.

  **Fix landed** (no mixture/brine support added — not needed by either
  risk above, and Chad's ask was specifically "same substance across a flow
  path," not composition modeling):
  1. `core/fluid_utils.py`'s `water_density`/`water_viscosity`/
     `water_enthalpy`/`water_cp` renamed to `fluid_density`/
     `fluid_viscosity`/`fluid_enthalpy`/`fluid_cp`, each now taking
     `fluid_name` explicitly and delegating to `FluidState.with_PT`
     (`core/fluid_state.py` — the same CoolProp wrapper the numerical well
     already used correctly). Added a `cp` property to `FluidState` so it
     covers all four. Every call site (`reservoir/lumped.py`,
     `well/lumped.py` ×3, `surface/graph.py`) now passes
     `self.common.fluid_name` — real per-fluid physics everywhere, not just
     in the numerical well.
  2. **`Stream.fluid_name` removed entirely** (`core/stream.py`) — it was
     genuinely redundant: every component that needs fluid identity already
     has `self.common` (the shared, frozen `Common` instance). Removed the
     inlet→outlet copy in every component's `solve()`
     (`well/lumped.py` ×3, `reservoir/lumped.py`, `surface/graph.py`,
     `well/numerical.py`) and the orchestrator-level copy
     (`SystemDirect._wire_one_stream`, `SystemBCIteration`'s
     `fluid_name` param/attribute and its stream-seeding assignments).
     `GraphSurface`'s TESPy `fluid={...}` dict now reads
     `self.common.fluid_name` instead of `self.inlet.fluid_name`.
  3. **One-time structural guarantee, not a per-timestep check**: added
     `_check_common_identity()` (`workflows/workflow.py`), called once from
     `Workflow.__init__` right after `_build_components`. Asserts (via `is`,
     not `==`) that every component's `common` attribute, if it declares
     one, is the literal same object as the Workflow's canonical `Common` —
     catching a future construction bug (a code path that accidentally
     builds a second, equal-but-separate `Common`) at Workflow-build time
     instead of letting it silently diverge later. This can't currently
     fail under `_build_components`'s existing behavior (it already only
     ever hands out one shared reference) — it's a guard against
     regression, not a fix for an existing gap in that function. Documented
     in `Workflow`'s class docstring as the mechanism that makes fluid
     identity (and rock/thermal params) consistent across a flow path
     without needing `Stream` to carry or re-verify anything after
     construction. Left an explicit comment (not speculative code) noting
     that a genuine future fluid-*boundary* component (e.g. a secondary/ORC
     loop) would need its own separate identity, not a relaxation of this
     check.
  Verified: `ruff check`/`mypy src/tango_next` clean; full `tests/unit` +
  `tests/regtest` suite green (updated the handful of
  `Stream(..., fluid_name="water")` test constructions in
  `test_serde_roundtrip.py`/`test_tango_next.py` — `Common.fluid_name`
  itself is untouched and still tested).
  Not done (deliberately out of scope, not asked for): mixture/brine/
  composition support, or a typed `Fluid` object beyond the existing bare
  `Common.fluid_name` string — neither risk above needed it, and adding it
  now would be speculative.
- **IN PROGRESS (~halfway, as of 2026-07-31) — Line-by-line debugger
  walkthrough of one `tango_next` single-simulation case.** Originally scoped
  against `examples/tango_next/flexible_SF_manual.yml` (the original
  reference example used throughout tango_next's design/porting work —
  simplest well-understood topology); in practice picked up against
  `hydro_double_flash_electric` instead, using
  `docs/diagrams/src/tango_next/hydro_double_flash_electric_exec_flow.drawio`
  as the map (built/corrected 2026-07-31 — fixed a mislabeled external-call
  node and added the previously-missing `Workflow.__init__` entry node).
  Goal: step through the full execution flow (`Workflow` →
  `Orchestrator`/`SystemBCIteration` → component `solve()` calls) with a
  real debugger for one config, to build or verify a concrete mental model
  of the current call graph. Chad did roughly half of the walkthrough
  himself — needs to be picked back up and finished, not restarted.
  **CAUTION (2026-08): the diagram's T-convergence/BC-iteration section is
  now stale** — `SystemBCIteration._converge_injection_T` was rewritten
  (reservoir no longer frozen/skipped during the inner loop; the old
  `t_d_old_saved`/`energy_before`/"Pass 2" mechanism replaced by a generic
  `Component.snapshot_convergence_state()`/`restore_convergence_state()`
  used uniformly by every component). A prominent warning box was added to
  the `.drawio` file marking exactly which nodes are affected, and a fresh
  annotated diagram of the *new* mechanism was published separately
  (see this session's artifact link in the `.drawio` warning box).
  **TODO, blocking further walkthrough progress: re-trace the
  T-convergence/BC-iteration section of
  `hydro_double_flash_electric_exec_flow.drawio` against the current
  `_converge_injection_T` (snapshot/restore, reservoir included, no more
  Pass 2) before continuing the debugger walkthrough past that point** —
  don't debug against the old nodes as if they still match
  `system_bc_iteration.py`.
- **Holistic repo-wide consistency/cruft review** — flagged 2026-07-24, not
  started. Chad wants a pass across the whole repo (not scoped to
  `tango_next`) to flag anything "wacky or inconsistent," explicitly
  including `examples/`/`applications/`/`tests/` that are overly
  duplicative and could be consolidated. Candidates worth checking when
  this starts (not yet verified, just things noticed in passing this
  session): the four near-identical `applications/run_*_sweep/` directories
  (`run_AGS_direct_heat_sweep`, `run_AGS_sweep`, `run_EGS_direct_heat_sweep`,
  `run_flexible_DF_manual_sweep`) each carry their own
  generate/sweep/summarize/plot scripts — worth checking how much is
  copy-pasted vs. genuinely different per site/product; `src/tango/`
  (old) vs. `src/tango_next/` (new) dual-maintenance surface generally.
  This is a big, open-ended audit — scope it explicitly before starting
  rather than diving in ad hoc.
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
