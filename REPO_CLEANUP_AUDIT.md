# Repo Cleanup Audit — tango-core

Generated 2026-07-16. This is a working document, not part of the permanent docs set — delete once acted on (or move into `memory/`/an issue if you want it preserved).

## Guidelines used to make keep/remove calls

Per instructions, each file/directory below was assessed against:

1. **Config files unused by anything** — checked against `tests/`, the web app in `~/git/projects/tango-super` (including `tango_app/`), `examples/`, and `applications/` via grep for references.
2. **Deprecated documentation** — docs superseded by a newer doc, pointing at nonexistent files, or describing a toolchain no longer in use.
3. **Staleness** — anything not touched by a git commit in the last year (before 2025-07-16), as a *signal*, not an automatic verdict — static fixture data is expected to be old and isn't penalized just for that.

Verdicts: **KEEP**, **REMOVE**, **OK** (correctly left as-is, no action), **UNSURE** (needs a decision from you), **ACTION** (not a file to delete, but a `.gitignore`/config fix).

**Status (2026-07-16): items 1–7 below have been executed.** See each line's verdict for what happened; anything still marked UNSURE was intentionally left for discussion.

---

## Directory tree with verdicts

```
tango-core/
├── src/                                    KEEP — current package, wired into pyproject.toml
│   ├── tango/                              KEEP — main package, actively developed (touched 2026-07-15)
│   │   ├── aaaa.csv, alpha.csv             DONE — removed (git rm)
│   │   ├── fff.xlsx, ggg.xlsx              DONE — removed (git rm)
│   │   ├── connections1.json, connections2.json,
│   │   │   connections_test2.json          DONE — removed (git rm); confirmed distinct from
│   │   │                                     thermagraph_connections.json, which stays (in use)
│   │   ├── states1.json, states2.json,
│   │   │   states_test2.json               DONE — removed (git rm)
│   │   ├── conda_and_pip_package_licenses.csv DONE — removed (git rm); confirmed the root-level
│   │   │                                     copy consumed by license_check.py is untouched
│   │   ├── license_check.py                DONE — moved to `tools/check_licenses.py` and merged
│   │   │                                     with the old root-level check_licenses.py; wasn't
│   │   │                                     imported by any package code, so it never belonged
│   │   │                                     inside src/tango/ in the first place
│   │   └── [rest of package: core/, units/, orchestrators/, workflows/, addons/,
│   │        interfaces/, models/, *.py]    KEEP — active source
│   ├── tango_next/                         KEEP — in-progress rewrite, active work per memory
│   └── tango.egg-info/                     OK — build artifact, not tracked by git, no action
├── source/                                 DONE — removed (git rm -r, ~65 files: *.rst, conf.py,
│                                              index.html), along with .readthedocs.yml, tox.ini,
│                                              make.bat. Added a note to
│                                              docs/TANGO_vision_and_roadmap.md flagging that a
│                                              real API-doc generation process is still needed.
├── docs/                                   KEEP — hand-written markdown design docs, active
│   ├── TANGO_vision_and_roadmap.md         KEEP — primary vision doc, touched 2026-07-15
│   ├── refactor-for-congruency.md          KEEP — recent, active refactor work
│   ├── state-management-framework-eval.md  KEEP — recent, active refactor work
│   ├── architecture/runner_data_ingestion.drawio  KEEP — recent design diagram
│   ├── diagrams/*.svg + diagrams/src/*.drawio     KEEP — paired source/export diagrams
│   ├── diagrams/src/.$*.drawio.bkp (untracked, 4 files)  DONE — deleted; `docs/diagrams/src/.$*.bkp`
│   │                                          added to .gitignore so this stops recurring
│   ├── .DS_Store                           OK — untracked, .gitignore already covers it
│   └── diagrams/.DS_Store                  OK — same as above
├── tests/                                  KEEP — active pytest suite (unit/ + regtest/)
├── examples/  (132 items)                  KEEP (directory) — mix of active test fixtures
│   │                                          (flexible_SF_manual.yml, tango_next/, MVP_templates/,
│   │                                          referenced by tests/regtest/*.py) and a long tail of
│   │                                          historical run configs (TANGO_paper/, EGC2025*/,
│   │                                          Martin_AGS/, AGS_new/, numbered testcaseN.yml).
│   │                                          Cheap to keep, no broken/orphaned files found in
│   │                                          spot check. Consider a subfolder reorg later
│   │                                          (not urgent, not a keep/remove call).
│   └── .gitignore                          KEEP
├── applications/                           KEEP (directory) — demo sweep scripts, actively
│   │                                          developed (see recent "feat(ags-sweep)" commits),
│   │                                          not referenced by tests but that's expected —
│   │                                          they're standalone analysis entry points
│   ├── run_AGS_direct_heat_sweep/          KEEP
│   ├── run_EGS_direct_heat_sweep/          KEEP
│   ├── run_flexible_DF_manual_sweep/       KEEP
│   └── */outputs/  (untracked in AGS/EGS,
│         tracked under DF_manual_sweep)    DONE — DF_manual_sweep's outputs/ is deliberately
│                                              DVC-managed (dvc.yaml/dvc.lock confirmed) and
│                                              already correctly gitignored. AGS/EGS each already
│                                              had a correct local outputs/.gitignore
│                                              (`*` / `!.gitignore`) sitting on disk untracked —
│                                              `git add`ed both so the pattern actually takes
│                                              effect; no root .gitignore change needed.
├── config/                                 KEEP — arangodb.conf(.example), used by
│                                              src/tango/workflows/arangodb_manager.py
├── data/                                   KEEP — cost/PPI/ORC lookup tables used by surface-unit
│                                              cost models; stale-by-date (2023) but load-bearing,
│                                              not dead
├── memory/ (untracked)                     DONE — `memory/` added to .gitignore
├── .agent/                                 KEEP — cross-tool AI agent rules, referenced in
│                                              CHANGELOG, actively used
├── .gitlab/issue_templates/issue.md        KEEP — GitLab issue template, matches GitLab MR
│                                              workflow documented in CLAUDE.md
├── .helix/                                 KEEP — Helix editor config; at least part of the team
│                                              uses Helix (justfile has a `hx .` task)
├── .claude/                                OK — untracked local settings, working as intended,
│                                              no action
├── CHANGELOG.md                            KEEP — actively maintained, Keep-a-Changelog format
├── CONTRIBUTING.md                         KEEP — current, matches CLAUDE.md conventions
├── README.md                               KEEP — current
├── ONBOARDING.md                           KEEP — content is NOT onboarding material; it's an
│                                              auto-generated "How We Use Claude" personal usage-
│                                              stats dump (work-type breakdown, top skills/commands
│                                              for Chad Baker). It's a bit haphazard but was deliberately added
├── TODO.md                                 KEEP — actively maintained task list, touched
│                                              2026-05-13, not duplicative of CHANGELOG
├── CLAUDE.md (untracked)                   OK — deliberately untracked
├── LICENSE.txt                             KEEP
├── check_licenses.py                       DONE — moved to `tools/check_licenses.py`, merged
│                                              with `src/tango/license_check.py` (see below) into
│                                              one script. The old `license_check.py` sourced
│                                              packages from a hardcoded, machine-specific
│                                              `/Users/morteza/.../environment.yml` that doesn't
│                                              exist in this repo — replaced with
│                                              `importlib.metadata` so it reads whatever's actually
│                                              installed. Fixed a bug along the way: newer packages
│                                              (PEP 639) only populate `License-Expression`, not
│                                              the legacy `License` field, which was silently
│                                              producing "Unknown" for ~half of dependencies.
├── licenses.json                           DONE — moved to `tools/licenses.json`, regenerated
├── conda_and_pip_package_licenses.csv      DONE — moved to `tools/conda_and_pip_package_licenses.csv`,
│                                              regenerated from the same data as licenses.json
│                                              (previously these two files came from unrelated,
│                                              disconnected generation paths and could silently
│                                              drift out of sync with each other)
├── components.json                         DONE — removed (git rm); confirmed zero references
│                                              anywhere in src/, tests/, or the sibling
│                                              tango-super repo (checked tango_app/ frontend too).
│                                              Not the same file as thermagraph_connections.json,
│                                              which stays (in use).
├── connections.json                        DONE — removed (git rm), same rationale as above
├── diagram.svg                             DONE — removed (git rm)
├── tango-logo.svg                          KEEP — recently added (2026-07-04), used by README
├── tango_flask_server.py                   KEEP — active backend for the tango_app React
│                                              frontend in the sibling tango-super repo, touched
│                                              2026-07-04
├── start_flask_server.sh                   KEEP — launcher for the above
├── server_output/                          OK — correctly gitignored runtime output, no action
├── justfile                                KEEP — current task runner
├── pyproject.toml                          KEEP — current build/dependency config
├── pytest.ini                              KEEP — current test config
├── uv.lock                                 KEEP — current lockfile
├── .envrc                                  KEEP — direnv hook for uv-based env activation
├── .pixi/ (untracked) + pixi.lock          DONE — kept, pixi stays supported; `.pixi/` added to
│                                              .gitignore
├── setup.py                                DONE — removed (git rm)
├── setup.cfg                               DONE — removed (git rm); dropped the now-dead
│                                              `!setup.cfg` exception from .gitignore too
├── tox.ini                                 DONE — removed (git rm)
├── make.bat                                DONE — removed (git rm)
├── .readthedocs.yml                        DONE — removed (git rm), alongside source/. Added a
│                                              note to docs/TANGO_vision_and_roadmap.md
│                                              (Miscellaneous section) that a real API-doc
│                                              generation process is still an open item.
├── requirements.txt                        DONE — removed (git rm)
├── flask_requirements.txt                  DONE — removed (git rm)
├── .coveragerc                             DONE — removed (git rm)
├── test.py (root)                          DONE — removed (git rm)
├── output.prof (untracked)                 DONE — deleted; `*.prof` added to .gitignore
├── scratch (untracked)                     DONE — deleted
├── deployment_analysis_questions.md
│   (untracked)                             OK — looks like a scratch note from a recent
│                                              analysis session; keep as untracked
├── tango_diagramming_workflow.md
│   (untracked)                             OK — personal process note from the diagram
│                                              migration effort; keep as untracked
├── .aider.chat.history.md,
│   .aider.input.history,
│   .aider.tags.cache.v4/  (untracked)      DONE — cleared from working tree (already covered by
│                                              .gitignore's `.aider*` pattern so won't recur)
└── .DS_Store (root, untracked)             DONE — deleted; .gitignore already covers it
```

