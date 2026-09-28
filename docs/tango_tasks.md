# tango granular task tracker

Working-level task list for `tango` porting/parity work. This is the
detailed, frequently-updated companion to `docs/TANGO_vision_and_roadmap/README.md`
— reconcile the two periodically (when a section here is fully done, fold a
one-line summary into the vision doc's Phase 3 task list and prune the
detail from here). The vision doc is the durable, Confluence-bound
narrative; this file is scratch-adjacent but checked in, for tracking
in-flight multi-step work across sessions.

**Migration to GitLab issues in progress (started 2026-09-25, see issue
#45 for the plan/decisions).** Open items are being ported to GitLab
issues one at a time; each migrated bullet's body is replaced with a
one-line pointer to its issue, in place, rather than deleted outright. The
"Completed Tasks" archive below is NOT being migrated — it stays here.

- See issue [#47](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/issues/47) — generate documentation and host on github.com.
- See issue [#48](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/issues/48) — `GraphSurface.net_power_W`'s name overclaims its scope.
- ~~**SUPER HIGH PRIORITY, added 2026-09-23 — `CPG_electric.yml`'s `LCOE` is
  `NaN`.**~~ — **resolved 2026-09-23.** Found while building full-length
  regression coverage for every `example_configs/` YAML
  (`tests/regtest/test_example_configs.py`).
  `DoubletEconomicComponent._compute_lcoe` intentionally returns NaN when
  its OWN `net_power_W` (the CAPEX-formula input, distinct from the
  surface plant's own always-positive `net_power_W` history) is `<= 0` —
  and for CPG that came out to ~-368 kW. Root cause: `_read_net_power`
  subtracts a cooling-tower parasitic-power term
  (`_cooling_condenser_parasitic_power`) from the surface's net output —
  CPG's condenser sets `cooling_tower_mode: DRY`, giving a parasitic
  fraction (~8.8% of the condenser's heat-rejection duty) that exceeded
  CPG's own average net turbine output (~1.63 MW parasitic vs. ~1.26 MW
  net). Confirmed this isn't a broken formula in general — the same
  calculation applied to `hydro_sf_electric.yml` (known-good) gives a
  sane ~19% of net power, not dominant, because single-flash only
  condenses its small flash-split vapor fraction, not the entire flow the
  way CPG's direct-expansion design does. The actual bug: `DRY` was never
  grounded in what old tango's `CPG_num_pp.yml` actually used — that file
  never overrides `cooling_mode`, so it gets `SurfaceSpecsCPGNative`'s own
  `"WET"` default. Switching CPG_electric.yml to `cooling_tower_mode: WET`
  (matching old tango) drops the parasitic power to ~497 kW, net goes
  positive (~764 kW), LCOE = 0.4298 (sane, finite) — verified directly,
  not guessed. `test_example_configs.py`'s CPG entry now has this real
  reference value instead of an asserted NaN.
  - ~~**Separate, NOT resolved, worth a follow-up**: `_bac_regression`'s
    ambient-temperature units~~ — **investigated and closed 2026-09-24,
    no code change needed.** Old tango's own `_BAC_regression_model`
    docstring claims its ambient-temperature term should be in °C, but
    old tango's actual call site passes the same Kelvin-valued
    `surface_temperature` straight through too — checked old tango's
    real YAML/code, not just its docstring. No recoverable original
    source for these coefficients exists to settle which convention was
    truly intended (old tango's own git history has no citation beyond
    "derived from Baltimore Aircoil (BAC) regression models," going back
    to its first commit). Since old tango's real (not documented)
    behavior is Kelvin, and a direct new-tango-vs-old-tango net-power
    comparison for CPG (same depth/mass rate/duration) came out within
    ~3.6-10% either way, changing tango's units now would only make it
    diverge from old tango's verified-correct behavior over a docstring
    neither codebase's implementation actually honors. `_bac_regression`'s
    own docstring in `doublet.py` now documents this explicitly so it
    doesn't get "fixed" into a regression later.
- See issue [#49](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/issues/49) — include GeoProp in TANGO.
- **KNOWN, LOW PRIORITY, NOT PURSUED FURTHER (2026-09-17) — `test_native.py`'s
  `flexible_SF_doublet.yml` LCOE golden is stale.** Found while investigating
  a merge (`dev/aitkens-process` <-> `dev/make-tango-robust`): expected
  `0.4925022354672546`, currently computes `0.6691340...` (~36% off) for
  old tango's own (`src/tango/`) run of this DOUBLET+SingleFlash example —
  a real, reproducible mismatch, confirmed on `dev/make-tango-robust`'s own
  tip in isolation (no `dev/aitkens-process` code involved at all). Not
  caused by the merge, not caused by the intern's WellPattern/depletion-
  curve work (traced both of those — `wellpattern_impedance.py` and the
  `C=1.13` revert — and confirmed neither ever touches `src/tango/`).
  Root cause NOT pinned down: a `git worktree`-based bisection across the
  ~73 candidate commits (touching `src/tango/units/native/reservoir.py`/
  `economic/`/`well/`/`surface/`, `orchestrators/`, `utils.py`) stalled
  (likely an old commit's run hanging on an ArangoDB write attempt with no
  reachable server, rather than failing fast) and was abandoned as not
  worth the effort for a stale reference on legacy `src/tango/` code that
  isn't under active development.
  **Why this was invisible:** `test_native.py` is marked `old_tango`;
  both the pre-push hook (`.pre-commit-config.yaml`'s `pytest` hook:
  `-m "not perf and not old_tango and not slow"`) and CI (`.gitlab-ci.yml`'s
  `test` job: `uv run pytest tests/unit -v`, which doesn't even reach
  `tests/regtest/`) deliberately skip it — by design, not
  misconfiguration, on the assumption someone runs `-m old_tango` by hand
  when old tango itself changes. Nobody has, for however long this has
  actually been stale. Revisit only if old tango needs to be trusted as a
  reference again for something specific; otherwise leave as-is.

- See issue [#50](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/issues/50) — build phase-diagram (P-h/T-s) visuals for tango fluid states.

- ~~**Added 2026-09-17**: add functionality to copy demos/examples/applications to
  working directories of where tango is a dep~~ — **DONE 2026-09-25**:
  `tango_cli init` now copies `example_configs/` and every
  `applications/` pipeline into DEST by default (`--app` narrows to
  specific apps, `--no-apps` skips applications entirely). Also fixed the
  related bug where re-running `init --app X` after a plain `init` failed
  outright because `example_configs/` already existed.

- ~~**Added 2026-09-17**: check the correctness of the Adams et al. (2015)
  transient conductive heat-loss reference used by `NumericalWell`~~ —
  **resolved 2026-09-21**: it was mislabeled, not incorrect. The formula
  itself matches the actual paper — but that paper is Zhang, Pan, Pruess,
  & Finsterle (2011), Geothermics 40:261-266
  ([DOI](https://doi.org/10.1016/j.geothermics.2011.08.003), verified
  directly against Crossref metadata), not Adams et al. (2015) at all.
  `core/fluid_utils.py`'s docstring already cited Zhang correctly (fixed
  in an earlier commit), but the function itself was still named
  `heat_loss_adams_2015` — renamed to `heat_loss_zhang_2011`
  (`HeatTransferModel.ADAMS_2015`/`"adams-2015"` → `ZHANG_2011`/
  `"zhang-2011"` too) across `fluid_utils.py`, `constants.py`,
  `physics_models.py`, `components/well/numerical.py`,
  `components/well/lumped.py`, and `example_configs/AGS_direct_heat.yml`.
  While auditing this, also found and fixed a separate, unrelated wrong
  citation: `wellpattern_impedance.py`'s doublet/5-spot impedance formula
  was attributed to "Adams et al. (2020)" but is actually Birdsell et al.
  (2024), Geothermics 116:102843 — Adams is the second author, not first,
  and the DOI's own "2023" is the online-first year, not 2020.

- See issue [#51](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/issues/51) — decide how surface-component cost sizing is calculated relative to time.

- See issue [#52](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/issues/52) — support production well operation with no pump (e.g. Larderello).
- See issue [#53](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/issues/53) — handle non-condensable gases in subsurface fluids.

- See issue [#54](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/issues/54) — build examples/tutorials demonstrating LCOE/power tradeoffs across system types.

- See **Completed Tasks → From the top-level list** for the outer-circuit
  `component_idx`/`prev`/`next` vs. tespy-style `edges` question (flagged
  2026-09-09, decided 2026-09-17: keep as-is) and the `LumpedReservoir`
  initial-pressure bootstrap fix (DONE 2026-08-04) and the production-well
  pump-power formula fix (DONE 2026-08-10).
- See issue [#55](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/issues/55) — re-architect the production-well pump boost as a Secant-converged iteration over segment inlet pressure.
- See **Completed Tasks → From the top-level list** for
  `pymoo_api.Minimization` saving the front every generation
  (DONE 2026-08-11) and the superseded stop/resume work for
  `Minimization.run()`.

## Next session priorities (set 2026-09-16)

Goal: get through all of this in the next session (2026-09-17).

- [x] **Release plan for `tango` as an internal release, GEG team members
      only** (not the open-source packaging question tracked elsewhere —
      this is the internal-distribution plan for the group itself).
      **Done 2026-09-18**, pending Chad's commit.
  - [x] remove all old tango artifacts, remove parity tests, and move
        `src/tango_next/` to `src/tango/` (plus the matching
        `examples/tango_next/` → `example_configs/`,
        `applications/tango_next/*` → `applications/*`, and doc renames).
  - [x] A notice that ships with the installed package making clear the
        code is not to be redistributed outside authorized users (GEG
        group members). — `NOTICE`.
  - [x] A closed-source license file, distributed alongside the code. —
        `LICENSE.txt` rewritten (was a leftover MIT license from the
        pre-fork history).
  - [x] A way to install specific versions — e.g. GitLab tags matching
        `version = "0.0.1"` in `pyproject.toml`. — documented in
        `CONTRIBUTING.md`'s "Cutting an Internal (GEG-only) Release"
        section (`v`-prefixed tags, matching the existing tag convention).
  - [x] Instructions for creating the environment via cookiecutter (see
        https://gitlab.ethz.ch/geg/templates/python-template,
        `/Users/cb/git/templates/python-template` locally), then adding
        `tango` from GitLab via `uv add ...`. — `CONTRIBUTING.md`'s
        "Installing `tango-core` in another project" section (package
        renamed from `tango` to `tango-core` for distribution purposes —
        `import tango` is unaffected).
  - [x] `CONTRIBUTING.md` documents the process for cutting a new internal
        (GEG-only) release, so this isn't tribal knowledge — covers
        versioning/tagging (see the GitLab-tags item above) and whatever
        steps actually publish the release once this plan is implemented.
  - **Follow-ups surfaced while doing this — done (2026-09-18):**
    - `docs/TANGO_vision_and_roadmap/README.md`'s ~5 stale illustrative
      mentions of the now-deleted `test_old_new_parity.py` — fixed (mix of
      "historical record now" rewording and one restored-to-contemporaneous-
      name citation for the actual 2026-07-16 CI job it referenced).
    - `tango_flask_server.py` — deleted outright by Chad (legacy, to be
      superseded when the web-app frontend work resumes from a clean
      slate). The `tango-app` optional-dependency group
      (flask/flask-cors/gunicorn) and the pixi `pyqt` feature it and the
      old addons were the only consumers of are removed from
      `pyproject.toml` too — nothing currently depends on either.
    - `tools/sweep_examples.py` deleted — it drove old-tango-format
      `examples/*.yml` configs through the `tango_cli` console script,
      which now means the new engine post-rename; every run would fail on
      the format mismatch alone, not a real regression. Its `.gitignore`
      stanza, plus a second dead stanza for `optimizerr.py`/`ThermaGraph`/
      `BatchSimulation` runtime artifacts (all three sources deleted),
      removed too.
    - The entire `examples/` directory deleted (historical/reference
      old-tango-format configs — `AGS_new/`, `EGC2025/`, `EGC2025_EGS/`,
      `Martin_AGS/`, `MOOSE input files/`, `MOOSE_Tespy examples/`,
      `MVP_templates/`, `TANGO_paper/`, `failing/`, plus ~90 loose files —
      none of it runnable against the current engine anyway, and nothing
      in the live codebase referenced most of it). `data/`'s 4
      `ORC_Tboil_optimum_*.csv` files went too (zero references anywhere;
      `PPI_Table.xlsx`/`cost_multiplier_table.xlsx` were kept — cited as
      live provenance in `core/economic_constants.py`). Everything
      removed is permanently reachable at git tag
      `pre-tango-core-rename-2026-09-18` — that tag is the bookmark for
      old tango and its historical example set going forward, so don't
      re-add any of it to the working tree. Elsewhere in this file, any
      mention of a path under `examples/` (as opposed to
      `example_configs/`) refers to that pre-removal state — check the tag
      if you need the actual file.
  - **Follow-ups surfaced while doing this, still open:**
    - 6 `dvc.lock` files got their stale `tango_next` path text fixed by
      hand, but weren't regenerated — worth a `dvc status` sanity check
      (or an actual `dvc repro`, which is a real, possibly-expensive run —
      hasn't been done).
    - ~~`justfile`'s `demos` recipe lost smoke coverage...~~ — **done
      2026-09-18**: all 5 previously-uncovered apps
      (`demo_well_mesh_convergence`, the 3 `run_*_sweep` apps' `--smoke`,
      `opt_hydro_df_electric_surrogate`'s 4-stage chain) wired in and
      verified end-to-end via a real `just demos` run. Found and fixed 2
      real bugs along the way (see the merge-commit message on
      `dev/make-tango-robust`: `surface.outlet.T` needing `.get_fresh()`,
      `check_well_spacing`'s 5000-vs-50000 range bug).
    - ~~Purge remaining old-tango-as-rationale mentions from docstrings/
      comments~~ — **done 2026-09-18.** Rewrote every bare `src/tango/`
      claim (misleading, not just stale — since the rename, that path
      means the *current* package) into explicit "old tango, removed;
      preserved at git tag pre-tango-core-rename-2026-09-18" framing,
      across all the files below plus the 3 new `example_configs/
      hydro_sf_electric_{5spot,autoflow,autopressure}.yml` the merge
      added (same trivial pattern, just not on the original list since
      they arrived after it was written). Historical-fact-style "matches
      old tango's X" mentions that don't claim old tango still exists
      were deliberately left as-is throughout — the goal was removing
      dangling/misleading references, not purging every mention of old
      tango's existence. Bonus find along the way: two comments in
      `doublet.py`/`policies.py` cited `project_economic_model_wackiness`/
      `project_src_tango_gotchas` "memory" — these are Claude's own
      private memory file names, not anything in this repo; meaningless
      to anyone (including a future session) without that exact memory
      loaded. Replaced with real citations (this module's own docstring,
      `docs/bugs-fixed-in-tango.md`) or inlined substance. Full list of
      what was touched, preserved as a record:
      - `example_configs/EGS_direct_heat.yml` (known simplification vs.
        old tango's `max_mass_rate` cap), `hydro_orc_electric.yml` (dropped
        cost-metadata attributes; the manual-vs-manual-fracking-check
        numeric-margin rationale).
      - `src/tango/orchestrators/system_bc_iteration.py`,
        `components/economic/doublet.py`, `core/policies.py` — the three
        with the most substantive old-tango-anchored explanations
        (deliberate deviations, behavioral parity notes, field-mapping
        tables).
      - Also touched: `components/reservoir/{base,lumped}.py`,
        `components/surface/graph.py`, `components/well/numerical.py`,
        `core/{constants,economic_constants,fluid_state,fluid_utils,
        physics_models,specs}.py`, `workflows/workflow.py`.
      - Also: `applications/run_AGS_direct_heat_sweep/run_AGS_direct_heat_sweep.py`,
        `run_EGS_direct_heat_sweep.py`, `run_hydro_df_electric_sweep.py`
        each describe themselves as "the tango port of
        `applications/run_*_sweep/`" — accurate before the flatten, now a
        self-reference since both old and new collapsed onto the same path.
      - **New, unrelated to the purge itself — found while fixing
        `components/well/numerical.py`'s stale `src/tango/` references
        (2026-09-18):** that module's docstring documents a "known
        simplification" that `t_d` (dimensionless time) only advances
        correctly when `solve()` is called exactly once per timestep —
        true "today" only because `InjectionPolicy.MANUAL` was the only
        mode implemented. `AUTO_PRESSURE`/`AUTO_FLOW`/`AUTO_BOTH` (all of
        which add multi-pass outer loops) are now implemented via the
        Aitken-process merge, and this simplification's premise was never
        re-checked against them — genuinely worth verifying `t_d` still
        advances correctly under multi-pass convergence, not just
        assuming it does because nothing has crashed yet.
      - **Also new, found the same way, in `core/constants.py`:**
        `GRAVITY = 9.81` was deliberately rounded to match old tango's
        value "for parity comparison purposes," with an explicit TODO to
        revert to the more precise NIST/ISO 80000-3 value (9.80665) "once
        old-tango parity is no longer the active concern." That condition
        is now literally true. Not changed as part of this purge — it's a
        one-line change but would shift every existing golden/reference
        value (e.g. `test_example_configs.py`'s golden LCOE values) by a
        tiny amount, so it's Chad's call, not a docstring-cleanup call.
      - Careful: some `src/tango/` mentions in these files are NOT stale —
        e.g. `example_configs/hydro_df_electric.yml`'s
        "`src/tango/components/economic/doublet.py`" is a self-reference
        to the *current* file, not old tango. Triage each one; don't
        blind-strip.
    - **Third-party dependency license compliance tooling needs
      modernizing** (`tools/check_licenses.py` +
      `tools/conda_and_pip_package_licenses.csv`, discovered while
      confirming closed-source licensing didn't conflict with any
      dependency's own license). Currently: a manual-only script, not
      wired into anything, dumping a 5,475-row CSV (full pip+conda
      transitive closure) that's already stale (last generated 2026-08-11).
      Chad wants:
      - A more human-readable output format than CSV (undecided — CSV
        felt too rigid for this).
      - Wired into `just` (a recipe, not just a standalone script).
      - Enforced via pre-commit and/or GitLab CI, not purely manual.
      - A red/yellow/green judgment per dependency based on license type
        (red = must remove, yellow = needs human review, green = fine) —
        beyond the current binary allowed/violation check.
      - See also (from `TODO.md`, folded in below): "fix and beef up
        license manager" cited
        https://gitlab.ethz.ch/geg/computing-guide/-/wikis/Understanding-Software-Licenses
        as a starting reference.

## Carried over from `TODO.md` (folded in 2026-09-18)

`TODO.md` predated this file and mixed genuinely-open ideas with items that
were already done or specific to old tango (now deleted, so moot). Only the
still-relevant, not-yet-covered-elsewhere items survive here; `TODO.md`
itself is deleted (preserved at git tag `pre-tango-core-rename-2026-09-18`
if the full original is ever needed — most of what's not here was either
already implemented in `tango` — LockedState, state/history split,
mypy/eval/circular-import cleanup, unit-suffix naming, absolute-path
removal, etc., all now CONTRIBUTING.md rules or shipped design — or
specific to deleted old-tango files/apps).

- **Graph Network Architecture — compact node+edge format.** Still
  genuinely open: `GraphSurface` YAML today keeps `nodes` and `edges` as
  separate sections (see any `example_configs/*.yml`'s `power_plant`
  block). The original idea was to merge them, each node carrying its own
  `connects_to`:
  ```yaml
  power_plant_graph:
    inlet:
      type: Source
      connects_to: valve1
    valve1:
      type: Valve
      p_out: 1
      connects_to: droplet_separator1
    droplet_separator1:
      type: DropletSeparator
      connects_to:
        out1: valve2
        out2: turbine1
  ```
  Benefits: merges component config with graph structure, eliminates
  redundant per-component sections, multi-port components use a dict for
  `connects_to`. See also
  [ALTRIOS's rail network representation](https://github.com/NatLabRockies/altrios/blob/main/python/altrios/resources/networks/Taconite.yaml)
  for another take on a self-contained graph format.
- **Restore/update `GUIDELINES.md`.** Doesn't exist in this repo at all
  currently (not even a stale copy) — the original TODO pointed at
  `https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/blob/main/GUIDELINES.md`,
  a different repo/branch. Needs Chad to say what should actually be in
  it before this is actionable.
- **Error handling and solver robustness:** run massive LHS parameter
  sweeps on Euler across `tango` simulations to find (a) parameter sets
  that cause errors that need better/more specific error handling, and
  (b) parameter sets that cause errors the solver should actually be able
  to handle (i.e. real bugs, not just bad inputs) — then use those
  findings to actually fix things. Ties directly to Chad's error-handling
  philosophy (rigorous typed error handling as a core design element, not
  an afterthought).
- **Agentic TANGO (backlog, lower priority):** use the same kind of
  massive LHS sweep data to train/prompt an LLM agent to (a) set up
  `tango` runs from a natural-language description, (b) interpret
  results of successful runs, (c) troubleshoot failed runs.
- **Physics: verify the turbulent-flow assumption.** Wellbore flow and
  heat-transfer calculations assume turbulent flow throughout
  (`core/physics_models.py`, `core/fluid_utils.py`). Nothing currently
  checks Reynolds number to confirm that assumption holds across the
  parameter ranges `tango` actually runs — worth checking `Re` and
  adjusting the friction-factor/heat-transfer correlations if it doesn't.
- **Foundational: standalone submodule execution.** Ability to copy and
  run any single submodule/component out of an existing `tango`
  simulation in isolation, for richer error context and troubleshooting
  (e.g. "just re-run this one well's solve with these exact inputs and
  see what happens"). Not designed yet; `LockedState`'s
  snapshot/restore-per-timestep mechanism may make this more tractable
  now than it would have been in old tango.

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
   guess blank entirely and let tango pick one — consistent with the
   idea floated earlier this session that ~65% of the way from reservoir
   temperature to ambient is a good default starting guess. When the pivot
   fires (retrying with a lower guess after a bad-guess solver failure),
   don't fail silently — log a `WARNING` (or similar) so it's visible that
   an automatic correction happened, even though it's not an error.
   Implementation lives in `SystemBCIteration._converge_injection_T` /
   `run_timestep`'s `MANUAL` branch (`orchestrators/system_bc_iteration.py`).

   Additional items folded into this same area of work, agreed 2026-08-04
   (two of them DONE — see **Completed Tasks → From "Next session
   priorities"**: non-convergence now raises instead of warning, and
   `max_inner_iterations` is a constructor parameter):
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
2. See **Completed Tasks → From "Next session priorities"** — `InjectionPolicy`
   variants (`MANUAL`, `MANUAL_FRACKING_CHECK`, `AUTO_PRESSURE`,
   `AUTO_FLOW`, `AUTO_BOTH`) are DONE and in good shape, including the
   2026-08-04 follow-up investigation into how a future pressure-converging
   policy should be compared against old tango.
3. See **Completed Tasks → From "Next session priorities"** — `pymoo_api`
   (`src/tango/pymoo_api.py`) is DONE and in good shape.

**Explicit non-goal:** do **not** fix the old-tango AGS
`system_name()`/no-time-marching bug (see "Open items — tracked, not
scheduled" below) — old tango is not being patched.

## Surrogate-assisted optimization (`opt_hydro_df_electric_surrogate`) — pareto-front quality gap

See **Completed Tasks → From "Surrogate-assisted optimization
(`opt_hydro_df_electric_surrogate`) — pareto-front quality gap, open
2026-08-19"** for the full investigation and its resolution
(2026-08-31–09-01): switching the regressor from `RandomForestRegressor`
to Gaussian Process Regression, then to a small MLP, fixed the
pareto-edge accuracy problem well enough to trust — MLP is now the
default (12/45 predicted-pareto designs survive real-sim correction, up
from 3/43 under the original `RandomForestRegressor`). The one item from
that investigation NOT yet acted on — an active-learning loop, Chad's
explicit call to deprioritize — remains deliberately deferred; see
**Backlog** if it's picked up later.

## Open items — tracked, not scheduled

Real, still-open items that are deliberately **not** being worked next
session. Kept here so they don't get silently dropped or re-discovered
from scratch.

- **`opt_hydro_df_electric_surrogate/run_trajectory.py` was never committed
  and went missing, 2026-09-24 (non-urgent).** `just apps` failed on it
  (`can't open file .../run_trajectory.py`). It's stage 1 of that app's
  DVC pipeline (`dvc.yaml`'s `run_trajectory` stage): a short, real NSGA2
  search that keeps every evaluated individual as surrogate training data
  (`outputs/lhs_training_data.csv`), replacing the old
  `generate_lhs.py`/`sweep_lhs.py` pair. It's also referenced by both
  `just apps` recipes, `REDESIGN_TODO.md`, `optimize_surrogate.py` and
  `surrogate_api.py`. **Recovered** from a dangling git blob (`5257e43`,
  so it had been `git add`ed once and then unstaged), and the only change
  needed was `tango_next.*` → `tango.*` in its imports. A single-process
  smoke run (`--pop-size 8 --n-gen 2 --n-workers 1`) completes and writes
  both outputs. Remaining:
  - Commit it, so this can't happen again.
  - Checked 2026-09-24: no other untracked files under `applications/`,
    `src/`, `tests/` or `tools/`
    (`git ls-files --others --exclude-standard ...`).
  - `just apps` runs it without `--n-workers`, so it picks up
    `n_train_workers: 45` from `params.yaml`, which is way too many for a
    laptop smoke run with `--pop-size 8`. Consider adding a small
    `--n-workers` there, like the other `run_*` lines.
  - Still never validated at real (Euler) scale — see `REDESIGN_TODO.md`'s
    "What's genuinely still open".
- **Pump-less closed-loop check is now stricter than reality, 2026-09-21.**
  Chad removed the "No perpetual motion machines" commandment from
  `CONTRIBUTING.md`'s TANGO Commandments — there are valid real-world
  geothermal systems with no pump anywhere in the loop (e.g. Larderello,
  Italy, a vapor-dominated/self-pressurized field). The runtime check this
  commandment used to justify, `_check_loop_has_pressure_source` in
  `src/tango/workflows/workflow.py`, is UNCHANGED and still hard-rejects
  any closed loop lacking a `Compressor`/`Pump`/`PumpOrValve` node or a
  `*_with_pump` well — so a Larderello-style config would still fail
  validation today. That function's docstring also still points at the
  now-removed commandment ("See TANGO Commandments (CONTRIBUTING.md) for
  the rule this enforces"). Needs a real decision on how to relax this
  (options discussed: keep the hard reject as today and just fix the
  dangling docstring reference; add an explicit opt-out config flag for a
  deliberately pump-less design; or drop the check entirely and let the
  solver/physics reveal problems) — deferred, not yet decided.
- **Audit encapsulated-mutation rule (`CONTRIBUTING.md`'s TANGO
  Commandments) for uniform application, 2026-08-27.** New rule: a class
  instance's fields must only be modified by the instance itself (via its
  own methods, called internally or externally), never by direct external
  assignment — `state` (and `state`-shaped containers like `Stream`) is
  the one exception. Added retroactively, prompted by the `inlet`/
  `outlet` `Stream` refactor (same session: `Stream` fields became
  `LockedState`-wrapped, `inlet` became a `solve()` parameter instead of a
  stored field — see `Component.solve()`'s docstring). Not yet swept
  across the rest of `src/tango/` for other direct external
  `obj.field = value` writes that predate the rule (e.g. anything on
  `SurfaceComponent.injection_pressure`, orchestrator-level bookkeeping,
  or elsewhere) — deliberately deferred, not urgent.
- See **Completed Tasks → From "Open items — tracked, not scheduled"** for
  the old-tango AGS no-time-marching bug (decision: not fixing old tango
  for this).
- **MOOSE/MOSKito integration** — ~55 configs unrunnable, hardcoded to a
  former contributor's (Morteza's) machine, no docs left. Blocked on his
  response to outreach. Backlog. Also covers GitLab issue #21's DWSIM
  coupling ask — Chad's call (2026-09-25): DWSIM is downstream of MOOSE
  here, tracked together rather than as a separate thread.
- **No genuine "modest disparity" old-vs-new parity case found yet** — SF/
  EGS/double-flash sweeps all came back "good" agreement. CPG/ORC
  topologies and edge-of-sweep-range points haven't been checked.
- **Multi-segment well CAPEX (`well_length_seq`/`well_diameter_seq`
  equivalent) — planned, not built.** Overlaps GitLab issues
  [#17](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/issues/17)
  (economic-calculation flexibility) and
  [#20](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/issues/20)
  (new wellbore cost models) — link those there when this gets built
  rather than opening a fresh issue. Old tango's fields of the same name
  are meant to let well CAPEX vary by depth segment based on OUTER/casing
  diameter (different drilling/material cost per segment), independent of
  the inner flow diameter the physics uses — confirmed with Chad
  verbally, undocumented anywhere in `src/tango/` itself. Never actually
  exercised in old tango (every example file uses a single-segment list
  representing the well's full combined depth, not genuinely varying
  diameter by segment). See `project_economic_model_wackiness` memory:
  this field's poor documentation caused a real, now-fixed double-counting
  bug in `DoubletEconomicComponent` (it briefly seemed like the two active
  reference files' data was wrong — it wasn't; the port's cost-combining
  logic was). An earlier pass here claimed ~80 old-tango example files had
  stale/mismatched `well_length_seq` values — that check compared against
  `well_length` alone, which is the WRONG comparison (per the corrected
  understanding above); that finding should be treated as unverified, not
  re-used, unless someone redoes it against the correct check (does
  `well_length_seq` sum to the well's true combined total depth). When
  multi-segment costing gets built in tango: make it a genuinely
  optional field on well components, defaulting to the well's existing
  single `well_length`/`diameter` (today's behavior) when unspecified —
  multi-segment costing should be strictly opt-in, not a new required
  field on every well. See the "Needs revisiting" note under the
  `DoubletEconomicComponent`/`opt_AGS_direct_heat` DONE entry above —
  the horizontal-vs-vertical well-costing split done there is a narrower
  structural special-case, not a substitute for this general capability.
- **AGS sweep-vs-sweep comparison** (old tango vs. tango, full sweep)
  — blocked on getting all tango sweep scripts DVC-consistent with
  `--clean` flags first; not actioned.
- **Debugger walkthrough** (half done) — blocked on re-tracing
  `hydro_df_electric_exec_flow.drawio`'s T-convergence section
  against the new mechanism; `docs/tango_t_convergence.md` now
  explains the mechanism itself, but the exec-flow diagram's nodes still
  need re-tracing, not just a warning box.
- Three "Active" threads below (AGS sweep parity port, `common:`/
  component-block override ambiguity, `GraphSurface` p_out/pressure-
  provenance follow-ups) — see their sections for status.
- Untracked repo-root files (`CLAUDE.md`, `deployment_analysis_questions.md`,
  `tango_diagramming_workflow.md`) — left as-is; could be `.gitignore`d
  instead of tracked, still an open call.
- See **Completed Tasks → From "Open items — tracked, not scheduled"** for
  the production-side circuit numerically-unstable-near-166kg/s finding
  (RESOLVED, explained, not fixed, 2026-08-13).
- **Single-objective search support in `tango.pymoo_api`** — old
  tango's `optimizerr.py` offers several single-objective algorithms (GA,
  DE, PSO, CMA-ES, etc.) alongside NSGA2/NSGA3; `Minimization` only
  supports multi-objective (Pareto-front) search today. Non-urgent:
  investigate whether any real use case actually needs single-objective
  search before building support for it — don't build it speculatively.

- **TRACED 2026-08-13 — root cause found for `AUTO_BOTH` parity degrading
  from ~0.026% (`max_mass_rate=100`) to ~3.3% (`max_mass_rate=150`) vs.
  old tango.** Previous note here speculated "locally steep
  pressure-vs-mass_rate curve amplifying numerical noise" — **wrong,
  ruled out directly**: computed `drho/dP` and `drho/dT` via
  `fluid_utils.fluid_density` across 349-360 K at 55 MPa (the actual
  operating window) and both derivatives are smooth, varying <2% across
  the whole range — no property steepening, this is plain dense liquid
  water, nowhere near a phase boundary. (Separate from, and not the same
  mechanism as, the ~166 kg/s CoolProp crash above, which *is* a genuine
  phase-change crossing — that one's on the production side, this is the
  injection side.)

  **Actual mechanism, found by instrumenting both codebases and logging
  every outer-iteration's `(injection_pressure, mass_rate, outlet_T)`
  side by side** (`fracking_flow`/`fracking_flow` patched to record state
  in both `BC_calculator.py` and `fluid_utils.py`, plus DEBUG-level
  `AUTO_BOTH`/`T-convergence` logging):
  - `mass_rate` is **not** the source of divergence — it locks to the cap
    (150 kg/s) within 1-2 outer iterations in both codebases, confirmed
    identical.
  - The divergence is 100% in `p_inj_wellhead_no_frack`/`test_p`. At
    `max_mass_rate=150`, tango's outer loop takes **34 iterations**
    to converge (old tango: 5), with `rel_change_p` shrinking by a
    near-constant ~0.91-0.93 ratio per iteration — a slow *linear*
    (Picard) contraction, not the fast convergence a true Newton step
    would give — and lands on a **genuinely different final value**
    (~7.338 MPa vs. old tango's ~7.103 MPa, a real ~3.3% gap, not rounding
    noise). At `max_mass_rate=100` both converge in ~4-5 iterations to
    the same value (~7.03-7.05 MPa, matching to 0.026%).
  - **Root cause: the two codebases solve genuinely different fixed-point
    equations for `p_inj_wellhead_no_frack`, not the same equation at
    different speeds.** tango's `_converge_injection_both` calls
    `_converge_injection_T` every single outer iteration, which restores
    the *entire circuit* to its start-of-timestep snapshot and
    fully re-converges injection temperature to tight tolerance
    (`_DT_SURFACE_TOL`) before the pressure residual is computed — so
    tango's outer Picard step operates on the *exact* composed map
    `p → T*(p) → outlet.P(T*(p))`. Old tango's `iterator()` does no such
    T sub-convergence at all: `T` is set directly from
    `surface.outlet_fluid.T`, which just carries forward from whatever
    the *previous* outer iteration's single forward pass left it at — a
    lagged, under-relaxed joint Picard update on `(P, T)` together, not a
    nested/exact one.
  - **Why it only shows up at `max_mass_rate=150` and not `100`:** at
    `max_mass_rate=100`, the cap is deeply active — old tango and
    tango's own uncapped `fracking_flow()` estimate stays around
    ~163-180 kg/s the entire time, far above the 100 kg/s cap, so the
    constraint is robustly binding and both iteration schemes land on the
    same well-separated fixed point regardless of how T is handled. At
    `max_mass_rate=150`, the uncapped estimate hovers much closer to the
    cap itself (~162-178 kg/s vs. a 150 kg/s cap) — operating right at
    the edge where the `min(new_mass_rate, max_mass_rate)` constraint is
    only marginally active. That's the classic ill-conditioned regime for
    a coupled iterative solve, and it's exactly where the "exact nested
    T-reconvergence" vs. "lagged single-pass T" difference between the
    two codebases stops being negligible and starts mattering.
  - **Open question, not yet resolved:** which answer is actually
    correct physically. tango's slow crawl is consistent with
    genuinely finding the self-consistent solution (T fully converged at
    every step); old tango's fast convergence never confirms T is
    self-consistent at all, so its speed may be masking a real (if small)
    inaccuracy rather than reflecting a better-conditioned problem. Ties
    directly into the still-undecided "Newton/secant acceleration of the
    T-convergence loop" discussion (injection-T-guess robustness section,
    top of this file) — accelerating tango's outer loop would also
    make it cheap to check whether more iterations change the answer
    further, which would settle this.
  - `tests/regtest/test_tango.py::test_auto_both_matches_old_tango_automatic`'s
    choice of `max_mass_rate=100` (deliberately clear of this regime) and
    0.1% tolerance both still stand — no change needed there.

See **Completed Tasks → From "CLOSED 2026-08-13: AGS sweep parity (heat +
power)"** for the full history of the abandoned AGS sweep-vs-old-tango
parity effort (decision: not pursuing further, old tango's AGS handling is
confirmed broken).

See **Completed Tasks → From "Active: common:/component-block override
ambiguity"** for the full history (all sub-items landed).

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
- See **Completed Tasks → From "Active: GraphSurface p_out /
  pressure-provenance follow-ups"** for the pressure-monotonicity
  validation port and the p_out/efficiency unit-comment sweep (both DONE
  2026-07-23).
- [ ] **Same gap exists much more widely in `src/tango/`'s old-format
      examples — separate, bigger task, explicitly deferred.** Spot-checked
      `examples/flexible_SF_manual.yml`/`flexible_ORC_manual.yml`: `p_out:`
      values (e.g. `p_out: 0.5`, `p_out: 0.05`) have zero unit comments
      anywhere. `grep -rln "power_plant_graph:" examples/` (excluding
      `tango/`) turns up **60+ files** — a real gap, but not "easy," so
      explicitly not swept today (Chad's call, 2026-07-23, when offered a
      3-way scope choice). If picked up later: same treatment as above
      (`p_out` is bar per `flexible_pp.py`'s `Network(p_unit="bar", ...)`),
      but budget it as its own task, not a quick add-on.

## Active: external binary release to a collaborator (added 2026-09-23)

Moved to [GitLab issue #61](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/issues/61) (2026-09-28): licensed Nuitka binary + docs release to Paromita Deb, including the full technical plan formerly here.

## Backlog (queued, not yet started)

- **Open-source packaging — decision made 2026-09-23**, resolving the
  scoping question from this session's open-source packaging investigation
  (2026-09-16, see `docs/tango_progress_summary_sep_2026.md`). Three
  separate, independently-versioned pieces:
  - **`tango-utilities`** (working name — feedback welcome; risk of
    confusion with the `tango-core`/`tango` naming already used
    internally, and PyPI already lists an unrelated `PyTango` for the Tango
    Controls SCADA system, so check name availability before publishing) —
    the 9 shared-foundation modules (fluid properties, state management,
    numerical solvers, physics correlations) that the wellbore model
    depends on, per the 2026-09-16 investigation's dependency count.
    GitHub + PyPI, Apache 2.0.
  - **Wellbore model** (name TBD) — GitHub + PyPI, Apache 2.0, depends on
    `tango-utilities`.
  - **Private `tango-py` meta-repo** — not published to GitHub/PyPI. Holds
    `tango-utilities` and the wellbore package as git submodules, so
    changes to either can be developed and tested locally against the real
    `tango` codebase before being cut as a real release upstream, without
    needing a fresh GitHub/PyPI release for every iteration.
  - **Still open**: whether `surface`/`reservoir` also get open-sourced —
    the 2026-09-16 investigation flagged interest in all three, not just
    the wellbore model; this decision covers wellbore + its foundation
    dependencies only.
  - **Still open**: an actual license audit of the 9 foundation modules'
    and wellbore model's own dependencies (TESPy, CoolProp, pymoo, etc.)
    for Apache 2.0 compatibility — not yet checked, don't assume clean.

- **Errors should include more context, where possible.** Flagged
  2026-08-14 (Chad, mid-session), not started. When an error can be tied
  to a specific component or interface between components, the specific
  convergence iteration/loop it occurred in, and/or the timestep, the
  error message should say so — makes failures in a long unattended run
  (SLURM job, optimization search) actually diagnosable from the log
  alone rather than needing a debugger session to figure out WHERE in the
  circuit/timeline something went wrong. Needs a survey pass across
  `core/errors.py`'s raise sites (`ConvergenceError`, `InvalidPowerStateError`,
  `CoolPropError`, etc.) to see which already carry this and which don't —
  not a one-shot fix, likely touches many call sites incrementally.

- See **Completed Tasks → From "Backlog"** for: assessing how many
  numerical cells wells actually need (flagged 2026-08-14, resolved
  2026-09-16 by deriving `num_cells` from a target cell length rather than
  picking one shared fixed default).

- See **Completed Tasks → From "Backlog"** for: the `AUTO_BOTH`
  `InvalidPowerStateError` gap (considered and explicitly rejected as not
  worth building, 2026-08-13); the `opt_AGS_direct_heat/` block-on-
  `DoubletEconomicComponent` → fix → unblock chain (2026-08-13 → 2026-08-17,
  wiring into `just demos` confirmed done 2026-09-14); and the
  `NativeEconomicComponent` → `DoubletEconomicComponent` rename/native-sweep
  (DONE 2026-08-17). `opt_EGS_direct_heat/` itself is still not built — see
  the open item elsewhere in this Backlog if one exists, otherwise treat as
  a fresh ask.

- **Rename/move `example_configs/` → `example_configs/` at the repo
  root.** Flagged 2026-08-13, not started. Deliberately held until old
  `src/tango` is fully stripped out (targeted late August 2026) — drops
  both the `tango` qualifier (no more legacy `tango` to disambiguate
  from) and the `examples/` name (by then, YAML-only, so "configs" is the
  accurate name). Precondition already done as of 2026-08-13:
  `example_configs/` now holds only `.yml` configs — its two demo/sweep
  scripts (`demo_flexible_sf.py`, `sweep_demo_AGS_direct_heat.py`) moved to
  their own directories under `applications/`
  (`demo_hydro_sf_electric/`, `sweep_demo_AGS_direct_heat/`), matching the
  `run_*_sweep/`/`opt_*` layout, with `demo_flexible_sf.py` itself renamed
  to `demo_hydro_sf_electric.py` to match its config's actual name instead
  of old tango's `flexible_sf` terminology. So this backlog item is now a
  pure directory rename whenever it happens, not a restructure.

- **GitLab pipeline (likely release-triggered) that generates and publishes
  documentation.** Flagged 2026-08-13, not started. Deliberately held until
  `tango` fully replaces old tango and the legacy code is stripped out
  — building doc-generation tooling around a module structure that's about
  to be deleted isn't worth the effort now.

- **`Workflow.to_dataframe()` — flatten per-timestep history into a single
  dataframe.** Flagged 2026-08-11, not started. Goal: one row per recorded
  timestep, one column per time-varying leaf value, column names dot-joined
  through the full hierarchy (e.g.
  `components.production_well_upper.history.T_outlet`,
  `components.surface.history.node_history.turbine.P`).

  **Design notes:**
  1. `tango` already has a live, canonical, never-stale nested dict:
     `Workflow.to_dict()` (`workflows/workflow.py`) — `common`/`layout`/
     `sim_config`/`title`/`components`/`economic`, each component's own
     `model_dump()` nested under `components.<name>`. Start from that, not
     a new pydict layer.
  2. No length-matching heuristic is needed to tell history apart from
     static config: every component's `history` field is a dedicated
     dataclass (`WellboreHistory`/`LumpedReservoirHistory`/
     `GraphSurfaceHistory`/`NumericalWellHistory`, per-component-type in
     `components/*/`) whose fields are *always* per-timestep lists, and
     `state` fields are always scalars (`LockedState.get_fresh()`, one
     value for the current timestep). So the flatten pass only needs to
     recurse into dicts (component name → `history` →, for `GraphSurface`,
     two more levels: `node_history[node_name][quantity]`) and treat any
     list found under a `.history.` path segment as a column — no
     length-based guessing needed, `history.` prefix is sufficient.
     (Non-history list-shaped YAML config, if any ever exists, would need
     excluding explicitly, but none is known to exist today — check before
     generalizing this rule.)
  3. **Real complication to design for up front.** `Component` has a
     per-component `save_interval` (`core/component.py`, default `1`,
     frozen config field) — every component decides independently whether
     to append to its own `history` on a given timestep, so two components
     in the same `Workflow` with different `save_interval` values
     genuinely produce different-length history lists.

     `tango` has no get/set mechanism for this today — `save_interval`
     is a plain frozen-at-construction Pydantic field, set once per
     component via YAML, not a runtime-settable cascading property. So
     this needs a getter designed from scratch that actually detects
     divergence across the tree instead of silently reporting only
     `self`.

     **Proposed API** (discussed with Chad 2026-08-11 — his sketch was a
     Rust sum type, `enum SaveInterval { Uniform(usize), NonUniform }`;
     translated to the actual Python idiom for that shape, PEP 634
     dataclass-variants + `match`/`case`, rather than the plain
     "return a set, caller checks `len() == 1`" shortcut he also floated
     as a fallback):

     ```python
     @dataclass(frozen=True)
     class UniformSaveInterval:
         interval: int | None

     @dataclass(frozen=True)
     class NonUniformSaveInterval:
         intervals: frozenset[int | None]  # every distinct value present

     SaveIntervalReport = UniformSaveInterval | NonUniformSaveInterval

     def get_save_interval(self) -> SaveIntervalReport:
         """Walk every component; report whether save_interval is uniform."""
     ```

     Call sites use `match`, with a final `case _: assert_never(report)` so
     mypy flags it if a third variant is ever added — the closest Python
     gets to Rust's compiler-enforced exhaustiveness (`typing.assert_never`
     is available; `requires-python = ">=3.11"` per `pyproject.toml`, so no
     version blocker). `to_dataframe()`'s own uniform-`save_interval`
     precondition check (point 3 above) becomes the first real caller:

     ```python
     match self.get_save_interval():
         case UniformSaveInterval(interval):
             ...  # proceed
         case NonUniformSaveInterval(intervals):
             raise ConfigError(f"non-uniform save_interval: {sorted(intervals, key=str)}")
     ```

     Chad's plain-`frozenset`-return alternative (skip the two dataclasses,
     just return `frozenset[int | None]` and let callers check
     `len(x) == 1`) is the lower-ceremony option if this ends up being a
     one-call-site need — flagged as the fallback, not the recommendation,
     since the tagged-union version is the one that actually matches the
     Rust design intent (self-documenting return type, a case caller can't
     silently forget to handle) rather than relying on every caller
     remembering the `len() == 1` convention. Pick whichever before
     implementing `to_dataframe()`, not after — this getter is a
     prerequisite for it, not a follow-on.
  4. `economic` has no per-timestep `history` at all — it's computed once in
     `finalize()` (see [[project_pymoo_economic_resume_state]]), so its
     fields are all scalars. Exclude `economic.*` from the flattened
     time-series columns entirely (there's nothing to align it to
     row-per-timestep with); if a combined view is wanted later, that's a
     second, separate one-row dataframe/dict, not mixed into this one.
  5. No time/index column exists implicitly. `to_dataframe()` should
     prepend an explicit index column (row `i` → calendar timestep
     `i * save_interval`, then `* dt_years` if a years-since-start column
     is wanted) rather than leaving rows positionally implicit.
  6. `pandas`/`polars` are both already base dependencies (`pyproject.toml`)
     — no new dependency decision is needed; supporting both via a
     `backend` parameter is a preference call, not a dependency question.

  **Proposed signature**: `Workflow.to_dataframe(backend: Literal["pandas",
  "polars"] = "pandas") -> pd.DataFrame | pl.DataFrame`, implemented as a
  method on `Workflow` (not on individual components — the hierarchy being
  flattened is the whole workflow's `to_dict()` tree, not any one
  component's).

- See **Completed Tasks → From "Backlog"** for: `mark_all_stale()`
  cascaded from the orchestrator (DONE 2026-08); the reservoir no longer
  frozen during injection-temperature convergence (DONE 2026-08); the
  T-convergence explainer doc (DONE 2026-08-03); the `sweep.py` TODOs
  (DONE 2026-07-27); the DVC/`--clean`/SLURM rollout across all 7 sweep
  apps (DONE 2026-07-29); and the fluid-identity review (DONE 2026-07-30).

  **Two design questions from the 2026-07-29 DVC/SLURM rollout are still
  open and deliberately deferred, not silently dropped:**
  1. **`src/tango` isn't tracked as a dependency, and that matters more
     here than it did for old tango.** The DF app's `dvc.yaml` has a comment
     explicitly waving this off as "burdensome to hash" — a reasonable
     tradeoff for old tango, which is stable. `tango` is not: engine
     changes have repeatedly silently changed sweep output for anything
     using them (see the "CLOSED 2026-08-13: AGS sweep parity" history in
     Completed Tasks). Without `src/tango` as a dependency, DVC can't
     catch an engine-level regression the way a pipeline like this is
     supposed to. Consider a lighter-weight proxy (a params entry pinning
     the current git commit hash of `src/tango`, or depending on just
     the specific subpackages actually touched — `components/`,
     `orchestrators/`, `workflows/`) rather than either ignoring it
     (matches old tango's tradeoff, but riskier here) or hashing the whole
     tree every run.
  2. **No standardized metrics output across the three completed ports yet.**
     The double-flash port's `summarize.py` writes a real `summary.yaml`
     (mean/std/percentiles) DVC could track as a `metrics:` output; the
     AGS/EGS direct-heat ports only print pivot tables and write CSVs — no
     single YAML/JSON summary to diff across commits. Decide whether all
     three (four, eventually) should get a consistent small metrics file
     (success/fail counts, thermal-power percentiles, count meeting the
     105 degC threshold, etc.) before wiring in `dvc metrics diff`.
- **IN PROGRESS (~halfway, as of 2026-07-31) — Line-by-line debugger
  walkthrough of one `tango` single-simulation case.** Originally scoped
  against `example_configs/flexible_SF_manual.yml` (the original
  reference example used throughout tango's design/porting work —
  simplest well-understood topology); in practice picked up against
  `hydro_df_electric` instead, using
  `docs/diagrams/src/tango/hydro_df_electric_exec_flow.drawio`
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
  `hydro_df_electric_exec_flow.drawio` against the current
  `_converge_injection_T` (snapshot/restore, reservoir included, no more
  Pass 2) before continuing the debugger walkthrough past that point** —
  don't debug against the old nodes as if they still match
  `system_bc_iteration.py`.
- **Holistic repo-wide consistency/cruft review** — flagged 2026-07-24, not
  started. Chad wants a pass across the whole repo (not scoped to
  `tango`) to flag anything "wacky or inconsistent," explicitly
  including `examples/`/`applications/`/`tests/` that are overly
  duplicative and could be consolidated. Candidates worth checking when
  this starts (not yet verified, just things noticed in passing this
  session): the four near-identical `applications/run_*_sweep/` directories
  (`run_AGS_direct_heat_sweep`, `run_AGS_sweep`, `run_EGS_direct_heat_sweep`,
  `run_flexible_DF_manual_sweep`) each carry their own
  generate/sweep/summarize/plot scripts — worth checking how much is
  copy-pasted vs. genuinely different per site/product; `src/tango/`
  (old) vs. `src/tango/` (new) dual-maintenance surface generally.
  This is a big, open-ended audit — scope it explicitly before starting
  rather than diving in ad hoc.
- LCOE/LCOH economic-component design work for `tango` — paused
  2026-07-21 before reading any `src/tango/units/native/economic/*.py`
  source. Relevant to AGS sweep work since old tango's sweep scripts both
  read CAPEX/LCOE off `economic._results`.
- Seasonal/variable heat-demand mechanism design (see vision doc's
  "Seasonal heat-demand variation" section) — the real fix for task 1's
  gap, not yet designed.
- ~~`tango` example coverage matrix (AGS/EGS/CPG/Hydrothermal × heat/power)~~
  — **DONE 2026-09-25.** Every cell filled (AGS/EGS/CPG/Hydrothermal ×
  heat/power, including all four CO2 variants) with a real, runnable,
  sanity-checked config — full details, including the depth-deepening
  rationale for each hypothetical site and three real pump-or-valve bugs
  found and fixed along the way (a CO2/CPG-wide audit prompted by Chad),
  in `docs/TANGO_vision_and_roadmap/README.md`'s coverage-matrix section.
- ~~Broader old-tango example porting (58 confirmed-PASS + ~10
  confirmed-fine-just-slow per `REPO_CLEANUP_AUDIT.md`)~~ — moot as of
  2026-09-18: old tango's `examples/` set and `REPO_CLEANUP_AUDIT.md` (the
  categorization this relied on) are both deleted; nothing left to port
  from. Preserved at git tag `pre-tango-core-rename-2026-09-18` if this
  ever needs revisiting.
- Profiling `tango` once it stabilizes — vision doc, Phase 3.
- Speculative long-horizon architecture thinking (Modelica-family tooling,
  e.g. Rumoca, as a possible eventual replacement foundation for TESPy's
  causal-solve approach) — `docs/long_term_architecture_exploration.md`,
  started 2026-07-24. Explicitly parked, not planned; not blocking
  anything above.
- See **Completed Tasks → From "Backlog"** for the `src/tango/optimizerr.py`
  review that informed `pymoo_api`'s design, and the `opt_*`-side DONE half
  of the per-swept-variable scatter-plots item. pymoo_api itself is DONE
  (see "Next session priorities" → item 3 in Completed Tasks) — this
  backlog entry's "Not started" framing is stale.

- **Per-swept-variable scatter plots — `run_*_sweep` apps.** Flagged
  2026-08-13. Same idea as the already-DONE `opt_*` version (see Completed
  Tasks), not started.
  **LOW PRIORITY, ADD ALONGSIDE — statistical (not raw-scatter)
  cross-correlation for sweep post-processing (flagged 2026-08-17).**
  Chad's ask, prompted by ESTECO modeFRONTIER's analysis views: a
  parameter-pair-vs-objective view that shows the STATISTICAL
  relationship rather than a cloud of raw points (too much to take in
  visually at a glance). Candidate techniques, roughly in order of
  effort: (1) a correlation matrix/heatmap (Pearson or Spearman) across
  every parameter/objective pair — cheap, but linear-only, won't catch a
  genuine two-parameter interaction; (2) an ANOVA/regression effect
  decomposition (`objective ~ p1 + p2 + ... + p1×p2 + ...`), interaction
  terms plotted as a tornado/Pareto bar chart; (3) Sobol variance-based
  sensitivity indices (first-order + second-order/interaction), the
  statistically rigorous version of (2), needs either many samples or a
  fitted surrogate; (4) a response-surface/partial-dependence contour
  plot (fit a smooth surrogate over a parameter pair, draw filled
  contours, no raw points shown) — visual but smoothed, closest match to
  "not the actual data points."
  **Important scoping note, already confirmed with Chad:** this
  shouldn't run against an `opt_*` app's own Pareto-front output — a
  Pareto front is a thin, non-representative slice of the design space
  (in `opt_hydro_df_electric`'s current front, `mass_rate`/
  `injection_pressure` barely vary at all), so any of the above run
  against it would likely just report "no interaction" from lack of
  variance to explain, not genuine physics. This wants the broader
  `run_*_sweep` sweep data instead — which is also why this is filed as
  an addition to the `run_*_sweep` half of this same item, not the
  (already-done) `opt_*` half.

- **LOW PRIORITY, NO URGENCY — make economic calculations modular at the
  component level.** Flagged 2026-09-16, not started. Today, all economic
  logic (CAPEX/OPEX/LCOE, `DoubletEconomicComponent`,
  `components/economic/doublet.py`, 760 lines) lives in one monolithic
  economic component that reaches into the other components' state to
  compute costs, rather than each component (well, surface, reservoir)
  owning/contributing its own cost calculation the way it already owns its
  own physics. Goal: push cost computation down to the component level
  (e.g. a well computes its own drilling/casing CAPEX, a surface plant
  computes its own equipment CAPEX) so the economic layer aggregates
  already-computed contributions instead of being the one place that knows
  about every component's cost model. Non-urgent — no immediate driver,
  filed to avoid the monolithic economic component calcifying further as
  more component types are added (see [[project_economic_model_wackiness]]
  for known fragility in the current single-component design). Scope not
  worked out yet — worth checking how `well_length_seq`/multi-segment
  CAPEX (see "Open items — tracked, not scheduled" above) interacts with
  this before starting, since both touch how well-level costing is
  structured.

- **LOW PRIORITY, NO URGENCY — sync up the diagrams.** Flagged 2026-08-17
  (Chad). Scope not worked out yet — at minimum, the exec-flow diagrams
  (`docs/diagrams/*.drawio`, e.g.
  `hydro_df_electric_exec_flow.drawio` referenced by the "Debugger
  walkthrough" item above) and the vision doc's own diagram set
  (`docs/TANGO_vision_and_roadmap/README.md`, already migrated to `.drawio` for
  Confluence — see `project_vision_doc_diagrams` memory) should be
  reconciled against tango's CURRENT actual architecture/solve order
  (e.g. `component_idx: 0` is now the injection well with the surface
  solved last, not whatever an older diagram version assumed) before
  relying on any of them for a walkthrough or onboarding. Revisit scope
  when this is actually picked up.

- **Answers Chad's "can we make our own tespy components?"** question
  (asked 2026-09-17): yes — every TESPy component subclasses
  `tespy.components.component.Component` and implements `component()`,
  `inlets()`/`outlets()`, `get_parameters()`, `get_mandatory_constraints()`;
  see `docs/TANGO_vision_and_roadmap/README.md`'s Appendix A for the full
  assessment. The two items directly below are what that unlocks in
  practice.

- **LOW PRIORITY, NO URGENCY — bump the `tespy` pin.** Flagged 2026-09-17.
  `pyproject.toml` pins `tespy==0.7.1.post1` (Dec 2023); current release is
  0.11.2 (Sept 2026) — 4 minor versions behind. Newer TESPy has a friendlier
  custom-component extension API (`dependents()`, `dc_cmc`/`num_eq_sets`)
  that doesn't exist in our pinned version — worth having before any
  custom-TESPy-component work starts (see
  `docs/TANGO_vision_and_roadmap/README.md`'s Appendix A). Bump the pin, fix
  whatever breaks, and re-check golden-snapshot economic/LCOE tests for
  drift (same category of issue as the recent CoolProp-BICUBIC tolerance
  loosening). Deliberately held until Chad finishes his current unrelated
  work in another session.

- **AGS-wellbore-as-TESPy-component prototype.** Flagged 2026-09-17, not
  started. Explore modeling a standalone surface plant with a custom
  AGS-subsurface wellbore component that extends a TESPy base class and
  incorporates the existing wellbore physics model, as a step toward
  solving subsurface+surface as one implicit TESPy network instead of
  today's outer BC-iteration loop wrapping a separate `GraphSurface` solve.
  See
  `docs/TANGO_vision_and_roadmap/subsurface_as_tespy_components.md` for the
  open questions this needs to resolve first (subclass vs. adapter, the
  outer circuit's linear-representation conflict, the fracking
  complementarity reformulation) and `docs/implicit_solver_exploration.md`
  for the prior exploration this builds on. **Deliberately held — do not
  start until Chad says so.**

# Completed Tasks

Finished work, pulled out of the sections above so they stay focused on
what's still open. Kept verbatim (not summarized) — this is still the
detailed working record, just filed separately.

**Convention — follow this when moving something here:**
1. Each subsection heading below is `## From "<exact heading text of the
   section above it came from>"` — copy the source section's `##` heading
   text verbatim into the quotes, no paraphrasing, no CLOSED/RESOLVED/etc.
   prefix substituted in. The one exception is `## From the top-level list`,
   for the unheaded intro bullets directly under this doc's `#` title (they
   have no `##` heading of their own to quote).
2. Subsections here are ordered to match the top-to-bottom order of the
   sections above, not chronologically and not by when something landed.
   If a whole section becomes fully completed and gets removed from above
   entirely (e.g. an `## Active: ...` section with nothing open left in
   it), its `## From "..."` subsection here still occupies the same
   relative position it held when the section still existed above.
3. If a parent item up top is still open but has a completed sub-bullet
   nested inside it, pull just that sub-bullet down here (into the
   matching `## From "..."` subsection, creating it if it doesn't exist
   yet) and leave a one-line "See Completed Tasks → ..." pointer behind in
   the parent item — don't leave the done sub-bullet sitting in place.
4. An item that was investigated/explained/decided-not-to-fix (RESOLVED,
   TRACED, "decision: not pursuing further," etc.) counts as completed
   even if the underlying behavior itself was deliberately left unfixed —
   the task was "figure this out," and that part is done.

## From the top-level list

- **DONE 2026-08-04 — `LumpedReservoir` initial-pressure bootstrap fixed.**
  Its "not yet solved" bootstrap for `P_out_prev` was using the
  fracking-ceiling formula instead of old tango's actual reservoir-bootstrap
  formula (`brine_density × g × reservoir_depth`) — two different physical
  quantities. Added a `brine_density` field to `ReservoirComponent`
  (default 1000 kg/m³, matching old tango); `LumpedReservoir` now computes
  a proper `P_initial` matching old tango's formula exactly. Verified via
  isolated fixed-input comparison: reservoir outputs now agree to
  sub-microkelvin precision given identical inputs. Also matched
  `core/constants.py`'s `GRAVITY` to old tango's rounded `9.81` (was
  `9.80665`, the more precise NIST/ISO 80000-3 value) for comparison
  purposes, and made gravity a per-component field (`WellComponent`/
  `ReservoirComponent`) with that constant only as the default, since
  gravity genuinely varies regionally — see the TODO on `GRAVITY` for
  reverting the default once old-tango parity is no longer the active
  concern. Full test suite, golden snapshot, and `ParityCase` tolerances
  updated. Full technical detail: `docs/TANGO_vision_and_roadmap/README.md`.

- **DONE 2026-08-10 — production-well pump-power formula fixed; LCOE parity
  went from +16.1%/+11.5% off to -1.1%/-1.0%.** Chad's "urgent" pump-power
  investigation (queued behind the `target_extraction_pressure` fix above):
  suspected old tango's iterative pump solve might be reading a STALE
  power value — ruled that out empirically (instrumented a live run of
  the ACTUAL code path these examples use, `BC_calculator.py`'s
  `FlowRateCalculator.iterator` — note: `orchestrators/native.py`'s
  Newton-Raphson pump loop, read earlier in the investigation, is a
  RED HERRING for these examples; they route through `bc_iteration`
  scheduling instead, a completely different orchestrator). Old tango's
  `prod_pump_w_list.append(...)` fires immediately after the outer
  BC-convergence loop exits, using that same converged pass's fluid
  states — confirmed self-consistent (achieved pressure lands exactly on
  `target_extraction_pressure`, residual 0.00 Pa, every timestep). Not
  stale.
  The real cause: compared old tango's actual pump ΔP against
  tango's at the plateau timestep — 5.395 MPa vs. 5.302 MPa, only
  1.7% apart, so the WELL PHYSICS agreed closely. The ~2.035x power gap
  was entirely in how each system converts that (nearly-identical) ΔP
  into power. tango used `mass_rate * ΔP / ρ / pump_efficiency` (a
  naive hydraulic-work estimate); old tango's `BC_calculator.py` computes
  an isothermal CoolProp enthalpy rise (`-(inlet.H - outlet.H) * mass_rate`
  after an isothermal `updatePT` pressure boost) with NO efficiency term
  at all. Verified with real numbers pulled from a live run: the
  hydraulic estimate overstates the true enthalpy rise by ~53% at these
  conditions (~400 K, ~11-16 MPa) — water is nearly incompressible
  (`(∂V/∂P)_T` is tiny, as expected) but NOT thermally inert, and it's
  the thermal-expansivity term in the exact identity
  `dH/dP|_T = V - T*(∂V/∂T)_P` that matters here, not compressibility.
  Confirmed to 4 significant figures using CoolProp's own isobaric
  expansion coefficient (β≈8.62e-4 K⁻¹ at 400 K): predicted `dH/dP` from
  the identity matched the measured value from the live run almost
  exactly. 1.53x (formula mismatch) × 1.33x (extra `/0.75` efficiency
  term old tango doesn't apply) ≈ 2.04x — fully accounts for the
  observed gap.
  **Fixed**: `NumericalProductionWellWithPump.solve()`
  (`components/well/numerical.py`) now computes pump power as
  `mass_rate * (H(target_Pa, T) - H(P_wellbore, T)) / pump_efficiency`
  via the existing `fluid_enthalpy()` CoolProp helper — matching old
  tango's formula shape exactly. `pump_efficiency` default changed
  `0.75 → 1.0` (Chad's call: match old tango's no-derating behavior for
  parity now; a TODO notes dropping it to ~0.9 later once a real figure
  is chosen, deliberately deferred). Also fixed
  `LumpedProductionWellWithPump` (`components/well/lumped.py`) the same
  way — found it had a WORSE, separate bug along the way: it declared a
  `pump_efficiency` field but never actually applied it in `solve()` at
  all (dead field). Not exercised by any current example
  (`unit: numerical` is used everywhere), but fixed for consistency
  rather than left as a landmine for whoever switches variants next.
  Result verified against a fresh `_run_old_tango`/`_run_tango`
  comparison: LCOE SF -1.1%, DF -1.0% (down from +16.1%/+11.5%);
  `CAPEX_surface_plant`/`CAPEX_total` unaffected, as expected (pump power
  only feeds the LCOE denominator, not CAPEX). Updated
  `tests/regtest/test_old_new_economic_parity.py`'s stale golden values
  and module docstring (previously described a now-superseded
  final-timestep-only/"1-step lag" narrative from an earlier round of
  this investigation) and `docs/tango_tasks.md`'s "Next session
  priorities" entry below. Full `tests/unit`+`tests/regtest` suite: 123
  passed, 0 failed (up from 5 pre-existing failures before this fix) —
  `ruff`/`mypy` clean.

- **DONE 2026-08-11 — `pymoo_api.Minimization` now saves the current
  non-dominated front after every generation**, not just at the end.
  `Minimization.run()` was refactored from pymoo's `minimize()`
  convenience wrapper to the equivalent `algorithm.setup()` +
  `while algorithm.has_next(): algorithm.next()` loop (confirmed
  behaviorally identical — that's literally what `minimize()` does
  internally) specifically to get a hook between generations. After each
  one, writes `pareto_results_partial.csv`/`pareto_configs_partial/`
  (deliberately different filenames from the final
  `pareto_results.csv`/`pareto_configs/`, so a completed run's real
  output is never ambiguous with a leftover partial one from an
  interrupted run) plus an `n_gen` provenance column. If a run gets
  killed (SLURM time limit, Ctrl-C, crash), whatever the front looked
  like as of the last completed generation is already on disk.

- **DONE (superseded) — stop/resume for `Minimization.run()`.** Chad's
  ask, prompted by the save-every-generation feature above — being able to
  pause a long HPC run and later continue it from where it left off, rather
  than restarting from scratch. True checkpoint/resume (pickling the live
  `algorithm` mid-run, including its `multiprocessing.Pool`) was researched
  but never implemented — see git history for the removed writeup. Instead,
  `Minimization` gained `seed_from`/`pad_sampling`: `seed_from` points at a
  previous run's `pareto_results.csv` (or `_partial` variant), its
  non-dominated designs become the initial population, and `pad_sampling`
  (default `LHS()`) fills the rest of `pop_size`. Not a true resume (fresh
  RNG state, restarts at generation 1), but it gets the practical benefit —
  a new run picks up from where the old front left off instead of from
  scratch — without the pool-pickling complication. Good enough that true
  checkpoint/resume is no longer planned.

- **DONE 2026-09-16 — switched TESPy's CoolProp backend from plain HEOS to
  BICUBIC-tabulated HEOS** (`COOLPROP_BACKEND` in `core/fluid_state.py`,
  threaded into `GraphSurface`'s TESPy connections) for a real wall-clock
  speedup on any run touching the power plant. Trade-off: the tabulated
  backend builds its interpolation tables adaptively around whatever P/T
  range a solve hits, so identical code run in separate processes can land
  on visibly different (though physically insignificant) answers — hence
  `GOLDEN_RTOL` in `test_old_new_parity.py` loosening from bit-exact to
  `50e-6`. Golden snapshots regenerated to match.

- **DECIDED 2026-09-17 — keep the outer-circuit `component_idx`/`prev`/
  `next` scheme; do not replace it with tespy-style `edges`.** Flagged
  2026-09-09 (see the top-level list's original entry) for consistency
  with `GraphSurface`'s own `power_plant.nodes`/`edges` block, which really
  is a 1:1 mirror of TESPy's own `Connection(source, port, target, port)`
  model. Scoped out before implementing anything: the outer circuit
  (injection well → reservoir → production well(s) → surface → back) is a
  DIFFERENT, deliberate design choice, not a port regression — it exists
  specifically to give `sim_config.bc_checkpoint_idx` a clean, explicit way
  to name where BC (boundary-condition) iteration happens, and for human
  readability of circuit position. Confirmed while scoping the ORC port
  (immediately below) that this doesn't even block binary/ORC topologies:
  a secondary fluid loop lives entirely inside one `GraphSurface` node's
  own `power_plant` subgraph (closed via `CycleCloser`), never touching the
  outer circuit's shape. Chad's call: keep `component_idx`/`prev`/`next` as
  it is.

- **DONE 2026-09-17 — ported `examples/flexible_ORC_manual.yml` as
  `example_configs/hydro_orc_electric.yml`; no dedicated ORC component
  needed.** The binary (ORC) plant is a plain `GraphSurface` subgraph — the
  secondary R245fa loop lives entirely inside `power_plant.nodes`/`edges`,
  closed via `CycleCloser`. Needed one real `GraphSurface` extension:
  per-port connection attributes (`GraphSurface._apply_connection_config`
  in `components/surface/graph.py` — `fluid_out{N}`/`h0_out{N}`/
  `p0_out{N}`/`vapor_mass_fraction_out{N}`, keyed by a connection's
  `source_id`) plus `pressure_ratio1`/`pressure_ratio2` (`HeatExchanger`'s
  `pr1`/`pr2`) and `ttd_l` at the component level, for a dual-fluid
  `HeatExchanger` carrying the geofluid loop on `out1` and the secondary
  loop on `out2`. `pump2` needed `type: PumpOrValve`, not a fixed
  `Compressor` — the same natural-pressure-surplus ambiguity
  `AGS_direct_heat.yml`'s `circulation_control` already resolves this way.
  Added as a real (non-stub) `ParityCase` in `test_old_new_parity.py` with
  a committed golden snapshot — measured old-vs-new deviation (reservoir T
  ≲3.83 K, production T ≲2.57 K, gross power ≲4.8%) is the same class/size
  as the already-accepted SF case, actually tighter. Runs
  `injection_mode: manual`, not `manual-fracking-check`: at these exact
  inputs old tango's injection well outlet sits at 54.48 MPa (just under
  the 55 MPa fracking ceiling) while tango's numerical well model
  puts it at ~55.4–56.0 MPa (just over) — same-size deviation as everything
  else here, landing on the wrong side of this site's tight margin;
  `manual-fracking-check` has no self-correction to absorb it. Also added:
  a draw.io topology diagram
  (`docs/diagrams/src/tango/hydro_orc_electric_topology.drawio` +
  rendered PNG). `docs/TANGO_vision_and_roadmap/README.md`'s AGS
  power-generation-sweep port can reuse this pattern directly — no new
  Python needed there either, only YAML composition.

- **DONE 2026-09-17**: renamed the `components:` YAML registry-key field
  `unit:` to `variant:` everywhere (`COMPONENT_REGISTRY`'s `(type, unit)` key
  is now `(type, variant)`) — `unit` was old tango's own registry-key naming
  and reads as "unit of measure" next to fields like `well_length: 5000.0 #
  m`; `variant` (Rust-enum-variant-flavored) doesn't have that collision.
  Changed: `src/tango/components/registry.py`,
  `src/tango/workflows/workflow.py` (`_build_components`,
  `_build_economic_component`, `Workflow.to_dict()`), every
  `example_configs/*.yml`, `docs/TANGO_vision_and_roadmap/README.md`'s two
  `unit: numerical`/`unit: lumped` mentions. Full test suite re-run green
  after the rename. Not a TESPy concept and never was — `GraphSurface`'s own
  `power_plant.nodes` never had a `unit`/`variant` key at all (TESPy
  component types are looked up by `type` alone, unambiguously); this
  rename is scoped entirely to the outer `components:` block.

## From "Next session priorities"

- **DONE 2026-08-04 — non-convergence must raise, not warn.**
  `_converge_injection_T`'s `for...else` now `raise`s `ConvergenceError`
  (already existed in `core/errors.py`, no new exception class needed)
  instead of `logger.warning(...)` when `max_inner_iterations` is
  exhausted without converging — previously the loop silently returned
  and the caller used the unconverged state as if it were final.
  Audited the rest of `tango` for the same silent-swallow pattern
  (`logger.warning`, bare `except`, other max-iteration loops) — this
  was the only instance; nothing else needed the same fix. Full test
  suite re-run clean (121 passed, 40 xfailed, matches baseline).
- **DONE 2026-08-04 — `max_inner_iterations` is now a constructor
  parameter** on `SystemBCIteration` (default `DEFAULT_MAX_INNER_ITER =
  20`, same value as before), replacing the hardcoded module-level
  `_MAX_INNER_ITER` constant, so it can be tuned per-case instead of
  requiring a code edit.
- **DONE — `InjectionPolicy` variants in good shape.** `MANUAL`,
  `MANUAL_FRACKING_CHECK`, `AUTO_PRESSURE`, `AUTO_FLOW`, and `AUTO_BOTH`
  are all real, implemented policies in `orchestrators/system_bc_iteration.py`.
  See `docs/tango_t_convergence.md` for how `MANUAL`'s convergence
  loop works as the reference case.

  **Follow-up once pressure convergence lands, agreed 2026-08-04**: after
  implementing real BC-iteration pressure physics (the "Planned: real
  BC-iteration physics" section of `system_bc_iteration.py`'s module
  docstring), re-run the `flexible_SF_manual.yml` parity comparison
  against old tango's actual equivalent. Confirmed the current comparison
  is *not* confounded by fracking/mass-rate iteration — verified two ways
  (instrumented a real run): `flexible_SF_manual.yml` uses
  `mass_rate.type: manual`, which skips old tango's `automatic`-only
  mass-rate iteration loops entirely, and `check_fracking`'s cap
  (`fracking_flow()` ≈ 183–403 kg/s across timesteps) never actually
  engages against the manual `mass_rate=50` kg/s — it's a no-op for this
  case. The real asymmetry is that old tango's outer loop *always*
  iterates injection pressure (`test_p`), in every mass-rate mode,
  including `manual` — there is no old-tango mode that skips pressure
  iteration the way tango's `MANUAL` currently does. So "the
  relevant old tango equivalent" to compare a future pressure-converging
  tango policy against is simply old tango's `iterator()` as-is, not
  a different/special old-tango mode.

  **Correction, 2026-08-04**: the paragraph above was written assuming
  old tango's `test_p` update actively runs for this comparison. Directly
  instrumented and checked across the full 20-timestep run: it does not
  — `manual` mass-rate mode's `test_p` update only fires when `target_p
  <= inj_well.outlet_fluid.P` (a one-sided fracking-safety cap, not an
  active solve), and for this config `target_p` (55 MPa) never drops
  below the bottom-hole pressure (~49.75–49.88 MPa) it's compared
  against — so `test_p` stays pinned at its YAML initial-guess value for
  every single timestep. **This asymmetry is real as a general
  mechanism, but is not active for `flexible_SF_manual.yml` and is not
  the cause of its parity delta** — see the top-level-list entry above
  (reservoir initial-pressure bootstrap fix) for what was. The general
  point about needing a future pressure-converging tango policy to
  compare against old tango's `iterator()` as-is (not a special mode)
  still stands for whenever a config *does* exercise this path.

  Also checked (instrumented a real run, reverted after) whether the
  `production_well_pump`'s hardcoded `num_dp_iter = 5` loop
  (`BC_calculator.py:456-497`) introduces meaningful error for this case:
  measured residual shrinks geometrically (~0.006× per iteration) from
  ~2.7 MPa (iteration 0) to 0.004 Pa (iteration 4, the last one
  performed) against a 7 MPa target — ≈6e-10 relative error. **Confirmed
  negligible for `flexible_SF_manual.yml`** — not a contributor to the
  observed parity deltas. Caveat: this converges fast because the
  pump-pressure/outlet-pressure relationship is nearly linear in this
  case's regime; the loop still has no real convergence check at all (its
  only early-exit condition requires `pump_dp == 0.0`, i.e. no boost
  needed — for any case actually needing a nonzero boost it just runs all
  5 iterations unconditionally), so this finding doesn't generalize to
  cases closer to a phase boundary — re-check if a future case exercises
  that regime. Not fixing this in old tango; noted here only so the
  "is this negligible?" question doesn't have to be re-derived.
- **DONE — `pymoo_api` in good shape.** Built (`src/tango/pymoo_api.py`),
  deliberately restricted to `MANUAL`/`MANUAL_FRACKING_CHECK` only — the
  `AUTO_*` policies are intentionally NOT wired in (Picard/BC-iteration
  convergence loops don't mix safely with an external optimizer driving
  the same state); do not treat this as a gap to fill.

## From "Surrogate-assisted optimization (`opt_hydro_df_electric_surrogate`) — pareto-front quality gap, open 2026-08-19"

Built `tango.surrogate_api` + `applications/opt_hydro_df_electric_surrogate/`
(LHS sample → real-sim sweep → train a `RandomForestRegressor` per
objective + a `RandomForestClassifier` feasibility gate → NSGA2 against
the surrogate → real-sim validation of the result). Confirmed on a real
2000-sample Euler run:

- **Speed: ~10x faster end to end** (whole pipeline ≈1763s vs. the real
  `opt_hydro_df_electric` run's 19,116s) — the surrogate-driven NSGA2
  step itself is negligible; most of the pipeline's own time is the LHS
  real-sim sweep (~330s) and the constrained NSGA2 search (~1365s at
  `n_ieq_constr=1`, elementwise evaluation — see gap below).
- **Feasibility classifier worked as intended**: 100% of the returned
  pareto designs are real-feasible now (up from 26%, i.e. 11/43, before
  the classifier gate was added) — CV accuracy 97.6%, recall on
  infeasible designs 98%.
- **But the result is not yet usable as-is.** Re-deriving genuine
  non-domination from the REAL (not predicted) objective values
  (`surrogate_api.corrected_pareto_front`) collapses the returned
  41-design front down to only **3** genuinely non-dominated designs —
  the other 38 are near-duplicates that only *looked* distinct under the
  surrogate's ~1-3% prediction noise. That surviving 3-design front also
  only spans a narrow low-LCOE corner (LCOE 0.3496–0.3498, power
  4591–4599 kW) vs. the real optimization's much broader 45-design front
  (LCOE 0.3463–0.4622, power 4691–4865 kW) — the higher-LCOE/higher-power
  half of the real tradeoff curve is missing entirely.
- **Working theory** (not confirmed): `RandomForestRegressor` predictions
  are piecewise-constant (flat per-leaf plateaus). NSGA2 can converge a
  whole population onto tiny variations within one lucky plateau, which
  looks like many distinct non-dominated tradeoffs to the surrogate but
  collapses once real values disambiguate them — and starves exploration
  of parts of the space with thinner training-data signal (only 926/2000
  LHS samples were feasible).

**Next steps, Chad's stated order (2026-08-19, prioritized this way
deliberately — do not reorder without checking with him):**

1. **Switch to a smooth predictor** instead of `RandomForestRegressor`
   (top candidate discussed: Gaussian Process Regression — standard
   choice for few decision variables + expensive real evaluations, and
   gives a native per-prediction uncertainty that could replace/augment
   the separate classifier). Chad also floated plain scikit-learn
   `DecisionTreeClassifier`/`DecisionTreeRegressor` (DTC/DTR) as an
   option — flag before trying: a single decision tree's plateaus are
   LARGER/coarser than a random forest's (a forest is an average over
   many trees, which already smooths the staircase somewhat), so DTC/DTR
   would likely make the plateau-collapse problem WORSE, not better, on
   the smoothness dimension specifically — worth confirming/refuting
   empirically rather than assuming, but that's the a priori expectation.
2. **Bump `n_lhs_samples` from 2000 to 5000** — cheap on Euler (~15-40 min
   given 45 workers), improves regressor/classifier resolution
   everywhere, especially the sparser higher-LCOE/power corner.
3. **Only if 1+2 don't work well: an active-learning loop** (retrain the
   surrogate on `validate_surrogate`'s real-evaluated designs each round,
   re-optimize, repeat a few times). Chad's explicit call: this is
   deprioritized — "overly complicated and risks giving away performance
   benefit" (each round adds a full real-sim validation pass, eating into
   the ~10x speedup) — don't reach for it first.

Status: paused here (Chad's call, 2026-08-19) — picking back up next
session, not mid-fix.

**RESOLVED 2026-08-31–09-01 — switched regressor, in the order above,
until pareto-edge accuracy was good enough to trust.**

- **Gaussian Process Regression (2026-08-31), item 1's top candidate:**
  ran ~5.3x faster than the real-sim baseline with strong CV R² (0.9985
  LCOE, 0.9954 power) — but NSGA2 exploited a region where its LCOE
  predictions were off by up to 35%, and only 3 of 43 predicted-pareto
  designs survived real-sim correction. Effectively the same failure mode
  as the original `RandomForestRegressor`, just with better-looking CV
  metrics — confirms the plateau/smoothness theory above wasn't the
  whole story, or at least that GP's own smoothness wasn't sufficient on
  its own.
- **MLP (small neural network) (2026-09-01), tried after GP's miss:**
  right-sized to `hidden_layer_sizes=(16, 16)` after an initial
  `(64, 64)` attempt turned out to be tens of thousands of weights
  against only a few thousand feasible LHS rows — a real overfitting
  risk the original tuning guidance didn't reflect. Confirmed on a real
  5000-sample Euler run (item 2, `n_lhs_samples` bumped to 5000, folded
  into this same run rather than tried separately): MLP trained in ~15s
  vs. GP's ~36 min, AND held up far better at the pareto edge (LCOE
  relative error: median 1.4%/max 4.3%, vs. GP's median ~9.8%/max 35%),
  leaving 12/45 predicted-pareto designs genuinely non-dominated after
  real-sim correction vs. GP's 3/43.
- **MLP is now the default regressor**; GP remains available as the
  smooth-surface reference case, documented as such rather than as the
  default. Item 3 (active-learning loop) was never reached — not needed
  once MLP's numbers were good enough — and remains deliberately
  deprioritized per Chad's original call, not restarted.

## From "Open items — tracked, not scheduled"

- **Old-tango AGS no-time-marching bug** (`system_name()` routing in
  `src/tango/utils.py` sends AGS-shaped configs to a no-op `SystemNative`,
  so old tango never advances time for AGS configs). Confirmed real,
  three independent ways. **Decision: not fixing old tango for this.**
  tango itself is unaffected; this only blocks using old tango as an
  AGS transient reference.
- **RESOLVED (explained, not fixed) 2026-08-13 — production-side circuit
  numerically unstable near/above ~166 kg/s for `hydro_sf_electric.yml`.**
  Chad's assessment: the elevated mass rate drives enough production-side
  pressure drop that the fluid crosses its phase-change pressure on the
  way back up, which is exactly consistent with the near-constant-enthalpy
  CoolProp failure signature below. Not worth digging into further.
  Original note, found 2026-08-12 while testing
  `InjectionPolicy.MANUAL_FRACKING_CHECK`'s flow-induced pathway. Raising
  `sim_config.mass_rate` even slightly above the config's own
  `fluid_utils.fracking_flow()` threshold (confirmed: crashes starting at
  166.5 kg/s, i.e. essentially at the threshold, not comfortably past it)
  makes some downstream node's CoolProp state solve go negative-pressure
  (`updateHP(...)` failing at a near-constant enthalpy ~768-770 kJ/kg
  across every mass rate/injection-pressure combination tried — 18 total
  permutations, all failed the same way). The near-constant enthalpy
  regardless of `components.surface.injection_pressure` indicates this is
  on the **production side** of the circuit (friction-driven pressure drop
  from the elevated mass rate through the production wells/surface plant),
  not the injection side that `injection_pressure` controls — so raising
  injection pressure can't rescue it. Net effect: for this example file,
  there is no numerically-stable mass rate high enough to actually trigger
  `MANUAL_FRACKING_CHECK`'s flow-induced check through a genuine full-circuit
  `Workflow.run()` — the circuit breaks (for an unrelated reason) at or
  below the fracking threshold itself. Worked around, not fixed:
  `tests/regtest/test_tango.py::test_manual_fracking_check_raises_on_flow_induced_violation`
  solves once at the nominal (safe) mass rate, then calls
  `SystemBCIteration._check_fracking()` directly with a boosted
  `orch.mass_rate` — exercising the same comparison `run_timestep` makes,
  without a second, numerically-unstable full solve. The pressure-induced
  pathway doesn't have this problem (a modest `injection_pressure` bump at
  the *nominal* mass rate triggers it cleanly via a real `run()`, see the
  test above it) — this gap is specific to pushing mass rate itself past
  the threshold. Root cause not investigated further (which specific
  component/node destabilizes first) — worth revisiting if a real
  `AUTO_FLOW`/`max_mass_rate`-cap use case needs to actually operate near
  this boundary rather than just detect it after the fact.
## From "CLOSED 2026-08-13: AGS sweep parity (heat + power)"

**Decision: not pursuing further.** Old tango's AGS handling is confirmed
broken (see the `system_name()` no-time-marching bug, filed under "From
'Open items — tracked, not scheduled'" above) — comparing tango's AGS
output against a reference that never actually advances time isn't worth
chasing. Rely on tango's own smoke tests and golden-snapshot
self-consistency for AGS instead of an old-vs-new comparison. History kept
below for context; treat everything in this section as abandoned, not
queued.

---

Started 2026-07-22. Scope: get both AGS sweep apps (direct-heat and the new
power-generation counterpart) verified in old tango, fully ported to
`tango` under `applications/run_AGS_sweep/`, compared
against old tango, and locked in with golden-snapshot regression coverage.

### 1. Demand-profile documentation for the thermal AGS sweep
- [x] Document that `run_AGS_direct_heat_sweep` assumes constant heat
      demand, not a real seasonal/dispatch curve — done 2026-07-21:
      `applications/run_AGS_direct_heat_sweep/run_AGS_direct_heat_sweep.py`
      docstring item 5, cross-referenced from
      `docs/TANGO_vision_and_roadmap/README.md`'s "Seasonal heat-demand variation"
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
Built as `applications/sweep_demo_AGS_direct_heat/sweep_demo_AGS_direct_heat.py`. Sweeps
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

### 3. Port both to `tango` under `applications/run_AGS_sweep/`
- [x] **Blocking gap RESOLVED 2026-09-17**: a binary/ORC plant is now a
      plain `GraphSurface` subgraph, no dedicated ORC component needed —
      confirmed by porting `examples/flexible_ORC_manual.yml` to
      `example_configs/hydro_orc_electric.yml` (parity case added to
      `tests/regtest/test_old_new_parity.py`). The secondary (ORC
      working-fluid) loop lives entirely inside `power_plant.nodes`/
      `edges` — `CycleCloser` closes it, and a two-sided `HeatExchanger`
      node carries the geofluid loop on its `out1` side and the secondary
      loop on `out2`. This needed one real `GraphSurface` extension:
      per-PORT connection attributes (`GraphSurface._apply_connection_config`,
      `components/surface/graph.py`) — a node with more than one outgoing
      connection can now take `{attr}_out{N}`-suffixed YAML keys
      (`fluid_out2`, `h0_out1`, `p0_out2`, `vapor_mass_fraction_out2`)
      targeting specifically the connection whose `source_id ==
      f"out{N}"`, plus `pressure_ratio1`/`pressure_ratio2` (`HeatExchanger`'s
      `pr1`/`pr2`) and `ttd_l` at the component level. `Stream.port` was
      NOT resurrected and does not need to be: this multi-port need was
      entirely internal to `GraphSurface`'s own TESPy connection list —
      every `Component`'s own `inlet`/`outlet` boundary (the thing
      `Stream.port` would have addressed) stayed genuinely single-port
      throughout. The AGS power-generation port below can reuse this
      directly — no new Python code, only YAML composition, same as the
      direct-heat port.
- [ ] Decide app structure: one shared `tango` sweep pipeline
      parameterized by product (heat/electricity), or two directories
      mirroring old tango's split. Leaning toward shared, since the
      well/loop topology and all four sweep axes are identical between the
      two old-tango apps and only the surface block differs — avoids
      duplicating the generate/sweep/summarize/plot pipeline twice.
- [ ] Wire the four sweep axes (depth, mass-flow, loop-length,
      loop-diameter) through `tango`'s YAML-mutation pattern,
      matching old tango's `sweep.py` `_apply_*` functions.
- [ ] `example_configs/AGS_direct_heat.yml` already exists (single
      design point, not the swept version) — decide whether the new sweep
      app reuses/generalizes it or the sweep pipeline generates its own
      per-design YAML from a template the way old tango's does.

### 4. Compare tango vs. old tango, close/explain discrepancies
- [ ] **`AGS_direct_heat.yml` parity — scoped 2026-07-23, picked up
      2026-07-31, BLOCKED on a discovered old-tango bug (not a tango
      problem).** Of the three pieces originally scoped, the first two are
      actually done; the third uncovered something bigger than "confirm a
      result key."
      1. **DONE 2026-07-31** — static single-point old-tango reference file
         added at `examples/AGS_direct_heat.yml` (copied from
         `applications/run_AGS_direct_heat_sweep/triemli_dh_base.yml`, the
         two sweep-placeholder fields — `horizontal_well.well_length` and
         `schedule.well_spacing` — fixed from `2500.` to `707.` to match
         `example_configs/AGS_direct_heat.yml`'s reference point exactly:
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
         `examples/AGS_new/AGS_H2O_native_direct_heat.yml` (20
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
         vs. tango (382 kW old, flat, vs. tango's real transient
         declining 142.7 kW → 110.1 kW over the run) — it isn't a tunable
         numerical deviation, old tango simply has no valid transient
         reference for this topology to compare against.

         **All affected files now carry an explicit in-file warning**
         (added 2026-08-01, not yet fixed): `system_name()`'s docstring and
         the `SystemNative` class docstring in the two files above; every
         old-tango config with `horizontal_well` + no `reservoir` —
         `examples/AGS_direct_heat.yml`, `examples/AGS_new/
         AGS_H2O_webapp_native.yml`, `examples/AGS_new/
         AGS_H2O_native_direct_heat.yml`, `examples/testcase{6,7,8}.yml`,
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
         no valid old-tango transient reference, and rely on tango's
         own smoke test (`test_ags_direct_heat_smoke`) + golden-snapshot
         self-consistency instead of an old-vs-new comparison; (b) fix
         `system_name()`'s AGS routing in old tango so it actually
         time-marches, then re-run this comparison for real; (c) something
         else. Chad's call, not started.
      Comparison harness (`_run_old_tango`/`_run_tango` in
      `test_old_new_parity.py` being hardcoded to the SF/DOUBLET topology)
      still needs the parallel no-reservoir/thermal-only path described in
      the original scoping — deferred behind the blocker above, no point
      building it against a reference that can't validate anything yet.
- [ ] Add an equivalent parity case for the power variant once its
      `tango` port exists.
- [ ] Decide comparison scope: full 6006-point sweep-vs-sweep comparison
      is expensive and probably unnecessary. Proposal: single-point parity
      (already the pattern) plus a small hand-picked set spanning the
      depth range (e.g. shallow/mid/8000 m-edge-case), not the full grid —
      revisit only if that surfaces something that needs denser sampling.
- [ ] Investigate and either fix or document (with tolerance/rationale,
      matching the existing `ParityCase` tolerance-with-notes pattern) any
      discrepancy found beyond old-vs-new tolerance.

### 5. Golden-snapshot regression coverage
- [ ] `tests/regtest/golden_tango/` currently only has
      `flexible_SF_manual.json`. Add golden snapshots for the AGS
      direct-heat case (once added to `PARITY_CASES`, step 4) and the AGS
      power case, via `tools/update_tango_golden.py`, only after
      their outputs are trusted (i.e., after step 4's discrepancies are
      resolved/explained — a golden snapshot locks in whatever's there,
      good or bad).

## From "Active: common:/component-block override ambiguity"

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
      `example_configs/flexible_SF_manual.yml` and
      `example_configs/AGS_direct_heat.yml` to move these two keys from
      `components.surface` into `common:` (previously only declared under
      `components.surface`, which happened to work because of the old
      `components_block.get("surface", ...)` fallback that's now removed).
      Also added a `common.get("surface_pressure", ...)` entry to
      `layout_extras` — previously `surface_pressure` wasn't shared at all,
      only `surface_temperature` was. All tango regtests pass
      (`test_old_new_parity`, `test_ags_direct_heat_smoke`, full
      `test_tango.py`) after the example-file edits, confirming no
      numeric behavior changed.
      `example_configs/SF_manual_differing_st.yml` (the file that
      demonstrates the bug) needed no change — it targets
      `unit: single_flash`, which isn't registered in `COMPONENT_REGISTRY`
      (`SingleFlashSurface` was deleted, see
      [[project_tango_ags_surface_design]]), so it's already skipped
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
      4. Locked in with 3 new tests in `test_tango.py`:
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
         alongside the existing `from_file()`. 5 new round-trip tests
         in `test_tango.py` (`test_workflow_to_config_*`,
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
         carryover, not a `tango`-native design). Chad's stated
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
         acceptable, for a derived-optional-field pattern — a handful of
         clearly-labeled exceptions is fine; an undocumented, ambiguous
         cache is not.
      8. **`brine_density` and `well_pattern`/`well_pattern_dimens` —
         confirmed dead, handled differently.** `brine_density` (present in
         every example file's `common:` block) is consumed by nothing in
         `tango`, and isn't in old tango's `CommonSpecs` either —
         genuinely dead cruft, now rejected by `Common`'s `extra="forbid"`;
         removed from all 3 `example_configs/*.yml` files.
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
         step); `mypy src/tango/` clean; `ruff` clean.
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
          Verified safe by grepping the whole `src/tango/` tree for
          direct reassignment of every frozen-candidate field name before
          touching anything — the only hits were `inlet`/`outlet`/
          `injection_pressure`/`save_interval` (comparison, not assignment)
          and the orchestrator's own unrelated `dt_years` attribute. Added
          `test_frozen_component_config_rejects_runtime_mutation`
          (`tests/regtest/test_tango.py`) alongside the existing
          `test_frozen_common_rejects_runtime_mutation`. Full
          `tests/regtest`+`tests/unit` suite green (36 passed, 1 xfailed);
          `mypy src/`, `ruff check`, `ruff format --check` all clean;
          `applications/sweep_demo_AGS_direct_heat/sweep_demo_AGS_direct_heat.py` re-run and
          confirmed byte-identical output to before this change.
- [x] **NEXT SESSION — Chad wants to understand the shared-reference
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
         NOT translate directly to Rust — wants this
         explained explicitly: `Rc<RefCell<Common>>`/`Arc<Mutex<Common>>`
         vs. Python's default pass-by-object-reference, why Rust's ownership
         model wouldn't let multiple structs hold an unsynchronized shared
         mutable reference the way Python just did, and what the Rust
         equivalent of "shared, effectively-immutable-in-practice state"
         actually looks like (interior mutability patterns, or just Rc
         without RefCell since Common is conceptually frozen anyway).
- [x] **`well_spacing` — resolved 2026-08-10, folded into the generic guard
      below.** Declared on `reservoir/lumped.py` and `surface/graph.py`.
      Explicitly discussed 2026-07-23 as "less obvious" than the
      rock/thermal fields — Chad wanted to fix the unambiguous ones first
      and come back to this one. The open question (is there a legitimate
      reason `well_spacing` could differ between the reservoir's impedance
      calc and the surface's injector-to-producer pipe-run length?) is
      settled in favor of "no, treat it the same as everything else in
      `layout_extras`" — Chad's call, prompted by wanting deterministic
      guardrails robust to configs authored by AI agents, not just humans,
      after live-demoing that a component's own block silently overriding
      `well_spacing` went uncaught. See the generalized-guard entry
      immediately below — `well_spacing` gets the exact same protection
      `target_extraction_pressure` already had, via one shared mechanism
      rather than a bespoke one.
- [x] Reconciled 2026-07-22: the intern's patch (`049fdaa`/merge `123ed39`)
      only fixed `tests/test_surface_temp_pressure.py`'s path/`KeyError` bugs
      and changed its assertion to `!=` — i.e. it documented the divergence
      as accepted behavior rather than fixing `_build_components`. It never
      touched `workflow.py`. Popped this session's stash on top cleanly (no
      conflicts — disjoint files). Additionally found and fixed, mid-review:
      (1) `example_configs/SF_manual_differing_st.yml` used a dead
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
      regression in either `src/tango/` or `tango`.
- [x] **Fixed 2026-08-10 — same pattern, `target_extraction_pressure`/
      `pump_target_pressure_megapascals`.** Chad flagged this independently
      while reviewing example YAML: `SurfaceComponent.target_extraction_pressure`
      and each pump-bearing production well's own
      `pump_target_pressure_megapascals` were two independent, unvalidated
      Pydantic fields with nothing enforcing they matched — a real Rule 5
      violation, confirmed at risk in practice (matching only by manual
      diligence across 4 of 5 relevant example files). Applied the same
      "single source, threaded by `_build_components`" treatment already
      used for `well_spacing`/`dt_years` (Chad's choice: thread it through
      `layout_extras`, not the full `Common`-style shared-reference object,
      since only two component kinds ever declare it):
      1. Added `target_extraction_pressure: float` (required) to `SimConfig`
         (`core/specs.py`) — the single source.
      2. `_build_components` (`workflows/workflow.py`) threads it through
         `layout_extras` like `well_spacing`/`dt_years`, and explicitly
         rejects (`ConfigError`) a component's own YAML block setting it
         directly — a stricter guard than `well_spacing`/`dt_years` get
         today (those still silently let `own` win over `shared`; the
         still-open item above about `well_spacing` applies here too, not
         yet revisited).
      3. Renamed `pump_target_pressure_megapascals` →
         `target_extraction_pressure` on both `LumpedProductionWellWithPump`
         and `NumericalProductionWellWithPump` (`components/well/{lumped,numerical}.py`),
         dropping the now-redundant `* MPA_TO_PA` conversion (value now
         threaded in Pa directly from `sim_config`).
      4. All 5 affected example YAML files updated: the value now lives once,
         under `sim_config.target_extraction_pressure`; removed entirely
         from `components.surface` and pump-bearing well blocks.
      5. **Found and fixed a real bug the new guard exposed**:
         `Workflow.to_dict()` (`workflow.py`) dumped every component field
         except `common` back into that component's own YAML block —
         including `target_extraction_pressure`, since it's a genuine field
         on `SurfaceComponent`/pump wells. Round-tripping a `to_dict()`
         output straight back into `Workflow(...)` therefore always tripped
         the new "can't set this per-component" guard. Fixed by excluding
         `target_extraction_pressure` from `to_dict()`'s per-component dump
         too, the same way `common` already is — `sim_config:` is the only
         place it appears in a round-tripped config now. Caught by the
         existing round-trip tests (`test_workflow_from_str_to_str_roundtrip`,
         `test_workflow_to_file_from_file_roundtrip`,
         `test_workflow_sweep_pattern_does_not_mutate_base`), no new test
         needed.
      6. **Found and resolved 2026-08-10 (same session)** — separate,
         pre-existing, unrelated to this fix:
         `example_configs/SF_manual_differing_st.yml` failed to load on
         current `main`/this branch (confirmed via `git stash`, independent
         of the `target_extraction_pressure` fix) with a pydantic
         `extra_forbidden` error on `surface_temperature`/`surface_pressure`
         inside `components.surface`. Root cause: this fixture's entire
         premise (item above, "Reconciled 2026-07-22") was a *guarded*
         per-component override of `common:` (`COMMON_ONLY_KEYS`, raising a
         friendly `ConfigError` on divergence) — but that guard-list
         mechanism was itself superseded later the same day (item above,
         "SUPERSEDED 2026-07-23") by the structural single-shared-`Common`
         -object fix, under which `SurfaceComponent` simply never declares
         `surface_temperature`/`surface_pressure` as its own fields at all.
         The file's rejection was therefore *correct* under the current
         design (no per-component override of ambient state is possible,
         full stop) — the fixture's premise was just obsolete, not the code.
         Chad's call: delete it — the general "own block can't override any
         `Common` field" behavior is already covered generically by
         `test_component_own_block_rejects_shared_rock_param` (`rock_k`,
         same field group per that test's own comment block). Deleted
         `example_configs/SF_manual_differing_st.yml` and its dedicated
         `tests/test_surface_temp_pressure.py` (the only other reference,
         entirely dependent on this fixture). `tests/TemperaturePressureDiscrepancy.md`
         left in place as the historical bug-report record (not code, not
         rewritten per established practice for historical log entries).
      `uv run ruff check`, `uv run mypy src/` clean; full
      `tests/unit`+`tests/regtest` suite: same 4 pre-existing economic
      golden-value failures as before this fix (unrelated — stale from the
      run-averaged-power/parasitic-power fixes earlier this session, tracked
      separately), no new failures once the `to_dict()` fix above landed.
      7. **Follow-on, same session — generalized the per-field guard.**
         Chad's ask, after seeing the `well_spacing` divergence go uncaught
         live in a demo: since AI agents (not just humans) will be
         authoring a lot of these YAML configs, make this whole class of
         bug hard to reintroduce, not just patched for the one field that
         happened to get reported. The `if "common" in own: raise` /
         `if "target_extraction_pressure" in own: raise` blocks in
         `_build_components` were two hand-written, near-duplicate guards
         added one at a time as each bug was found — `well_spacing`/
         `dt_years` had no equivalent guard at all, purely because nobody
         had written one yet. Replaced with:
         - Module-level `_LAYOUT_EXTRA_KEYS` and
           `_PROTECTED_COMPONENT_KEYS = frozenset({"common", *_LAYOUT_EXTRA_KEYS})`
           in `workflows/workflow.py` — ONE list of "fields no component's
           own YAML block may set," checked generically
           (`_PROTECTED_COMPONENT_KEYS & own.keys()`) instead of one
           hand-written `if` per field. A future shared field is protected
           the moment it's added to this one set — no separate guard to
           remember to write.
         - `Workflow.to_dict()`'s per-component dump now excludes the same
           `_PROTECTED_COMPONENT_KEYS` set (was hardcoded to
           `{"common", "target_extraction_pressure"}` only) — otherwise
           `well_spacing`/`dt_years` would round-trip straight back into
           the new rejection, the same `to_dict()` bug found earlier this
           session for `target_extraction_pressure` alone.
         - Added a same-file `assert set(layout_extras) == set(_LAYOUT_EXTRA_KEYS)`
           in `_build_components` — guards against the *meta* version of
           this exact bug (the dict-of-values and the tuple-of-names drifting
           apart), cheap enough to always run.
         - **Found 3 more real instances of the exact bug being guarded
           against**, only surfaced because the generalized guard is
           strict where the old one was silent: `example_configs/hydro_df_electric.yml`,
           `AGS_direct_heat.yml`, and `EGS_direct_heat.yml` all redundantly
           set `well_spacing` inside `components.surface` (matching
           `layout.well_spacing` today, by manual diligence only — exactly
           the pre-guard risk profile `target_extraction_pressure` had).
           Removed all three; `well_spacing` now lives once, under
           `layout:`, same as `hydro_sf_electric.yml` already had it.
         - Full `tests/unit`+`tests/regtest` suite re-run after the YAML
           fixes: back to the same 5 pre-existing economic golden-value
           failures as before this fix (one more test passing than before,
           from `test_ags_direct_heat_smoke` — it happened to load
           `AGS_direct_heat.yml`, which had the `well_spacing` duplication)
           — no new failures. `ruff`/`mypy` clean.

## From "Active: GraphSurface p_out / pressure-provenance follow-ups"

- **Port `src/tango/`'s pressure-monotonicity validation — done 2026-07-23.**
  Added `GraphSurface._validate_pressure_monotonicity()`
  (`components/surface/graph.py`), called from `init()` right after
  `node_cfgs`/`edge_cfgs` are parsed (pure YAML-config check, no TESPy
  objects needed). Same algorithm as `flexible_pp.py`'s
  `validate_pressure_monotonicity()`: walk upstream from every node with
  a fixed `p_out_megapascals`, stopping at pressure-increasing nodes
  (`Compressor` — `tango` has no separate `Pump` type, pumps are
  `type: Compressor`), raise `ConfigError` if a downstream `p_out`
  exceeds an upstream one. Verified: (a) raises correctly on a
  deliberately-sabotaged copy of `flexible_SF_manual.yml` (turbine
  `p_out` bumped above valve's); (b) no false positive on
  `pump`/`pump2` — confirmed they're simply absent from the check's
  `p_out_values` dict since they don't declare `p_out_megapascals`
  explicitly (their pressure is solved via `Merge`'s equality
  constraint, as expected); (c) full `tests/regtest` suite still 70
  passed / 40 xfailed, no regressions. Locked in with two permanent
  tests in `tests/regtest/test_tango.py`
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
  at all — see the still-open item in "Active: GraphSurface p_out /
  pressure-provenance follow-ups") or anything else where pressure is
  implicit rather than declared.
- **Add unit comments to every `p_out`/pressure-bearing key in every
  `tango` TESPy-graph YAML file — done 2026-07-23.** Checked all 3
  `example_configs/*.yml` files with `power_plant` blocks
  (`flexible_SF_manual.yml`, `AGS_direct_heat.yml`,
  `SF_manual_differing_st.yml`). `p_out_megapascals`/`T_out` already had
  unit comments (added when these files were first written/ported — not
  actually missing). The real gap was `efficiency:` (7 occurrences) and
  `vapor_mass_fraction_out:` (2 occurrences) having no unit/scale note at
  all — added `# dimensionless [0-1] — TESPy eta_s (isentropic
  efficiency)` and `# dimensionless [0-1] — TESPy vapor quality x (0 =
  saturated liquid, 1 = saturated vapor)` respectively. Full
  `test_old_new_parity`/`test_tango.py`/
  `test_surface_temp_pressure.py` suite still green after — comment-only
  diff, confirmed via `git diff`.

## From "Backlog"

- **OPTIONAL, NO URGENCY — `InjectionPolicy.AUTO_BOTH`'s outer Picard loop
  can hit `InvalidPowerStateError` on an intermediate (not final) iterate
  near the reservoir's feasibility boundary.** Found 2026-08-13 building
  `applications/demo_auto_both_slow_convergence/` (reproduces
  the same slow-convergence case traced earlier that day — `hydro_sf_electric.yml`,
  `max_mass_rate=150`, ~34 outer iterations expected). After `d078e4e`
  ("guard against silently-invalid negative power states") landed
  same-day, this scenario now raises `InvalidPowerStateError` at outer
  iteration 2 — a pump asked to boost from well under 1 MPa up to a 7 MPa
  target, a transient/intermediate state the Picard walk passes through en
  route to its eventual answer, not the converged result itself (that
  distinguishes it from the bug `d078e4e` was actually built to catch — a
  bad *final* design silently corrupting an LCOE average).

  **Considered and explicitly rejected, 2026-08-13:**
  1. Making the Picard loop robust to bad intermediate states (damped/
     globalized stepping so it "pivots" instead of crashing).
  2. Deferring the `InvalidPowerStateError` check until final convergence
     instead of every intermediate pass — rejected specifically because
     there's no reason to trust a Picard iteration to reliably self-correct
     out of an already-wacky intermediate state; tolerating it mid-loop
     would likely just delay the same failure, not avoid it.

  **Why neither is worth building: `AUTO_BOTH` exists mainly/only for
  old-tango parity, not as a capability tango needs going forward.**
  Chad's reasoning: a real design should run one constant mass flow rate
  across its whole operational lifetime without causing fracking, not a
  yearly-adjusted one — runtime auto-control logic (which is what
  `AUTO_BOTH` effectively is, an in-simulation control loop) is out of
  scope for a techno-economic analysis tool. And critically: not-fracking
  is a CONSTRAINT, not the objective — what we actually care about is
  minimizing LCOE and maximizing power, which is exactly pymoo's job
  (`opt_*` apps), with fracking-avoidance enforced as a constraint/CV
  exception (`FrackingViolationError`, already in `pymoo_api.py`'s
  `_CV_EXCEPTIONS`) rather than something an in-simulation auto-adjustment
  loop needs to hunt for live. Consistent with `pymoo_api.py`'s own module
  docstring, which already explains why `AUTO_*` policies aren't wired
  into `Minimization` at all — `MANUAL`/`MANUAL_FRACKING_CHECK` plus
  pymoo's own search is the intended path for finding good operating
  points, not `AUTO_*`.

  Left as-is, not fixed. `demo_auto_both_slow_convergence.py` catches
  `InvalidPowerStateError` and reports it as an expected, documented
  finding rather than crashing uninformatively — revisit only if `AUTO_BOTH`
  ever needs to become more than a parity fixture.

- **PAUSED 2026-08-13 — `opt_AGS_direct_heat/` blocked on
  `DoubletEconomicComponent`'s single-diameter well-costing assumption.**
  **Correction, same day: `opt_EGS_direct_heat/` is NOT blocked by this** —
  initially claimed it would hit the same wall since it's "the same
  topology," which was wrong. Chad caught it: EGS differs from classic
  hydrothermal only in the (unmodeled) hydraulic-stimulation assumption,
  not in well plumbing. Confirmed directly: `EGS_direct_heat.yml` has no
  horizontal loop at all (its own brute-force sweep is explicitly 2-axis,
  depth × mass-flow — see `run_EGS_direct_heat_sweep/common.py`'s own
  docstring) and every well (`injection_well`/`production_well_lower`/
  `production_well_upper`) shares one fixed 0.311 m diameter — there's no
  independently-varying diameter decision variable to ever conflict with
  the economic component. Structurally `EGS_direct_heat.yml` is the same
  `injection_well -> reservoir -> production_well_lower ->
  production_well_upper -> surface` shape as `hydro_sf_electric`/
  `hydro_df_electric` (district-heat surface instead of electric) — so
  `opt_EGS_direct_heat/` should be built the simple way, mirroring
  `opt_hydro_sf_electric/`'s pattern (reuse `depth`/`mass_rate` params +
  a local thermal-power objective), NOT `opt_AGS_direct_heat`'s 4-axis
  pattern. Not blocked on the `DoubletEconomicComponent` fix below — can
  proceed independently, any time.

  Built `applications/opt_AGS_direct_heat/
  opt_AGS_direct_heat.py` (mirrors `opt_hydro_df_electric.py`'s shape;
  decision variables copied verbatim from the existing brute-force sweep's
  own axes — `run_AGS_direct_heat_sweep/common.py`'s `WELL_DEPTHS_M`/
  `LOOP_LENGTHS_M`/`LOOP_DIAMETERS_M`/`MASS_FLOW_RATES_KG_S` — plus a
  locally-defined `negative_mean_thermal_power_objective()`, since AGS is
  direct-heat (`history.net_thermal_W`, not the electric
  `negative_mean_power_objective`'s `history.net_power_W`); this objective
  belongs in the app script, not `pymoo_api.py` itself, which is
  deliberately generic — see [[feedback_pymoo_api_objectives_belong_in_app_scripts]] memory.
  One real bug fixed along the way: the first draft copied old tango's
  `sweep.py`'s `_apply_loop_length` verbatim, which also sets
  `components.surface.well_spacing` — `tango` rejects that
  (`well_spacing` is sourced only from `layout.well_spacing`, per
  `AGS_direct_heat.yml`'s own comment); fixed to set `layout.well_spacing`
  only.

  **Actual blocker, confirmed via smoke test** (`--n-max-gen 2 --pop-size
  6`): sweeping `loop_diameter` on `horizontal_well` alone (matching the
  brute-force sweep's own precedent — `production_well`'s casing diameter
  is a separate, fixed 0.311 m assumption, untouched by that axis)
  collides with `DoubletEconomicComponent._combined_production_length_and_diameter`,
  which requires all production-side wells to share one uniform diameter
  and raises a hard `ValueError` otherwise — NOT one of `pymoo_api.py`'s
  caught constraint-violation exceptions (`CoolPropError`/
  `FrackingViolationError`/`ConvergenceError`), so it crashes the whole
  NSGA2 run rather than marking one design infeasible. This is the same
  multi-segment-costing limitation already tracked below (see
  "Multi-segment well CAPEX" in "Open items — tracked, not scheduled")
  — hit here via diameter instead of length, but the same root cause.
  Since almost every candidate design has `loop_diameter != 0.311`, this
  isn't a rare corner, it fires on nearly every evaluation.

  **Chad's call (2026-08-13): pause `opt_AGS_direct_heat`, don't work
  around it.** Picking one of "drop loop_diameter as a decision variable"
  or "drop LCOE, optimize thermal power alone" would both mask the real
  gap (multi-segment well costing) rather than fix it.
  `opt_AGS_direct_heat.py` is left in place, mostly built and passing
  lint/format, but not smoke-tested end to end — do not add it to
  `just demos` until this is resolved. See the three near-term items just
  below ("Extend `DoubletEconomicComponent` for multi-diameter wells",
  "Revisit `opt_AGS_direct_heat`/build `opt_EGS_direct_heat`", "Rename
  `DoubletEconomicComponent`") for the concrete next steps. `opt_hydro_sf_electric/`
  (electric, no diameter-sweep/economic conflict) proceeded independently
  in the meantime and is done/wired into `just demos`.

- **DONE 2026-08-17 — fixed `DoubletEconomicComponent`'s well-costing so
  `opt_AGS_direct_heat/` no longer crashes on an independently-swept
  horizontal-loop diameter.** Flagged 2026-08-13, redesigned and
  implemented 2026-08-17. Per Chad's call, did NOT generalize
  `_combined_production_length_and_diameter` (`components/economic/
  doublet.py`) to handle multiple diameters — instead, a new
  `_is_horizontal()` helper (checks `NumericalWell.angle_from_vert_deg ==
  90`, defaulting to "not horizontal" via `getattr` for well types without
  that field) excludes any horizontal segment from
  `_compute_well_capex`'s production-well combination entirely, costing it
  as its own, independent `_well_section_cost()` call (own mobilization
  charge — a separate drilling operation from the vertical production
  well, not a segment of the same one). Everything else stays on the
  original single-diameter vertical-production path unchanged (which never
  actually needed multi-diameter support: `production_well_lower`/
  `production_well_upper` already share one diameter today). Also made the
  gengeo formula's three coefficients (`gengeo_quadratic_length_coeff`/
  `gengeo_diameter_length_coeff`/`gengeo_mobilization_cost_usd`) overridable
  `Field`s on the component, defaults matching the old hardcoded values.
  Open question resolved by proceeding with the documented default rather
  than blocking further: the horizontal segment reuses the SAME
  coefficients as vertical wells (no distinct horizontal-drilling formula
  exists anywhere in the ported gengeo model to begin with) — cheap to
  override per-config later if a real horizontal-specific cost basis shows
  up, via the same new `Field`s. Verified: `opt_AGS_direct_heat.py --n-max-gen
  2 --pop-size 6` runs end to end across the swept diameter; manually
  confirmed a differing horizontal-loop diameter (0.55 m vs.
  `production_well`'s fixed 0.311 m) costs correctly instead of raising;
  `tests/regtest/test_tango.py`/`test_old_new_economic_parity.py`
  (40 tests) still pass unchanged. Not the same problem as "Multi-segment
  well CAPEX" below (that one is genuinely about one well's OWN casing
  diameter varying by depth segment; this one turned out not to need
  multi-diameter costing at all once the horizontal well is treated as a
  separate asset). Still open: `opt_AGS_direct_heat` is not yet wired into
  `just demos` (see the item just below).

  **Needs revisiting: this fix is a structural special-case
  (horizontal-vs-vertical), not the general multi-diameter well-costing
  capability old tango actually had.** Chad's recollection (2026-08-17):
  old tango DID generalize to multiple OUTER/casing diameters affecting
  economics without affecting the internal flow diameter physics uses —
  this is exactly the `well_length_seq`/`well_diameter_seq` mechanism
  described in "Multi-segment well CAPEX" just below, which tango has
  never rebuilt. Today's fix works around the immediate `opt_AGS_direct_heat`
  crash by excluding the horizontal well from the combination entirely
  (treating it as a wholly separate wellbore) — it does NOT give
  tango any way to cost, say, a single vertical wellbore whose casing
  diameter genuinely changes by depth segment while its internal flow
  diameter stays one value throughout, which old tango's mechanism could
  apparently do. When "Multi-segment well CAPEX" gets built, revisit
  whether it should also subsume the horizontal/vertical split done here
  as a special case of the more general per-segment model, rather than
  leaving both mechanisms living side by side.

- **`opt_AGS_direct_heat/` unblocked (2026-08-17)** — the economic-component
  blocker above is fixed and the script smoke-tests clean end to end.
  It was later confirmed (2026-09-14 session) that `opt_AGS_direct_heat.py`
  IS wired into `justfile`'s `demos` recipe (both the `[unix]` and
  `[windows]` variants run it through its smoke path), so the "still needs
  wiring" note this bullet originally carried was stale — the wiring itself
  had already happened, just never crossed off here. `opt_EGS_direct_heat/`
  was never blocked by any of this (see the corrected note above — no
  horizontal loop, no independently-varying diameter) and can still be
  built any time, following `opt_hydro_sf_electric/`'s simple pattern
  (depth + mass_rate params, a local `negative_mean_thermal_power_objective()`
  mirroring the one already written for AGS) rather than AGS's 4-axis one
  — this part is still open, see the Backlog section above.

- **DONE 2026-08-17 — renamed `NativeEconomicComponent` to
  `DoubletEconomicComponent`, and swept "native"/"Native" out of
  tango generally.** Flagged 2026-08-13 (class rename only); Chad
  broadened it 2026-08-17 to a full sweep after `_gengeo_well_section_cost`
  → `_well_section_cost` prompted a closer look at the file itself.
  Changed: the class (`NativeEconomicComponent` → `DoubletEconomicComponent`,
  matching its own module docstring's existing "DOUBLET plant" scope) and
  its file (`components/economic/native.py` → `.../doublet.py`); the
  registry's `unit`/`type` string values that meant "the Lumped/closed-form
  model" (`"native"` → `"lumped"` for wells/reservoir, `"native"` →
  `"doublet"` for economic — including the implicit defaults in
  `workflow.py`'s `_build_components`/`_build_economic_component`); every
  example YAML's `unit: native`/`type: native` fields and their inline
  explanatory comments. Left alone, deliberately: every citation of OLD
  tango's own real class/file names (`WellUnitNative`, `EconomicUnitNative`,
  `SystemNative`, `src/tango/units/native/...` paths) — those are facts
  about a different, soon-to-be-deleted codebase, not tango's own
  naming, and changing them would misrepresent old tango's actual code.
  Also left alone: incidental correct English usage of "native" (e.g. "a
  native Python type") that isn't this naming convention at all.

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
  `docs/diagrams/src/tango/hydro_df_electric_exec_flow.drawio`,
  since that diagram's T-convergence section now describes the old
  mechanism).

  Regenerated the golden snapshot for `flexible_SF_manual.yml` (genuine
  physics change) and re-measured old-vs-new agreement: tightened as
  expected (reservoir T max delta 0.214→0.172 K, prod T 0.190→0.160 K,
  gross power 0.36%→0.26%) but didn't vanish — old tango's loop also
  converges injection *pressure* together with temperature, which
  tango's `MANUAL` policy still treats as a fixed given (see "Open
  Design Questions" → extraction pressure note in the vision doc for the
  related, still-open policy question).
- **DONE 2026-08-03 — T-convergence explainer pulled into the TANGO docs
  proper.** The mechanism (reservoir/production-well/surface-plant
  circuit, the snapshot/restore convergence loop, why the reservoir must
  be re-solved every iteration) previously only existed as a Claude
  Artifact page. Now checked into the repo: `docs/tango_t_convergence.md`
  (renders natively on GitLab, embeds two SVGs via standard markdown image
  syntax), backed by an editable `.drawio` source
  (`docs/diagrams/src/tango/t_convergence.drawio`, two pages —
  "Circuit" and "Convergence loop") with matching exported SVGs under
  `docs/diagrams/img/tango/`. The warning box in
  `hydro_df_electric_exec_flow.drawio` now points at the new doc
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
  max, mirrored into `applications/run_AGS_direct_heat_sweep/common.py`'s
  matching axis.
- **DONE 2026-07-29 — DVC pipeline + `--clean` flag + SLURM sbatch script
  added to every sweep app.** All 7 apps (`run_AGS_direct_heat_sweep`,
  `run_AGS_sweep`, `run_EGS_direct_heat_sweep`, `run_flexible_DF_manual_sweep`,
  and the three `tango/` ports) now have: a `dvc.yaml` mirroring the DF
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
  log). One of the three open design questions from the original discussion
  was resolved by this pass — **RESOLVED — `outputs/results` is tracked as a
  whole DVC `out` directory in every app**, matching the DF precedent, for
  consistency across all 7 apps. Simpler than a two-tier (aggregate-only +
  per-design-scratch) scheme, at the cost of slower `dvc repro`/`dvc
  status` on the larger grid sweeps (AGS direct-heat's 12,870-design
  grid) — acceptable for now, revisit if that becomes a real bottleneck.
  The other two design questions are still open and deliberately
  deferred, not silently dropped — see the Backlog section above.
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
     copy in `SystemDirect._update_stream`/`SystemBCIteration` — two
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
     (`SystemDirect._update_stream`, `SystemBCIteration`'s
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
  Verified: `ruff check`/`mypy src/tango` clean; full `tests/unit` +
  `tests/regtest` suite green (updated the handful of
  `Stream(..., fluid_name="water")` test constructions in
  `test_serde_roundtrip.py`/`test_tango.py` — `Common.fluid_name`
  itself is untouched and still tested).
  Not done (deliberately out of scope, not asked for): mixture/brine/
  composition support, or a typed `Fluid` object beyond the existing bare
  `Common.fluid_name` string — neither risk above needed it, and adding it
  now would be speculative.

- **`src/tango/optimizerr.py` review (2026-07-24), informing the now-built
  `pymoo_api` (see Completed Tasks → From "Next session priorities" →
  `pymoo_api` in good shape).** Read in full (1229 lines) before answering
  whether it's worth reusing. Verdict: the overall shape (`Optimizer` →
  `BaseOptimizer` → `{SOOOptimizer, MOOOptimizer}`, each defining a pymoo
  `Problem` and wiring `minimize()`) is a reasonable scaffold — but the
  plumbing inside has real problems, not just style complaints:
  - **`set_parameter()` (line 232) uses `exec(f"{param_path} = {value}")`,
    and `objective_func()` (line 134) uses `eval(target)`** to read/write
    arbitrary attribute paths built from string templates
    (`parameter_mappings.py`'s `VARIABLE_PARAMETER_MAPPING`). This is a
    genuine anti-pattern, not just ugly: no type checking, no useful error
    location, and a real (if currently low-probability, since the string
    templates are developer-authored, not user input) code-injection shape
    if that ever changes. The pattern to actually follow instead: set a
    parameter by name, extract an objective by name, with plain `Callable`
    functions operating directly on a dict.
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
  is also reasonable scope to carry forward. (Not yet confirmed whether
  ASF/pseudo-weights selection was actually carried into `pymoo_api.py` —
  check before assuming it's there.)

  **Bottom line**: not "garbage" outright — the architecture shape and
  the Pareto-selection math are worth keeping conceptually — but the
  parameter-setting/objective-extraction mechanism (eval/exec) is a real
  problem to leave behind entirely, not a style nitpick. Plain `Callable`
  functions operating on a dict is the actual pattern to follow instead.

- **Per-swept-variable scatter plots — DONE for `opt_*` (2026-08-17).**
  Flagged 2026-08-13. Every `opt_*` app now calls
  ``pymoo_api.plot_objective_vs_param_scatter`` (objective × parameter
  grid) and ``pymoo_api.plot_param_pair_vs_objective_scatter`` (parameter
  × parameter grid, colored by objective — a visual cross-correlation
  view) from its own ``main()``, writing `pareto_scatter_by_param.png`/
  `pareto_scatter_param_pairs.png`. Both are generic, shared helpers in
  `pymoo_api.py` (plain column-name lists in, no domain assumptions),
  not duplicated per app. The `run_*_sweep` half of this same ask, plus a
  low-priority statistical-cross-correlation addendum, are still open —
  see the Backlog section above.

- **DONE 2026-09-16 — assessed how many numerical cells wells actually
  need; resolved by deriving, not picking, a default.** Flagged
  2026-08-14 as "not started, needs an actual convergence study before
  picking a new default." Resolved differently than originally scoped:
  rather than a single shared fixed `num_cells` default chosen from a
  convergence sweep, `NumericalWell` now derives `num_cells` from a fixed
  target cell length (`TARGET_CELL_LENGTH_M = 250 m`, itself set from an
  existing mesh-convergence study), rounded up to the nearest 10, whenever
  `num_cells` isn't set explicitly — so discretization accuracy stays
  consistent across wells of different lengths instead of sharing one
  default that over- or under-resolves some of them. Explicit `num_cells`
  overrides still work. Dropped the redundant `num_cells: 100` line from
  all four `tango` example configs; golden snapshots and economic-
  parity values regenerated (shifted ~1e-5 relative from the changed
  discretization). Note: an earlier, differently-scoped mesh-convergence
  sweep app (`applications/demo_well_mesh_convergence/`,
  dropped `num_cells` 100 to 20 directly) was left stashed mid-session
  when a more fundamental off-by-one marching bug was found and fixed
  first — see `git stash list` on `dev/make-tango-robust`. That stashed
  work predates the off-by-one fix and this cell-length-based resolution;
  treat it as superseded, not something to pop and merge, unless
  revisiting the sweep app itself specifically.
