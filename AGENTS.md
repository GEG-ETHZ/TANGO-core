# AGENTS.md

Operating instructions for AI coding agents in the TANGO repository. `CLAUDE.md` and `GEMINI.md` point here; this file is the single source of agent instructions. It routes to the documents that own each rule and does not repeat them.

Read before any change:

1. [`.agent/rules.md`](.agent/rules.md): agent permissions, pre-approved commands, commit format, Markdown and Python rules.
2. [`CONTRIBUTING.md`](CONTRIBUTING.md): the TANGO commandments, which every code change must satisfy.
3. [`src/tango/README.md`](src/tango/README.md): how the package works.

## Repository at a glance

| Item | Value |
|---|---|
| Package | `tango` (distribution `tango-core`), Python 3.11, in `src/tango/` |
| Entry points | `tango_cli` (`run`, `validate`, `init`), `tango.workflows.workflow.Workflow` |
| Environment | `uv sync`; tasks in `justfile` |
| Checks | `just check` = ruff format, ruff lint, mypy strict, pytest |
| Code CI | GitHub Actions (`.github/workflows/tests.yml`): format check, lint, mypy, `tools/gen_reference.py --check`, and `tests/unit/` only, on macOS, Linux, and Windows |
| Docs site | Zensical (`mkdocs.yml`); `just docs` serves it at <http://127.0.0.1:8000>, `just docs-build` writes `site/`, `just docs-internal` adds the internal pages; built on GitHub by `.github/workflows/docs.yml` |
| Issue tracker | GitHub issues on `GEG-ETHZ/TANGO-core` |

## A. Using TANGO for someone

1. Ask which system they study (hydrothermal, EGS, CPG, AGS) and whether they need one run, a sweep or an optimization.
2. Start from the closest file in [`templates/`](templates/README.md). Never write a config from scratch.
3. Validate before running: `uv run tango_cli validate <config>`, then `uv run tango_cli run <config> --save-dir results/`.
4. For sweeps and optimizations, use [`applications/`](applications/README.md). Run a sweep with `--smoke` first. For an `opt_*` app, run a tiny `--n-max-gen`/`--pop-size` with a throwaway `--save-dir` first.
5. Report the LCOE together with the config and version that produced it (`uv run tango_cli --version`).

## B. Changing TANGO

### Where each fact lives

| Fact | Owner |
|---|---|
| Agent rules, permissions, commit format | `.agent/rules.md`, `.agent/rules/` |
| Code rules (object == config, LockedState, schemas, docstrings) | `CONTRIBUTING.md` |
| Setup and first run | `README.md`, `docs/guides/` |
| How the code is built and runs | `src/tango/**/README.md`, `docs/architecture/`, `docs/runtime/` |
| API | Docstrings, rendered under `docs/reference/` |
| Changes per release | `CHANGELOG.md` |
| Open work | GitHub issues, `docs/tango_tasks.md` |
| Observations outside the task | `.agent/FINDINGS.md` |
| Changes not yet shown working in a real run | `.agent/DEFERRED_VERIFICATION.md` |

### How a change moves

1. Branch off `main`. Never commit to `main` or `develop`; a hook blocks it. Agents do not commit unless the person asks ([`commit-permissions.md`](.agent/rules/commit-permissions.md)).
2. Make one logical change, with a test that fails without it.
3. Run `just check` before handing back.
4. A behavior change updates the documents that describe it in the same change: the package README and the `docs/architecture/` or `docs/runtime/` page.
5. A documentation change passes `just docs-build`. Page and diagram rules are in [`docs/AGENTS.md`](docs/AGENTS.md).
6. Diagrams are generated: edit the script in `tools/diagrams/` (or `tools/readme_assets.py` for the banner), run `just diagrams`, and commit the script with the regenerated `.drawio.svg`. `just diagrams` needs the `drawio` command line from the draw.io desktop app; without it, a `.drawio.svg` can still be opened and saved in draw.io by hand.
7. Record anything noticed outside the task in `.agent/FINDINGS.md`; do not fix it in passing.

### Things that will bite you

1. `tests/regtest/` takes over an hour. CI runs only `tests/unit/`; the pre-push hook runs the fast subset (`not slow and not perf`), and `just test --all` runs everything before a release tag.
2. A hook regenerates `src/tango.hash` on every `src/tango/` change. The DVC stages in `applications/` depend on it.
3. Every shipped example sets `sim_config.injection_mode`, so every example runs `SystemBCIteration`. `SystemDirect` runs only when the key is absent.
4. The docs site must stay private (see `NOTICE`) until tango-core goes public. The deploy job runs only when the repository variable `PAGES_PRIVATE` is `true`. Never set it without confirming Settings → Pages → Visibility: Private. The first deploy is tracked in [#74](https://github.com/GEG-ETHZ/TANGO-core/issues/74); the steps for going public, including the switch to the public build, are in [#110](https://github.com/GEG-ETHZ/TANGO-core/issues/110).
5. Links in `src/tango/**/README.md` are absolute GitHub URLs, because the site includes those files from a different path.
6. A new or renamed config field, or a changed field docstring, changes the generated docs: run `just docs-gen` and commit the result, or the CI check `tools/gen_reference.py --check` fails.

### Definition of done

1. `just check` is green.
2. The documents that describe the changed code are updated.
3. `CHANGELOG.md` has an entry if users will notice the change.
4. The change has been run for real once, or is listed in `.agent/DEFERRED_VERIFICATION.md`.
5. The person has seen the result.