---

## Highest-value cleanup, in priority order

1. ✅ **DONE — Removed the legacy PyScaffold/Sphinx doc toolchain as one coherent unit**: `setup.py`, `setup.cfg`, `tox.ini`, `requirements.txt`, `flask_requirements.txt`, `make.bat`, `.readthedocs.yml`, `source/` (~65 files).
2. ✅ **DONE — Cleaned debug/scratch junk shipping inside the actual package**: `src/tango/aaaa.csv`, `alpha.csv`, `fff.xlsx`, `ggg.xlsx`, `connections1/2/_test2.json`, `states1/2/_test2.json`, `conda_and_pip_package_licenses.csv` (dupe).
3. ✅ **DONE — Removed orphaned root-level JSON**: `components.json`, `connections.json`.
4. ✅ **DONE — Added missing `.gitignore` entries**: `applications/*/outputs/` (handled via each dir's own local `outputs/.gitignore`, now tracked), `docs/diagrams/src/.$*.bkp`, `*.prof`, `memory/`, `.pixi/`. Also cleared out other untracked litter (`output.prof`, `scratch`, `.aider.*`, root `.DS_Store`, drawio `.bkp` files).
5. **SKIPPED (overruled) — `ONBOARDING.md`** — you marked it KEEP; the "How We Use Claude" content was deliberate, not accidental. Left untouched.
6. ✅ **DECIDED — pixi vs. uv**: keep pixi supported (some team members use it); `.pixi/` is now gitignored so it stays local-only and doesn't get accidentally committed. `pixi.lock` stays tracked.
7. **SKIPPED (overruled) — Commit `CLAUDE.md`** — you marked it deliberately untracked. Left untouched.

Bonus: added a note to `docs/TANGO_vision_and_roadmap.md` (Miscellaneous section) that a real API-doc generation process is still an open item, per your note.

## Staleness note

383 of 720 git-tracked files haven't been touched in over a year. The bulk of that (~230 files) is `examples/*` static fixture data and (~65 files) `source/*.rst` Sphinx stubs — expected/consistent with the findings above, not an independent red flag beyond what's already called out.

✅ **DONE — objective validity signal instead of staleness-by-date**: ran every `examples/*.yml` through `tools/sweep_examples.py` (see its own docstring). Result (2026-07-20, `tools/examples_sweep_output/sweep_20260720_101252.md`): 24 configs deleted (irrecoverably stale — missing required fields, deprecated unit paths, abandoned placeholder values), 2 real code bugs fixed (`parameter_mappings.py` `workflow.results` typo, 3 CSV file-reader path bugs), and 75 configs now auto-categorized `EXPECTED_FAIL` for documented, non-mysterious reasons rather than showing up as noise — see `KNOWN_UNSUPPORTED_MARKERS` in `tools/sweep_examples.py` for the exact logic.

## Backlog: `EXPECTED_FAIL` configs blocked on external dependencies (not urgent, revisit later)

These are correctly *not* deleted — each is blocked on something outside this repo's control, not dead. Listed here so they don't quietly get re-litigated from scratch next time someone runs the sweep and sees a big EXPECTED_FAIL count.

- **~55 configs need an external MOOSE + moskito2 install** (`examples/AGS_new/`, `examples/EGC2025/`, `examples/Martin_AGS/`, `examples/cever1-10.yml`, `examples/TANGO_paper/CO2_6b.yml`/`H2O_6b.yml`, `examples/MOOSE_Tespy examples/`). Deeper than example-YAML hardcoded paths — `src/tango/units/dataclasses.py` hardcodes `moose_executable_path` *defaults* to a former contributor's machine (lines 162, 250). Decide: get a MOOSE toolchain working in CI/dev envs and make the executable path configurable (env var or repo-relative), or accept these stay permanently un-runnable here and say so explicitly in the examples themselves.
- **4 configs need PyQt5 or hit a hardcoded personal path** (`examples/TANGO_paper/CPG.yml`, `examples/EGC2025_EGS/EGS_reader{10,50,100}.yml`). `ThermaGraph_interface.py`'s docstring claims a headless SVG batch mode exists but `execute()` always imports PyQt5 and launches a GUI regardless — worth fixing properly (`uv sync --group tango-app` is already the intended opt-in dependency group) since a real batch mode would make ThermaGraph usable in CI. Analyzer's `results_file` path is a simpler one-line fix (make it configurable/relative).
- **3 configs use the deprecated `BatchSimulation` feature** (`flexible_CPG_manual_batch.yml`, `flexible_SF_batch_opt.yml`, `flexible_SF_batch_simulation.yml`). Decided not to fix the underlying code (undocumented, grid-only sampling, currently broken on a missing-arg bug) — plan is to port these 3 configs to standalone DOE scripts (see `applications/*_sweep/` for the pattern) and then delete the feature + these configs from `examples/`.
- **1 config with a hardcoded path and no override at all**: `examples/flexible_heat_district_runner.yml` / `flexible_heat_district_reader.yml` trigger `Orchestrator.hotmapsdispatch_runner()` (`src/tango/orchestrators/external.py:164`), which has a former contributor's absolute path as a string literal in the function body — not even config-driven. Needs a real parameter added before this is fixable at all.

## Backlog: `TIMEOUT` configs from the sweep (300s budget), excluding confirmed-working ones

Same 2026-07-20 sweep also flagged 31 configs as `TIMEOUT`. **10 of those are confirmed fine** — each has independently verified as completing well under a longer budget (re-run at 900s on 2026-07-17, or standalone with zero contention for `flexible_SF_manual.yml`, which finished in 130s): `MVP_templates/flexible_DF_manual.yml` (803s), `flexible_CPG_hot_opt.yml` (453s), `flexible_ORC_back.yml` (574s), `flexible_ORC_manual.yml` (494s), `flexible_SF_doublet.yml` (646s), `flexible_SF_inverted.yml` (571s), `flexible_SF_manual.yml` (130s standalone), `flexible_heat_district_reader.yml` (494s), `flexible_pp_cost_breakdown.yml` (781s), `flexible_pp_cost_entire.yml` (770s). These just need `tools/sweep_examples.py`'s default timeout raised (or accept they'll show TIMEOUT under the current 300s budget) — not a real problem, no action needed on the configs themselves.

