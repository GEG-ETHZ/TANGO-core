# Spec Delta

## Purpose

States what every coupling of an externally owned model to TANGO provides, on the TANGO side and on the external package's side, and how the work is agreed with the model's authors.

## ADDED Requirements

### Requirement: An agreed change on each side

Each integration SHALL have an OpenSpec change (or, where the authors prefer, an issue with the same content) in the external model's repository, describing what the package provides for TANGO and who does each task, and an OpenSpec change in TANGO-core describing the coupling. The TANGO change SHALL name the partner change and the package release it depends on. TANGO code for the coupling SHALL NOT be merged before the authors have agreed to the interface in the partner change.

#### Scenario: Starting a new integration

- **WHEN** a model owned by another team is to be coupled
- **THEN** a partner change is proposed to its authors listing the readiness items the package lacks, before any TANGO code is written

#### Scenario: Model not under version control

- **WHEN** the model's authors share it without a repository
- **THEN** the partner change's first task is a repository the authors own, and TANGO does not keep a copy

### Requirement: Minimum readiness of the external package

Before a TANGO release depends on an external package, the package SHALL be in a repository its authors own, under a licence, installable, tested against stored reference outputs in CI, documented with units and validity ranges, and released with tags, and its dependency ranges SHALL resolve together with TANGO's.

#### Scenario: Conflicting pins

- **WHEN** the package pins a dependency to a version outside TANGO's range
- **THEN** the conflict is resolved by widening one side's range, recorded in both changes, before the dependency group is added

#### Scenario: Package without tests

- **WHEN** a TANGO-motivated change is proposed to a package that has no tests
- **THEN** regression tests against its current outputs are proposed first, so every later change provably keeps its results

### Requirement: Further readiness items are decided per model

The partner change SHALL state which further readiness items the first TANGO release that uses the model needs: validity bounds readable by code, status as data, batch evaluation, and model files independent of one library version.

#### Scenario: Surrogate called at hourly resolution

- **WHEN** a model is evaluated at hundreds of operating points per TANGO step
- **THEN** the partner change lists batch evaluation, marked as needed for the first release or as a later improvement

### Requirement: One wrapper per external model

All imports of an external package SHALL be in one module, `src/tango_core/external/<model>_wrapper.py`. The import SHALL be lazy, and a missing package SHALL raise a `ConfigError` naming the install command.

#### Scenario: Package not installed

- **WHEN** a config uses a component backed by an external package that is not installed
- **THEN** a `ConfigError` names the install command, and configs that do not use it are unaffected

### Requirement: Depend only on the authors' releases

The package SHALL be an optional uv dependency group pinned to a release (tag or commit) of the authors' repository. TANGO SHALL NOT vendor, patch or depend on a fork of it.

#### Scenario: A fix the authors have not published

- **WHEN** TANGO needs a change the authors have not released
- **THEN** it is proposed to them as a pull request, and TANGO keeps depending on the last release, or runs that release in a separate process as recorded in the TANGO change

### Requirement: Replaceable implementations

The wrapper SHALL define a backend protocol, so that another implementation of the same model (for example its detailed model in place of a surrogate) can be selected in the config without changing the component.

#### Scenario: Switching backend

- **WHEN** a second backend implementing the protocol is added
- **THEN** a config selects it with one setting, and the component's code does not change

### Requirement: Checks at the interface only

The wrapper SHALL check every value TANGO sends against the backend's validity bounds, and every value it reads back that TANGO relies on, under an `out_of_range` policy of `error` (default) or `warn`. It SHALL record the model's own warnings and status unchanged, and SHALL NOT check the model's internal quantities.

#### Scenario: Input outside the model's range

- **WHEN** TANGO would send a value outside the backend's bounds under the default policy
- **THEN** the run fails naming the input, its value and the bound

### Requirement: The coupling reproduces the package

The TANGO tests SHALL include a test that the wrapper reproduces the package's own reference outputs at its published examples, skipped when the dependency group is not installed, and a CI job SHALL install the group and run it.

#### Scenario: Package release changes its outputs

- **WHEN** the pinned release is updated to one whose outputs differ at the published examples
- **THEN** the reproduction test fails, and the difference is checked with the authors before the reference values in TANGO are changed

### Requirement: Physics described from the authors' documentation

Comments, docstrings and documentation in TANGO SHALL describe the external model's physics only from its authors' documentation, citing it. Questions about its internals SHALL go to its authors.

#### Scenario: Unclear model quantity

- **WHEN** the meaning of a model output is not documented by its authors
- **THEN** TANGO's documentation does not guess it, and the question is listed in the partner change
