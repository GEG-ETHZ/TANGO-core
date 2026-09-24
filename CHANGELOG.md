# Changelog

All notable changes to TANGO are documented here.
Starting with `1.0.0`, the project follows [Semantic Versioning](https://semver.org/).

## [In Development]

*(Nothing yet.)*

---

## [1.0.1] — 2026-09-24

Patch release: completes two more cells of the example coverage matrix,
fixes two real bugs found while doing so, adds full regression coverage
for every `example_configs/` YAML plus a release-tag test gate, and adds
`tango_cli run --save-dir` (previously, running a config via `tango_cli`
directly produced no output at all — only `applications/` scripts could
save anything).

### Added

- **`EGS_electric.yml`** — completes the EGS coverage-matrix row (heat +
  power).
- **`CPG_electric.yml`** — new CPG power coverage-matrix cell, ported from
  old tango's `examples/CPG_num_pp.yml` (preserved at git tag
  `pre-tango-core-rename-2026-09-18`).
- **`tests/regtest/test_example_configs.py`** — full-length (real
  `sim_config.num_tsteps`, never a reduced smoke count) regression
  coverage for every `example_configs/*.yml`: injection-well physics
  invariants, surface net-power/thermal sanity, and a golden LCOE value
  per config. Includes a guard test that fails if a new
  `example_configs/` file ever ships without coverage. `just test
  --example-configs` runs this plus `hydro_sf_electric.yml`'s own
  dedicated, more detailed coverage in one command.
- **Release-tag test gate** (`tools/check_full_tests_before_tag_push.py`)
  — a pre-push hook that runs `just test --all` and blocks the push if a
  `vX.Y.Z` release tag is being pushed and the suite fails. Local, not
  GitLab CI, since this repo's runner is too slow for `tests/regtest/`
  (already excluded from CI for that reason).
