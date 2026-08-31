# Contributing

## TANGO Commandments
These are strict rules that all TANGO developers must follow.  These rules are
intended to prevent problems that TANGO users and developers have struggled
with.
1. <a id="rule-object-is-config"></a>**object == config**: All new code objects and attributes must comply with the object-is-config, config-is-object
  paradigm in which code objects and config (e.g. yaml files) have near 1:1
  congruence (exceptions could be e.g. parameter values that are derived upon
  instantiation).  Similarly, all new module structure must have reasonable
  compliance with this paradigm.
1. <a id="rule-locked-state"></a>**Mutation is guarded**: All state variables (i.e. any variables
  that mutate through temporal/time iterations) must be wrapped in
  `src/tango_next/core/locked_state.py::LockedState`, the single-value wrapper
  that enforces exactly one `update()` per time step, AND must live inside the
  component's `state` dataclass field — never as a bare `Component` attribute.
1. <a id="rule-state-history-parity"></a>**History is recordable**: All attributes in `*State` classes must have analogs in `*History`
  classes (a `list[T]` field, appended to in `record()`) — a value worth
  protecting as per-timestep state is worth keeping a time series of.
  Exception: `EconomicComponent`'s `EconomicState` has no `*History` class
  at all, since it isn't per-timestep state — the component runs exactly
  once (via `finalize()`), never through `record()`. Revisit if that
  changes.
1. <a id="rule-shared-by-reference"></a>**Single source of truth**: Any shared data that must be available within multiple objects in the
  hierarchy must be shared via reference rather than multiple, separate copies
  that can get out of sync.
1. <a id="rule-ci-checks"></a>**Deterministic quality checks**: All new code additions must pass:
    - `mypy --strict` type checking, as handled in the pyproject.toml file
    - `ruff` format checking
    - `pytest` tests

    All tests are automated through git hooks and GitLab pipelines and can optionally be run with `just check`.
1. <a id="rule-docstrings"></a>**Doc string formatting**: All doc strings must be formatted in Google style and explain what the
  documented object does, arguments, class attributes, outputs, ...
