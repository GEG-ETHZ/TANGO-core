# Repo Cleanup Audit — tango-core

Generated 2026-07-16. This is a working document, not part of the permanent docs set — delete once acted on (or move into `memory/`/an issue if you want it preserved).

## Guidelines used to make keep/remove calls

Per instructions, each file/directory below was assessed against:

1. **Config files unused by anything** — checked against `tests/`, the web app in `~/git/projects/tango-super` (including `tango_app/`), `examples/`, and `applications/` via grep for references.
2. **Deprecated documentation** — docs superseded by a newer doc, pointing at nonexistent files, or describing a toolchain no longer in use.
3. **Staleness** — anything not touched by a git commit in the last year (before 2025-07-16), as a *signal*, not an automatic verdict — static fixture data is expected to be old and isn't penalized just for that.

Verdicts: **KEEP**, **REMOVE**, **UNSURE** (needs a decision from you), **ACTION** (not a file to delete, but a `.gitignore`/config fix).

---

## Directory tree with verdicts

```
tango-core/
├── src/                                    KEEP — current package, wired into pyproject.toml
│   ├── tango/                              KEEP — main package, actively developed (touched 2026-07-15)
│   │   ├── aaaa.csv, alpha.csv             REMOVE — scratch/debug files with no imports, ship in every wheel
│   │   ├── fff.xlsx, ggg.xlsx              REMOVE — same as above
│   │   ├── connections1.json, connections2.json,
│   │   │   connections_test2.json          REMOVE — orphaned debug artifacts (not the same as
│   │   │                                     thermagraph_connections.json, which IS used)
│   │   ├── states1.json, states2.json,
│   │   │   states_test2.json               REMOVE — orphaned debug artifacts
│   │   ├── conda_and_pip_package_licenses.csv REMOVE — duplicate of root-level file actually
│   │   │                                     consumed by license_check.py; this in-package copy
│   │   │                                     is dead weight
│   │   └── [rest of package: core/, units/, orchestrators/, workflows/, addons/,
│   │        interfaces/, models/, *.py]    KEEP — active source
│   ├── tango_next/                         KEEP — in-progress rewrite, active work per memory
│   └── tango.egg-info/                     OK — build artifact, not tracked by git, no action
├── source/                                 REMOVE (whole dir) — orphaned Sphinx doc-source tree.
│   │                                          Not legacy app code, just *.rst API-doc stubs +
│   │                                          conf.py. Currently broken: .readthedocs.yml points
│   │                                          at docs/conf.py, which doesn't exist. tox.ini's docs
│   │                                          env points at docs/requirements.txt, which also
│   │                                          doesn't exist. Dormant since ~2024-12/2025-02.
│   │                                          Remove together with .readthedocs.yml, tox.ini,
│   │                                          make.bat unless you want to revive Sphinx API docs.
│   └── *.rst, conf.py, index.html          REMOVE (all ~65 files)
├── docs/                                   KEEP — hand-written markdown design docs, active
│   ├── TANGO_vision_and_roadmap.md         KEEP — primary vision doc, touched 2026-07-15
│   ├── refactor-for-congruency.md          KEEP — recent, active refactor work
│   ├── state-management-framework-eval.md  KEEP — recent, active refactor work
│   ├── architecture/runner_data_ingestion.drawio  KEEP — recent design diagram
│   ├── diagrams/*.svg + diagrams/src/*.drawio     KEEP — paired source/export diagrams
│   ├── diagrams/src/.$*.drawio.bkp (untracked, 4 files)  REMOVE — draw.io autosave/crash-recovery
│   │                                          litter; ACTION: add "*.bkp" or ".$*.drawio.bkp" to
│   │                                          .gitignore so this stops recurring
│   ├── .DS_Store                           REMOVE — untracked Finder metadata, no action needed
│   │                                          beyond confirming .gitignore already covers it
│   └── diagrams/.DS_Store                  same as above
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
│         tracked under DF_manual_sweep)    ACTION — add "applications/*/outputs/" to .gitignore;
│                                              these are generated sweep results (plots/CSVs), not
│                                              source, and the DF_manual_sweep copy should likely
│                                              be untracked too (or is deliberately DVC-tracked —
│                                              check dvc.yaml/dvc.lock in that dir before removing)
├── config/                                 KEEP — arangodb.conf(.example), used by
│                                              src/tango/workflows/arangodb_manager.py
├── data/                                   KEEP — cost/PPI/ORC lookup tables used by surface-unit
│                                              cost models; stale-by-date (2023) but load-bearing,
│                                              not dead
├── memory/ (untracked)                     ACTION — this is the Claude Code memory directory;
│                                              should be gitignored, not left as an untracked
│                                              working-tree item
├── .agent/                                 KEEP — cross-tool AI agent rules, referenced in
│                                              CHANGELOG, actively used
├── .gitlab/issue_templates/issue.md        KEEP — GitLab issue template, matches GitLab MR
│                                              workflow documented in CLAUDE.md
├── .helix/                                 UNSURE — Helix editor config; legitimate if the team
│                                              uses Helix (justfile has a `hx .` task) but is
│                                              editor preference rather than project-necessary.
│                                              Low priority either way — your call.
├── .claude/                                OK — untracked local settings, working as intended,
│                                              no action
├── CHANGELOG.md                            KEEP — actively maintained, Keep-a-Changelog format
├── CONTRIBUTING.md                         KEEP — current, matches CLAUDE.md conventions
├── README.md                               KEEP — current
├── ONBOARDING.md                           UNSURE — content is NOT onboarding material; it's an
│                                              auto-generated "How We Use Claude" personal usage-
│                                              stats dump (work-type breakdown, top skills/commands
│                                              for Chad Baker). Looks like it was committed by
│                                              accident from a Claude Code report generator.
│                                              Recommend rewriting with real onboarding content or
│                                              deleting — as-is it exposes personal usage stats and
│                                              doesn't help a new team member.
├── TODO.md                                 KEEP — actively maintained task list, touched
│                                              2026-05-13, not duplicative of CHANGELOG
├── CLAUDE.md (untracked)                   ACTION — should be committed; it's the project
│                                              instructions file, clearly meant to be tracked
├── LICENSE.txt                             KEEP
├── check_licenses.py                       KEEP — consumes licenses.json
├── licenses.json                           KEEP — consumed by check_licenses.py
├── conda_and_pip_package_licenses.csv      KEEP — consumed by src/tango/license_check.py (root
│                                              copy is the real one; see src/tango/ dupe above)
├── components.json                         REMOVE — zero references anywhere in src/, tests/, or
│                                              the sibling tango-super repo (checked tango_app/
│                                              frontend too). Not the same file as
│                                              thermagraph_connections.json, which is in-use.
├── connections.json                        REMOVE — same as components.json, zero references
├── diagram.svg                             UNSURE — root-level orphan SVG (2024-12-15), not
│                                              referenced by code, duplicative of the properly
│                                              organized docs/diagrams/ set. Likely removable but
│                                              confirm nothing external links to it.
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
├── .pixi/ (untracked) + pixi.lock          UNSURE — pixi is a second, parallel toolchain still
│                                              wired into pyproject.toml's [tool.pixi.*] and
│                                              README/CHANGELOG ("both pixi run and uv run
│                                              confirmed working"). Not dead, but redundant with
│                                              uv. Flag for a team decision: consolidate on one.
├── setup.py                                REMOVE — PyScaffold-era shim, bare setup() call,
│                                              fully superseded by pyproject.toml's
│                                              [build-system] setuptools.build_meta
├── setup.cfg                               REMOVE — PyScaffold-generated legacy config,
│                                              superseded by pyproject.toml + pytest.ini + ruff
│                                              config; also references a nonexistent README.rst
├── tox.ini                                 REMOVE — legacy PyScaffold tox config, stale since
│                                              2022-11-22, superseded by uv + justfile
├── make.bat                                REMOVE — Sphinx-generated Windows doc-build helper,
│                                              paired with the orphaned source/ + .readthedocs.yml
│                                              setup
├── .readthedocs.yml                        REMOVE — points at docs/conf.py, which does not
│                                              exist (only source/conf.py does); currently broken
│                                              as configured. Remove alongside source/, or fix if
│                                              you actually want ReadTheDocs API docs revived.
├── requirements.txt                        REMOVE — pinned old conda-build hashes incl. a
│                                              self-referencing -e git+...TANGO5.git line;
│                                              superseded by uv.lock/pyproject.toml
├── flask_requirements.txt                  REMOVE — superseded by pyproject.toml's
│                                              [project.optional-dependencies] tango-app group
├── .coveragerc                             UNSURE — stale since 2022-11-22, no --cov usage
│                                              found in current CI/justfile; likely vestigial
│                                              from setup.cfg-era pytest-cov. Probably removable.
├── test.py (root)                          REMOVE — stray root-level file outside tests/; not
│                                              collected by pytest (testpaths = tests), looks like
│                                              an accidentally committed debug script
├── output.prof (untracked)                 ACTION — cProfile binary output, delete + add
│                                              "*.prof" to .gitignore
├── scratch (untracked)                     ACTION — ad hoc working file, delete or move to your
│                                              scratchpad convention, not repo-appropriate
├── deployment_analysis_questions.md
│   (untracked)                             UNSURE — looks like a scratch note from a recent
│                                              analysis session; keep only if still needed
├── tango_diagramming_workflow.md
│   (untracked)                             UNSURE — personal process note from the diagram
│                                              migration effort; keep only if it documents a
│                                              repeatable workflow, otherwise move to memory/ or
│                                              delete
├── .aider.chat.history.md,
│   .aider.input.history,
│   .aider.tags.cache.v4/  (untracked)      REMOVE — Aider CLI tool artifacts, already covered
│                                              by .gitignore's `.aider*` pattern, just clear them
│                                              from the working tree
└── .DS_Store (root, untracked)             REMOVE — Finder metadata, no action needed beyond
                                               confirming .gitignore coverage
```

