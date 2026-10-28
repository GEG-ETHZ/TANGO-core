# Contributing to TANGO

For anyone changing TANGO's code, configs or documentation: the setup, the rules every change follows, and how a change gets from a branch to a release. TANGO is released under the Apache License 2.0 (see [`LICENSE.txt`](https://github.com/GEG-ETHZ/TANGO-core/blob/main/LICENSE.txt)); contributors are GEG members with write access to [`GEG-ETHZ/TANGO-core`](https://github.com/GEG-ETHZ/TANGO-core).

## Development setup

Python 3.11, [`uv`](https://docs.astral.sh/uv/getting-started/installation/), [`just`](https://github.com/casey/just), [gitleaks](https://github.com/gitleaks/gitleaks) and [SSH access to GitHub](https://docs.github.com/en/authentication/connecting-to-github-with-ssh).

```bash
git clone git@github.com:GEG-ETHZ/TANGO-core.git tango-core
cd tango-core
just setup        # uv sync, direnv allow, and the git hooks
```

The hooks are managed by [`prek`](https://prek.j178.dev) from [`.pre-commit-config.yaml`](https://github.com/GEG-ETHZ/TANGO-core/blob/main/.pre-commit-config.yaml). On commit: Ruff, whitespace and YAML checks, gitleaks, the `src/tango_core.hash` refresh. On push: remote freshness, mypy, the fast pytest subset, the release-tag gate. They block commits and pushes to `main` and `develop`. Skip a single hook with `SKIP=<id>`, never with `--no-verify`.

## TANGO Commandments

Binding for every change; each exists because its absence caused a real problem.

1. <a id="rule-object-is-config"></a>**object == config.** Code objects and the YAML config are congruent, close to 1:1; only values derived at instantiation are exempt.
1. <a id="rule-locked-state"></a>**Mutation is guarded.** Every value that changes across timesteps or iterations is a `LockedState` (`src/tango_core/core/locked_state.py`) inside the component's `state` dataclass, written exactly once per solve.
1. <a id="rule-state-history-parity"></a>**History is recordable.** Every `*State` field has a `list[T]` twin in the matching `*History`, appended in `record()`. Exception: `EconomicState`, which runs once through `finalize()`.
1. <a id="rule-shared-by-reference"></a>**Single source of truth.** Data several objects need is shared by reference, never copied.
1. <a id="rule-ci-checks"></a>**Deterministic quality checks.** Every change passes mypy strict, Ruff lint and format, and pytest; `just check` runs them locally, and CI runs them again on every pull request.
1. <a id="rule-docstrings"></a>**Docstrings** follow the Google style and document arguments, attributes and return values; the API reference is generated from them.
1. <a id="rule-pydantic-schemas"></a>**Schemas defined in code.** Config and persisted state are pydantic fields. Exempt: orchestration internals, `LockedState` runtime state, and framework primitives, none of which is loaded from or dumped to config.
1. <a id="rule-no-eval"></a>**No `eval`.**
1. <a id="rule-unit-conversion-factors"></a>**Unit conversions** are defined in, and imported from, `src/tango_core/core/constants.py`.
1. <a id="rule-finite-values-strenum"></a>**Enums for finite variants.** A parameter with a small, finite set of values is a `StrEnum`.
1. <a id="rule-no-silent-pass"></a>**No silent base-class methods.** An unimplemented method raises `NotImplementedError`, never `pass`.
1. <a id="rule-unit-suffix-naming"></a>**Unit suffixes.** A non-SI value names its unit (`p_out_megapascals`) and is converted where it is read; SI values carry no suffix. A file-global unit such as TESPy's `p_unit='bar'` hides the unit and is not used.
1. <a id="rule-descriptive-variable-names"></a>**No opaque short names** for physical quantities: `wellbore_diameter_m`, not `rw`, so a radius cannot be passed where a diameter is expected.
1. <a id="rule-document-private-attributes"></a>**Document private attributes.** Every `_name` has a comment.
1. <a id="rule-encapsulated-mutation"></a>**Encapsulated mutation.** Only the instance modifies its fields; external code never assigns `obj.field = value`. `state` and `Stream` fields are `.update()`d through `LockedState`. Compliance is not yet audited (`docs/tango_tasks.md`).
1. <a id="rule-yaml-booleans"></a>**YAML booleans are `True`/`False`**, never `yes`/`no`/`on`/`off`: PyYAML and YAML 1.2 parsers read those differently.
1. <a id="rule-templates-regression-covered"></a>**Every `templates/` YAML is regression-tested** by `just test --all`, against a golden value or for structural sanity; a smoke run alone does not count.

## How a change moves

| Branch | Purpose | From | Into |
|---|---|---|---|
| `main` | Release-ready; tags are cut here | — | — |
| `develop` | Integration | `main` | `main`, by pull request, as a merge commit |
| `dev/<feature>`, `fix/<issue>` | One change | `develop` or `main` | `develop`, as a squash merge; `main` only with the lead developer's sign-off |
| `exp/<name>` | Experiments | anywhere | usually abandoned |

Every merge into `main` or `develop` is a pull request with one approval and green CI (format, lint, mypy, generated-docs check, `tests/unit/`, and docs build), on a branch that is up to date with its target. Changes users will notice get a changelog entry. Branch protection and merge strategies are repository settings, set once by an admin.

Commits follow [Conventional Commits](https://www.conventionalcommits.org/), without emoji, `fix(orchestrators): reset Aitken state between timesteps`; the types and rules are in [`.agent/rules/commit-permissions.md`](https://github.com/GEG-ETHZ/TANGO-core/blob/main/.agent/rules/commit-permissions.md).

## Testing

| Command | Runs | When |
|---|---|---|
| `just check` | Format, lint, type check, fast tests, in CI order | Before every push |
| `just test` | `tests/unit/` and the fast part of `tests/regtest/` | The pre-push hook |
| `just test --all` | Everything, over an hour | Before a release tag, and before merging numerics changes |
| `just test --templates` | Every `templates/*.yml` against its golden LCOE | When a config or a model changes |
| `just apps` | A smoke run of every script in `applications/` | When an application changes |

CI runs `tests/unit/` only; the regression tier exceeds the runner's time limit. A new feature or fix comes with a test that fails without it.

## Documentation

`just docs` previews the site, `just docs-build` is what CI runs. A behavior change updates the page that describes it in the same pull request (`docs/architecture/`, `docs/runtime/`, the subpackage `README.md`). The API reference comes from docstrings; diagram rules and the palette are in [`docs/AGENTS.md`](https://github.com/GEG-ETHZ/TANGO-core/blob/main/docs/AGENTS.md); `just diagrams` regenerates the diagrams from `tools/diagrams/`.

## Large Files

Store meshes and other large binary inputs with DVC, not git: `dvc add <file>`, commit the `.dvc` file, and run `dvc push`. The `check-added-large-files` hook rejects files over 500 KB.

The one exception is `templates/raft/AGS_single.msh` (1.1 MB), the mesh of the RAFT example. It's committed to git, and excluded from `check-added-large-files`, so CI can run RAFT without DVC credentials.

## Changelog

[`CHANGELOG.md`](https://github.com/GEG-ETHZ/TANGO-core/blob/main/CHANGELOG.md) follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Entries collect under `## [In Development]` until a release is cut, then move under `## [X.Y.Z] — YYYY-MM-DD`, and the comparison links in the footer are updated. Since 1.0, an entry is required per release and optional per merge.

## Cutting an Internal (GEG-only) Release

TANGO is installed from a release tag on the private repository; nothing is published to PyPI. Versions follow [Semantic Versioning](https://semver.org/); tags carry a `v` prefix.

1. Check that `## [In Development]` covers the release.
2. Bump `version` in `pyproject.toml` on `main` through a pull request. Its `license-check` job (`tools/check_licenses.py`) fails if a runtime dependency's license is not allowed; do not tag until it passes. Review each flagged license (the job uploads `licenses.json` and a draw.io dependency tree) and either replace the dependency or add a `REVIEWED_PACKAGES` entry in `tools/check_licenses.py` giving the reason, through its own pull request.
3. Tag that commit and push the tag; the pre-push hook runs `just test --all` first and blocks a failing tag. Never reuse a version number.

   ```bash
   git checkout main && git pull
   git tag v1.0.1
   git push origin refs/tags/v1.0.1
   ```

4. Create a GitHub Release from the tag (`gh release create v1.0.1 --notes-from-tag`) with the changelog section as its notes, and tell consumers which tag to pin.
