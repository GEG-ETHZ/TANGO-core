# Design

## Context

- **RAFT** is the existing precedent. `src/tango_core/external/raft_wrapper.py` is the only module importing `geg_raft`, lazily, turning `ImportError` into a `ConfigError` with the install command. RAFT is a uv dependency group (`raft`) pinned to a tag of its public repository in `[tool.uv.sources]`. Unit tests use a stand-in for RAFT; a separate CI job runs one simulated year on the real package. The wrapper checks only what crosses the interface (boundary values, mass rate in vs. out) and records RAFT's interior fields without judging them.
- **`.agent/rules/external-coupling.md`** states the principles learned with RAFT: TANGO owns the interface; check only at the interface; never change the other package's setup silently; never edit the other package, and report problems to its developer; describe its physics from its own documentation.
- **RevORC** (`add-revorc-coupling`) is the first model coupled with a written plan. Its package, as first published, had none of the readiness items below. The work to fix that was proposed to its authors as an OpenSpec change and pull requests in their repository, before any TANGO code.
- **FlexGEO** brings five more models, from teams that are geoscientists and engineers rather than software developers. Integration contacts and status are tracked outside TANGO (the FlexGEO repository).

## Goals / Non-Goals

**Goals:**

- Anyone starting a new coupling knows what to ask the authors for, what to build in TANGO, and when the coupling is done.
- The external model stays its authors' model: they own its physics and its code; TANGO depends on their releases.
- Couplings look alike in TANGO, so a reader who knows one knows all.

**Non-Goals:**

- See `proposal.md`.

## Decisions

### D1: Two OpenSpec changes per integration

For each model, one change lives in the model's repository: what the package provides for TANGO (the readiness items it lacks), with each task marked as done by its authors or by the TANGO team, agreed with the authors before code is written. A second change lives in TANGO-core: the component, the wrapper and the tests. The TANGO change names the other change and the package release it depends on.

The partner change is proposed as a pull request to the authors' repository, first opened in a fork for the TANGO team's own review. If the authors prefer not to keep an `openspec/` folder, the same documents go into an issue on their repository or stay an unmerged pull request; the agreement is what matters, not the folder.

If the model is not in version control, the first task of the partner change is to put it in a repository the authors own.

Alternative considered: one change in TANGO-core describing both sides. Rejected: it decides what another team's package should do in a repository they do not read, and gives them nothing to agree to.

### D2: Readiness checklist for the external package

| Item | Why TANGO needs it |
|---|---|
| Version control, in a repository the authors own | Something to depend on and propose changes to |
| A licence | TANGO may only depend on what it may use |
| Installable package (`pyproject.toml`), importable from any directory | A dependency group can install it |
| Regression tests against stored reference outputs, run in CI | Changes to the package, including ours, provably keep its results |
| Dependency ranges, not exact pins, that resolve together with TANGO's | Both can live in one environment |
| Docstrings with units, return structure and validity ranges | The wrapper can be written and checked without guessing |
| Validity bounds readable by code | Interface checks use the model's own bounds |
| Status as data (flags, codes), not only warning sentences | TANGO can act on an unsupported result instead of missing it |
| Batch evaluation (many operating points per call) | Hourly or representative-day resolution inside an optimizer |
| For ML models: model files that do not depend on one library version | TANGO's own versions are not pinned by a pickle |
| Releases (tags) | TANGO pins a version, not a branch |

Items a package lacks become tasks of the partner change. Not every item blocks a first coupling: the partner change says which are needed for the first TANGO release that uses the model.

### D3: The TANGO side

- One registered component (type and variant) per coupled model, and one wrapper module, `src/tango_core/external/<model>_wrapper.py`, the only module that imports the package.
- A backend protocol in the wrapper, so a model's implementations (a surrogate first, its detailed model later) can be swapped by a config setting.
- An optional uv dependency group per model, pinned to a release of the authors' repository; a lazy import with a `ConfigError` naming the install command.
- Interface checks before and after each call, against the backend's bounds, with an `out_of_range` policy (`error` by default, or `warn`); the model's own warnings recorded unchanged.
- Tests: unit tests against a stand-in backend; a test that the wrapper reproduces the package's own reference outputs at its published examples, skipped without the group; a CI job that installs the group and runs it.
- The component reports its own costs (`add-component-costs`) and takes its time step from TANGO's time stepping (#150).

### D4: Never vendor, patch or fork

TANGO never copies the package into its tree, patches it at import, or depends on a fork branch. A fork branch may be used in a throwaway environment for a spike. If the authors cannot publish a needed change in time, the fallback is running their release in a separate process, decided case by case and recorded in the TANGO change.

### D5: The spec complements the agent rule

`.agent/rules/external-coupling.md` keeps the short principles and its RAFT examples, and points to the spec for the requirements and process. The spec does not repeat its explanations.

## Risks / Trade-offs

- **Authors decline the work or the folder.** The readiness items are requests, not conditions on them; D1's fallback keeps the agreement in an issue, and D4's fallback keeps TANGO unblocked.
- **The checklist delays a first coupling.** D2 lets the partner change mark which items the first release needs.
- **RAFT does not meet every requirement yet.** The audit records the gaps (task 3.1); they are fixed as separate changes.

## Open Questions

1. Resolved 2026-11-18: per-model integration status lives in the project that funds it (for FlexGEO, `GEG-ETHZ/flexgeo#30`), not in TANGO-core.
2. Resolved 2026-11-18: no template machinery. The RevORC partner change (`prepare-for-tango-coupling` in the RevORCHP-SM repository) is the worked example; `src/tango_core/external/README.md` links it, and the next partner change starts as a copy of it.
