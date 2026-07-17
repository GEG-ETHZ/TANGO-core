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

TODO: after doing the highest value stuff, let's discuss and revisit this