1. <a id="rule-pydantic-schemas"></a>**Schemas defined in code**: All class attributes representing simulation config or persisted/
  serialized state must be defined in pydantic schemas. Orchestration/wiring
  internals, runtime state governed by `LockedState` ([rule: LockedState](#rule-locked-state)), and framework
  primitives (e.g. `LockedState` itself) are exempt — they're never loaded
  from or dumped to config, so pydantic's validation/serialization contract
  doesn't apply to them.
1. <a id="rule-no-eval"></a>**See no `eval`**: There shall not be any `eval` functions!
1. <a id="rule-unit-conversion-factors"></a>**Unit conversions**: All unit conversion factors shall be defined in and imported from src/tango_next/core/constants.py
1. <a id="rule-finite-values-strenum"></a>**Enums for finite variants**: Any parameter that can take on a small, finite set of values should be
  handled as `StrEnum` so that we explicitly document and enforce these values.
1. <a id="rule-no-silent-pass"></a>**Guard against misused base classes**: Unimplemented base-class methods must `raise NotImplementedError` (or a
  more specific error), never a silent `pass`. A no-op placeholder is
  indistinguishable from "correctly does nothing" until someone goes
  looking, and can let real bugs run silently for a long time before
  anyone notices.
1. <a id="rule-unit-suffix-naming"></a>**Unit naming convention**: Any variable or YAML field whose value is in a non-SI unit must name that
  unit explicitly as a suffix (e.g. `p_out_megapascals`, not `p_out`) —
  converted to/from SI at the point the field is read, using the factors
  from [rule: unit conversion factors](#rule-unit-conversion-factors). Fields already in SI units (`T_out` in Kelvin, pressures in
  Pa, mass rates in kg/s, power in W, ...) need no suffix, since SI is the
  assumed default everywhere a name doesn't say otherwise. This replaces
  old tango's convention of an implicit, file-global unit (e.g. TESPy's
  `Network(p_unit='bar', ...)`, so a bare `p_out: 0.05` silently meant bar)
  with one that's self-evident from the name alone, no matter where it's
  read out of context.
1. **Document private attributes/fields**: All private attributes/fields and variables (e.g. preceded with `_` or `__`) must have an explanatory comment.
1. <a id="rule-encapsulated-mutation"></a>**Encapsulated mutation**: A class instance's fields must only be modified by the instance
  itself — via methods it defines, whether those methods are called
  internally or by external code — never by direct external assignment
  (`obj.field = value`). `state` (and `state`-shaped containers like
  `Stream`, whose own `LockedState` fields are directly `.update()`-able
  by external callers — see [rule: LockedState](#rule-locked-state)) is
  the one exception. **Not yet verified applied uniformly** — see
  `docs/tango_next_tasks.md`'s open-items list for the audit task.
1. <a id="rule-fluid-loop-needs-pressure-source"></a>**No perpetual motion machines**: Every closed fluid loop must have an explicit pump or compressor
  driving circulation somewhere in it — a downhole pump-bearing well
  (`*_with_pump`) or a surface circulation pump (a `Compressor`/`Pump`
  node in `power_plant.nodes`). Relying on thermosiphon effect (the
  density difference between a cold descending leg and a hot ascending
  leg) alone, with nothing mechanical to fall back on, is not a valid
  simplification — confirmed the hard way (2026-08-17): a pump-less AGS
  closed loop let an optimizer converge on a design whose wellhead
  pressure sat just 0.07% above the fluid's own saturation pressure, with
  no fallback once that margin ran thin. This applies to every fluid loop
  in a config, not just the first one found — a future multi-loop system
  (e.g. an ORC's secondary working-fluid loop) needs a real pressure
  source in EACH loop independently. Partially enforced today by
  `workflows/workflow.py::_check_loop_has_pressure_source` — see that
  function's own docstring for its current whole-workflow (not yet
  per-loop) scope, and revisit once multi-loop/grouped-subsystem support
  exists.

## Branching Strategy

### Persistent Branches
- `main` — production-ready code
- `develop` — integration branch for ongoing work

### Topic Branches
- `dev/<feature>` — feature branches (e.g., `dev/fix-convergence`)
- `fix/<issue>` — bug fixes
- `exp/<name>` — experimental / throwaway work

All merges into `main` must be peer reviewed via a GitLab Merge Request.
Topic branch work is normally merged into `develop` first; direct merges to
`main` require explicit sign-off from the TANGO lead developer (Chad Baker).
Case-specific work may be done directly on `develop` with lead-developer
approval.

### Branching Strategy Diagram

> **Note on diagram format**: Standard Markdown cannot embed draw.io (`.drawio`)
> files. The diagram below uses [Mermaid](https://mermaid.js.org/), which
> renders natively on GitLab, GitHub, and VS Code (with the Mermaid extension).

```mermaid
%%{init: { 'logLevel': 'debug', 'theme': 'base',
           'gitGraph': {'rotateCommitLabel': false} } }%%
gitGraph LR:
   commit id: "initial"

   branch develop
   checkout develop
   commit id: "dev work"

   branch dev/my-feature
   checkout dev/my-feature
   commit id: "feat: init"
   commit id: "feat: done"

   checkout develop
   merge dev/my-feature id: "MR: feature → develop"

   checkout main
   branch fix/hotfix
   checkout fix/hotfix
   commit id: "hotfix"
   checkout main
   merge fix/hotfix id: "hotfix MR (direct)"

   checkout develop
   merge main id: "sync from main"

   checkout develop
   branch fix/some-bug
   checkout fix/some-bug
   commit id: "fix: bug"
   checkout develop
   merge fix/some-bug id: "MR: fix → develop"

   branch exp/prototype
   checkout exp/prototype
   commit id: "e1"
   commit id: "e2"

   checkout main
   merge develop id: "release MR"
```

**Key rules encoded in the diagram:**

| Branch | Created from | Merges into | Requires MR? |
|---|---|---|---|
| `develop` | `main` | `main` | Yes |
| `dev/<feature>` | `develop` or `main` | `develop` or `main`* | Yes |
| `fix/<issue>` | `develop` or `main` | `develop` or `main`* | Yes |
| `exp/<name>` | anywhere | typically abandoned | — |

\* Direct merge to `main` requires lead-developer approval.

### Merge Requirements

**Tests must pass** before any Merge Request can be merged into `main` or `develop`.

All branches **must be up to date** with their target branch before they can be merged. This ensures that integration conflicts are resolved locally by the author.

#### Merging strategies
Depending on the target branch, use the following merge strategies:

- **Merging a topic branch (`dev/*`, `fix/*`) into `develop` or `main`**:
  - *Note: This must **always** be merged via a GitLab Merge Request.*
  1. Important: **Create a lightweight git tag** of the branch *before* merging (see [Tagging deleted branches](#tagging-deleted-branches)).
  2. Perform a **Squash merge**.
  3. Delete the source branch.
- **Merging `develop` into `main`**:
  - *Note: This must **always** be merged via a GitLab Merge Request.*
  1. Perform a **Standard merge** (often called "Merge commit" or "Create a merge commit") to preserve the squashed history of the individual features.

To enforce these rules centrally, a project **Maintainer** should apply these settings once after creating the repository. They cannot be set by Developers and should not be automated by scripts or agents.

**Settings → General → Merge requests:**

| Setting | Value |
|---|---|
| Merge method | Merge commit |
| Squash commits | Encourage |
| ☑ Pipelines must succeed | checked |
| ☑ Delete source branch | checked |

**Settings → Repository → Protected branches** — add each branch:

| Branch | Allowed to merge | Allowed to push and force push |
|---|---|---|
| `main` | Maintainers | No one |
| `develop` | Maintainers | Developers + Maintainers |

## Setup

After cloning, install the git hooks using `just setup` (or run the `prek` command directly):
```bash
just setup
# or: uv run prek install --hook-type pre-commit --hook-type pre-push --overwrite
```

## Git Hooks

Git hooks are scripts that run automatically at key points in your Git workflow (e.g. before a commit or push). We use [`prek`](https://prek.j178.dev) to manage them, providing a consistent set of checks across all contributors. This enforces code quality and prevents accidental direct commits or pushes to `main` and `develop`. We split these checks to keep your development fast:
- **`pre-commit` (auto-format as you type):** Runs fast linting and formatting (Ruff).
- **`pre-push` (test before you share):** Runs heavier validation (Mypy type checking, Pytest) only when sharing code with the remote.

To skip a specific hook for one push, set the `SKIP` environment variable to the hook's `id` (not its display name):
```bash
SKIP=pytest git push
```
This skips the "Run test suite" hook while still running Mypy. Use sparingly — bypassing tests before sharing code is rarely a good idea.

## Changelog

[`CHANGELOG.md`](CHANGELOG.md) follows the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
convention, using the standard KaC entry types:

| Category | When to use |
|---|---|
| `Added` | New user-visible functionality |
| `Changed` | Internal restructuring or behaviour change |
| `Deprecated` | Features that will be removed in a future version |
| `Removed` | Features removed in this version |
| `Fixed` | Defect corrections |
| `Security` | Security-related fixes |

Entries live under a `## [In Development]` heading at the top of the file
until a release is cut. Each `[In Development]` block may optionally note the
associated MR number in the **body** (not the heading) for traceability.

> **Public release note**: if/when this project is released publicly and adopts
> [Semantic Versioning](https://semver.org/), rename the `[In Development]`
> heading to `[Unreleased]` and update the footer link label to match. This
> aligns with the standard KaC convention and is expected by most changelog
> tooling (e.g. `git-cliff`, `standard-changelog`).

### When to add an entry

| Project phase | Merges into `develop` | Merges into `main` | Releases |
|---|---|---|---|
| **Pre-1.0** (current) | Optional | **Required** | **Required** |
| **Post-1.0** | Optional | Optional | **Required** |

**Pre-1.0 rationale**: Before the first release the changelog is the primary
record of what TANGO is becoming. Every merge into `main` represents a
meaningful, reviewable change that an end-user or future contributor will want
to understand, so an entry is expected.

**Post-1.0 rationale**: Once releases are the primary communication mechanism,
individual merges need not be documented — but every release *must* have a
complete entry so that upgrading users know exactly what changed.

### Format

The changelog is structured around **merge requests into `main`**, not releases.
Keep a `## [In Development]` stub at the very top for ongoing work. Right before a MR
is merged into `main`, convert it into a named section:

```markdown
## [In Development]

*(Nothing yet.)*

---

## MR !<N> — YYYY-MM-DD: <short title>

Optional summary paragraph.
[Link to MR !<N>](<gitlab MR URL>)

### Added
- **<Thing>** — description.

### Fixed
- **<Thing>** — description.
```

When the first public release is cut, group the relevant MR sections under a
`## [1.0.0] — YYYY-MM-DD` heading and update the [footer comparison
links](#tagging-deleted-branches) at the bottom of `CHANGELOG.md`.

### Tagging deleted branches

GitLab prunes branch refs when branches are deleted, which would break
`CHANGELOG.md` comparison links. To preserve a permanent pointer to where a
branch landed, **create a lightweight git tag immediately before deleting the
branch**:

```bash
git tag fix/some-bug                              # lightweight tag, same name as branch
git push origin refs/tags/fix/some-bug            # push the tag explicitly
git push origin --delete refs/heads/fix/some-bug  # delete branch explicitly
# (using refs/tags/ and refs/heads/ avoids ambiguity since tag and branch share the name)
```

This is a well-established practice — unlike branches, tags are static pointers
to a specific commit. This ensures the commit remains reachable even after the
branch ref disappears.

> **Convention**: prefix *release* tags with `v` (e.g. `v1.2.0`) to
> distinguish them from branch-preservation tags (e.g. `fix/some-bug`).

The `CHANGELOG.md` footer will then look like:

```markdown
[Unreleased]: https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/compare/v1.2.0...HEAD
[1.2.0]: https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/compare/v1.1.0...v1.2.0
[1.1.0]: https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/releases/tag/v1.1.0
```

---

## YAML Style

### Booleans: always `True` / `False`, never `yes` / `no`

**Always write `True` or `False`** (Python-style capitalisation) for boolean values
in all TANGO YAML files, including examples, tests, and config fixtures.

```yaml
# Wrong
check_fracing: yes
enabled: no

# Correct
check_fracing: True
enabled: False
```

**Why this matters — two separate failure modes:**

1. **`src/tango/` string-comparison trap**: several fields in `src/tango/` (e.g.
   `controlled_power_generation`, `bypass_processing`) check their value with
   `== "yes"` rather than a truthy test.  This means writing `True` in the YAML
   silently disables the feature — PyYAML parses `True` as a Python boolean, and
   `True == "yes"` is `False`.  You must write `yes` (as a string) for those
   specific `src/tango/` fields to work.  **Do not repeat this pattern in
   `tango_next`** — all boolean fields must use proper boolean types, checked
   with `if value:`, not `if value == "yes":`.

2. **YAML 1.2 forward compatibility**: YAML 1.1 (PyYAML) treats `yes`, `no`,
   `on`, `off` as booleans; YAML 1.2 (ruamel.yaml and newer parsers) does not —
   those become plain strings, causing silent mismatches if the parser is ever
   switched.

This rule applies to any file loaded by `tango_next`, including `examples/`,
`tests/`, and any input configs committed to the repo.