- **`tango_cli run --save-dir DIR`** — writes `<name>.yml` (full results,
  reloadable with `Workflow.from_file()`), `<name>.smry.csv` (one row per
  timestep, one column per component's own scalar history field), and
  `<name>.econ.csv` (one row, the economic component's final state).
  Saving is opt-in; nothing is written without this flag.
- **Per-config CoolProp backend selection** (`common.coolprop_backend`) —
  BICUBIC's tabulated backend has coarse resolution right at a fluid's
  critical point; a config can now opt into the exact (slower) HEOS
  backend near one instead.
- New TANGO Commandment: every `example_configs/` YAML must be
  regression-tested (see `CONTRIBUTING.md`).

### Fixed

- **`CPG_electric.yml`'s surface plant physics**: held CO2 supercritical
  through the whole cycle, including the turbine/condenser outlet
  pressures — but an absolute pressure only has real physical meaning
  where temperature and pressure are locked together by a fluid's
  saturation curve, which doesn't exist above the critical point. Fixed
  by condensing CO2 after the turbine instead, the same mechanism
  `hydro_sf_electric.yml`'s water cycle and old tango's own CPG model
  both use.
- **`CPG_electric.yml`'s `LCOE` was `NaN`**: its condenser's
  `cooling_tower_mode: DRY` gave a parasitic cooling-tower power draw
  that exceeded its own net turbine output (CPG condenses its entire
  flow, unlike `hydro_sf_electric.yml`'s small flash-split fraction, so
  this term matters far more here) — and `DRY` was never grounded in
  what old tango's own config actually used (`WET`, its unoverridden
  default). Fixed by switching to `WET`.
- Two mis-attributed physics citations: Adams → Zhang for the well
  heat-loss model, Adams → Birdsell for the well-pattern impedance
  formula (both verified against Crossref/DataCite).
- `--p`/similar ambiguous CLI abbreviations across `applications/`
  scripts used to fail with a confusing "ambiguous option" error instead
  of a clear one (`allow_abbrev=False` added everywhere); a script whose
  `--help` silently ran its sweep instead of showing help;
  `run_hydro_df_electric_sweep.py`'s docstring/`--help` now states its
  design-matrix size and that it's fixed, not tunable at runtime.
- An orphaned old-tango-vs-new-tango parity test (`test_lcoe_parity`)
  survived — with its original, much-looser tolerance — long after the
  actual comparison it once ran against was deleted. Replaced with a
  tight self-consistency golden-value check, consolidated into
  `test_example_configs.py` alongside every other config's.

### Changed

- **`just demos` renamed to `just apps`** — its job is smoke-testing
  `applications/` scripts; `example_configs/` regression coverage moved
  to `just test --example-configs`/`--all` instead of living in this
  recipe.

---

## [1.0.0]

The first public release. This entry covers everything between `old-tango-main-2026-06-08`
(the last commit before the multi-month `tango_next` rewrite landed on `main`) and this tag —
a full rewrite of TANGO's core, squashed into a single commit
(`c5a9d8c`, "refactor to make tango robust"). Old TANGO's `src/tango/` package still exists,
preserved at git tag `pre-tango-core-rename-2026-09-18`, but is no longer part of the working
tree; everything below refers to the new implementation unless noted otherwise.

### Added

- **`GraphSurface`**: replaces bespoke per-layout Python surface-plant code with a YAML
  `nodes`/`edges` graph. New surface configurations are authored as data, not new component
  classes.
- **`LockedState`**: enforces that every value meant to be recomputed each simulated year
  actually is — raises immediately instead of silently reusing a stale number from the
  previous timestep.
- **`InjectionPolicy`**: replaces three separate, ambiguous fracking-safety settings from old
  TANGO with a single explicit setting (5 modes: manual, manual+check, auto-pressure,
  auto-flow, auto-both).
- **Real economic model and multi-objective optimizer (`pymoo_api`)**: replaces a placeholder
  economic model. Supports HPC/Euler-parallelized sweeps with automatic worker sizing, mid-run
  checkpointing, and warm-starting, and saves every evaluated design as a ready-to-run file
  (rather than only a single "recommended" design as before). Wires parameters and objectives
  through a small set of composable functions instead of old TANGO's `eval`-based
  configuration.
- **Pydantic-based config validation** (`src/tango/core/specs.py`): raises typed
  `ConfigError`s and warnings for out-of-range, missing, or contradictory configuration
  values, replacing untyped dict-based config handling.
- **AGS (closed-loop) direct-heat system**: implemented end to end, including a
  parameter-sweep example — the first fully modern closed-loop system type in TANGO.
- **New example ports**: added a supercritical-CO2 power-generation topology
  (`CPG_electric.yml`) and the ORC power cycle (ported onto `GraphSurface`).
- **Adaptive well discretization**: scales segment count automatically with well length
  (manual override still available).
- **CI-enforced regression tests**: compare new-TANGO output against golden snapshots and
  against old TANGO's own results.
- **"TANGO Commandments"**: added a short list of hard design rules to `CONTRIBUTING.md`
  (e.g. every closed fluid loop must contain a pump/compressor), each tied to the real bug
  that motivated it.

### Changed

- **Downhole production-well pump model**: replaced constant-temperature (isothermal) pump
  with an entropy-conserving (isentropic) model including an efficiency penalty — a more
  accurate ~53% pump-power increase for one benchmark design.
- **Production-well pump pressure targeting**: replaces a one-shot correction with a real
  iterative (secant-method) solve that accounts for density feedback on friction loss.
- **Fluid-property evaluation**: switches the hot path to a pre-tabulated/interpolation mode
  of the same underlying property library — roughly halves that hotspot's cost, for up to an
  18% total runtime improvement (about 2x on surface-solver-heavy runs).
- **AGS closed loop**: adds a real circulation pump (previously thermosiphon-only); requires
  every closed fluid loop to contain a pump or compressor, enforced at construction time.
- Labels optimizer output columns explicitly as decision-variable, objective, or
  reported-only, and shows real units on plot axes.
- Catches CoolProp failures inside the surface-plant solver as a single failed design,
  instead of crashing an entire optimization run.

### Fixed

Real physics/correctness bugs found while porting old TANGO's behavior to the new
implementation (see `docs/bugs-fixed-in-tango.md` for full detail on each):

- Fixed AGS never advancing simulated time past year one in old TANGO (a fake-convergence
  bug) — every downstream multi-year AGS number from the old system was invalid. The new
  implementation's `LockedState` guardrail structurally cannot have this bug.
- Fixed the new implementation's own reservoir initial-pressure formula, which borrowed a
  safety-ceiling formula instead of the true initial condition (~12% error); now agrees with
  old TANGO to sub-microkelvin precision.
- Fixed an AGS well-depth bug: a well starting partway down another well segment had its
  surrounding rock temperature computed as if it started at the surface, modeling a heat
  *sink* as a heat *source*. Corrected the best-case AGS design temperature from 92.7°C to
  136.6°C.
- Fixed old TANGO's well-cost safety-limit formula, which used diameter where the equation
  called for radius (off by a factor of `-ln(2)`).
- Fixed old TANGO's `check_fracking`, which didn't gate what its name implied (only capped
  flow, not pressure) — superseded by the unified `InjectionPolicy`.
- Fixed old TANGO's boolean config fields, which used `== "yes"` string comparisons so `True`
  in YAML silently did nothing — the new implementation uses real booleans throughout.
- Fixed old TANGO silently swallowing solver non-convergence (warning and proceeding, or
  reusing the last unconverged guess) — the new implementation raises `ConvergenceError`.
- Fixed the economic model double-counting well mobilization cost when a well was split into
  multiple physics sub-components.
- Fixed numerically-marched wells falling about 1% short of their declared length (an
  off-by-one in the march step count).
- Fixed the optimizer scoring a crashed design better than a design that ran but failed — a
  crash now always scores strictly worse.

### Known limitations

- **MOOSE-coupled examples** (~55 configs) cannot currently be run — hardcoded to a former
  team member's machine with no remaining documentation. Not part of this release.
- **Pump electricity accounting** needs human-in-the-loop verification before net-power or
  LCOE outputs should be trusted; the current implementation is based on static code analysis
  only.
- **`GraphSurface`'s fixed outlet pressures** (flash pressure, condensing pressure) are a
  deliberate modeling choice — real plant control targets, not derived quantities — but are
  only self-consistent if calibrated to the site's assumed conditions, and nothing currently
  checks that. Old TANGO's pressure-monotonicity sanity guard has no equivalent yet. See
  `docs/TANGO_vision_and_roadmap/README.md` for the full discussion.
- **Seasonal heat-demand variation** is not modeled — direct-heat and cogeneration examples
  run at constant mass flow.
- **Combined heat-and-power (cogeneration)** has topology precedent and support in
  `GraphSurface`, but the economic side (how to compute/report a combined levelized cost)
  needs a design decision before an example is built.
- Deleted old TANGO's `examples/` directory and its example-coverage audit as part of this
  release's cleanup; preserved at git tag `pre-tango-core-rename-2026-09-18` for anyone who
  needs to consult them.

---

<!-- Version comparison links — verify and update when cutting a release -->
[Unreleased]: https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/compare/v1.0.1...HEAD
[1.0.1]: https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/compare/v1.0.0...v1.0.1
[1.0.0]: https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/compare/old-tango-main-2026-06-08...v1.0.0