3 more (`TANGO_paper/Hydrothermal_single_flash.yml`, `Single_flash_cogeneration_e.yml`, `Single_flash_cogeneration_h.yml`) are already covered above — they finish the actual simulation (445-523s) and only fail afterward on the PyQt5/Analyzer addon issue, so they'll keep showing as TIMEOUT under a 300s budget even though the real story is the addon backlog item above, not a hang.

**The remaining 17 are the genuine backlog**, split by confidence:

- **14 confirmed to still time out even at a 900s budget** (re-run 2026-07-17): `MO4.yml`, `SO2.yml`, `TANGO_paper/Hydrothermal_double_flash.yml`, `TANGO_paper/Hydrothermal_double_flash_optimised.yml`, `TANGO_paper/multi_objective_optimization.yml`, `flexible_DF_doublet.yml`, `flexible_DF_inverted.yml`, `flexible_DF_manual.yml`, `flexible_DF_opt_valves.yml`, `flexible_DF_reader.yml`, `flexible_ORC_doublet.yml`, `flexible_ORC_inverted.yml`, `flexible_SF_opt_mass_rate.yml`, `flexible_SF_opt_valve.yml`. Worth noting: the entire `flexible_DF_*` (double-flash) family times out consistently, including non-optimization variants (`_doublet`, `_inverted`, `_manual`, `_reader`) — that's a suspicious pattern pointing at something specific to the DF topology's solver, not "optimization is just slow" (which would explain `MO4`/`SO2`/`multi_objective_optimization`/`*_opt_*` on its own, but not the plain DF ones). Worth a real look before assuming it's just a slow config.
- **3 with no data point yet** (new to the TIMEOUT list this run, never re-tested at a longer budget): `flexible_SF_cogeneration_e.yml`, `flexible_SF_cogeneration_h.yml`, `flexible_SF_manual_cost.yml`. Cheapest next step: re-run just these 3 with a longer timeout before assuming they belong in either bucket above.

Also flagged, different kind of oddity, not really a "timeout": `examples/failing/flexible_SF_manual_playground.yml` lives in the directory reserved for configs that are *supposed* to fail, but it actually passes once given enough time (375s, confirmed 2026-07-17) — `UNEXPECTED_PASS` in sweep terms. Worth a look at why it no longer demonstrates whatever failure mode it was built to show.

TODO: after doing the highest value stuff, let's discuss and revisit this