---

## Highest-value cleanup, in priority order

1. **Remove the legacy PyScaffold/Sphinx doc toolchain as one coherent unit**: `setup.py`, `setup.cfg`, `tox.ini`, `requirements.txt`, `flask_requirements.txt`, `make.bat`, `.readthedocs.yml`, `source/` (~65 files). All superseded by `pyproject.toml` + `uv` + hand-written `docs/`, and the doc-build config is currently broken anyway.
2. **Clean debug/scratch junk shipping inside the actual package**: `src/tango/aaaa.csv`, `alpha.csv`, `fff.xlsx`, `ggg.xlsx`, `connections1/2/_test2.json`, `states1/2/_test2.json`, `conda_and_pip_package_licenses.csv` (dupe).
3. **Remove orphaned root-level JSON**: `components.json`, `connections.json` — verified zero references in tango-core or the sibling `tango-super` web app.
4. **Add missing `.gitignore` entries**: `applications/*/outputs/`, `docs/diagrams/src/.$*.drawio.bkp`, `*.prof`, `memory/`.
5. **Fix or replace `ONBOARDING.md`** — currently contains personal Claude Code usage stats instead of onboarding content.
6. **Decide on pixi vs. uv** — both toolchains are live and documented (`pyproject.toml` `[tool.pixi.*]`, `pixi.lock`, README/CONTRIBUTING both mention `pixi run`). Consolidating on `uv` alone would remove real redundancy, but this is a team call, not a unilateral cleanup.
7. **Commit `CLAUDE.md`** — currently untracked despite being the canonical project-instructions file.

## Staleness note

383 of 720 git-tracked files haven't been touched in over a year. The bulk of that (~230 files) is `examples/*` static fixture data and (~65 files) `source/*.rst` Sphinx stubs — expected/consistent with the findings above, not an independent red flag beyond what's already called out.
