# Changelog

All notable changes to TANGO are documented here.
From `1.1.0` on, version numbers follow [Effort-based Versioning (EffVer)](https://jacobtomlinson.dev/effver/): the number says how much work upgrading takes, and the **Breaking** section of each release says what to change.

## [In Development]

### Fixed

- **`just slurm` and the SLURM job scripts accept an environment with RAFT installed**: after `just setup-raft`, the up-to-date check (`uv sync --check --offline`) counted the optional `raft` group as extra packages and refused to submit with "The uv environment is out of date". The check now passes `--inexact`, so it still catches missing or outdated locked packages but ignores extra ones.

---

## [1.2.0] — 2026-11-09

### Added

- **`tango_core init` copies the RAFT example**: `templates/AGS_ORC_electric_raft.yml`, with RAFT's config and mesh in `templates/raft/`, now ship in the package. Add RAFT with `uv add "geg-raft @ git+https://github.com/GEG-ETHZ/RAFT@v0.2.1"` and run the example from your own project, no source checkout needed.

### Changed

- The documentation site is public and shows the public pages only.
- TANGO has a DOI, [10.5281/zenodo.23952662](https://doi.org/10.5281/zenodo.23952662): Zenodo archives every GitHub Release. `CITATION.cff` and the README carry it.

---

## [1.1.0] — 2026-11-03

First public release: tango-core is open source under Apache-2.0, and
releases go to PyPI. It completes the example coverage matrix with an
optimized design for every example config, can simulate an AGS loop's
wells and rock with RAFT (from a source checkout), moves the stream interface from temperature to
specific enthalpy, adds interactive phase diagrams, and fixes several
physics and solver bugs those diagrams exposed. Run-time guards turn
physically impossible results into typed errors, component efficiencies
are realistic and cited, and third-party licenses are a release gate.
**Breaking:** the package and command are renamed `tango_core`, and
`tango_core run` needs `--save-dir` or `--no-save`. **Results change
substantially for CO2 and closed-loop (AGS) configs**; every example config
is regoldened.

The version is 1.1.0 rather than the 2.0.0 that EffVer gives a package
rename: this is the first public release, and nobody outside GEG upgrades
from 1.0.x.

[Link to MR !68](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/merge_requests/68)

### Breaking

Configs, scripts, and workflows written for an earlier version need these
changes:

- **`auto-pressure`, `auto-flow`, and `auto-both` injection modes are
  removed**; a config that names one fails validation with a message
  saying so. Use `manual-fracking-check` and find the
  operating point with an `applications/opt_*/` search.
- **`sim_config.max_mass_rate` is rejected** as an unknown key. Drop it; it
  only served `auto-flow`.
- **`example_configs/` is now `templates/`**, in the repository, in the wheel
  (`tango_core/templates/`), and in what `tango_core init` copies.
- **The sweep apps are deleted** (`run_*_sweep`, `sweep_demo_AGS_direct_heat`),
  and the surrogate app moved to
  `applications/_on_hold/opt_hydro_df_electric_surrogate/`. Use the `opt_*`
  apps, or `Workflow` in a loop as its docstring shows.
- **Unknown surface-node keys raise `ConfigError`.** Fix the typo or remove
  the key.
- **`p0_out{N}` is now `p0_megapascals_out{N}`, in MPa.** The old key was
  passed to TESPy as bar, so its values were 10x too low; rename the key and
  give the value in MPa.
- **A linked config value that disagrees raises `ConfigError`.** Values
  derived from another one (e.g. `hydro_static_pressure`,
  `well_eff_diameter`, the injection well's length, a numerical well's
  `num_cells` with `cell_length`) must match it; drop them from the config and
  let TANGO derive them.
- **`tango_core run --save-dir` writes `<name>.results.yml`** instead of
  `<name>.yml`. Update anything that reads the old name.
- **`just slurm-fetch` needs app names or `--all`.** A bare call fetches
  nothing.
- **The package is `tango_core` and the command is `tango_core`.** Replace
  `import tango` with `import tango_core` and `tango_cli` with `tango_core`
  in scripts and notebooks; there is no alias for the old names.
- **`tango_core run` needs `--save-dir DIR` or `--no-save`.** A run with
  neither stops with an error instead of discarding its results.

### Added

- **Releases on PyPI.** `pip install tango-core` or `uv add tango-core`.
  Pushing a version tag runs
  `.github/workflows/release.yml`, which uploads the release to TestPyPI
  and then, after a maintainer approves, the same files to PyPI, using
  Trusted Publishing (no stored token). `CONTRIBUTING.md` has the steps.
- **`grouped_subsurface` component** (`type: grouped_subsurface`): an AGS
  loop's injection, horizontal and production wells grouped into one circuit
  component, configured as three segment blocks (see
  `templates/AGS_ORC_electric_grouped_subsurface.yml`); a first,
  fixed-topology step toward grouped subsystems (GitHub #102).
  Variant `numerical` marches the three `NumericalWell`s in sequence and gives
  results identical to configuring them as separate components; it is the
  shape an external subsurface simulator plugs in behind. The linked lengths
  (production length, loop depth, `layout.well_spacing`) are derived the same
  way as for the three-component AGS configs.
  Both variants take the loop's mass flow and temperature at the injection
  wellhead and its pressure at the production wellhead
  (`sim_config.target_extraction_pressure`), and solve for the injection
  pressure, the way RAFT's own template sets the well up; this keeps the
  injected mass rate under tango's control if RAFT loses fluid to storage or
  leak-off (GitHub #63). `SystemBCIteration` hands that pressure to the
  surface plant in the same pass (`SurfaceComponent.set_injection_pressure`)
  and waits for it to settle (|ΔP| < 1 kPa), so the surface
  `injection_pressure` in these templates is only the first timestep's
  starting guess. The `numerical` variant finds the injection pressure by
  shooting and reproduces a separate-well run's injection pressure and cell
  profiles to within 7e-11 over 25 years (GitHub #130). A topology diagram,
  `docs/diagrams/AGS_ORC_electric_raft_topology.svg`, marks where tango and
  RAFT exchange these boundary conditions and how each timestep's passes
  converge.
- **Optional `raft` dependency group** for the RAFT wellbore/rock simulator
  (`just setup-raft`, or `uv sync --group raft`), pinned to release tag `v0.2.1`. Plain
  `uv sync` never fetches it; see the install guide (`docs/guides/install.md`) for access to the private repo.
  RAFT runs from a source checkout only: the PyPI package has no `raft`
  extra and leaves out the RAFT example (`templates/AGS_ORC_electric_raft.yml`,
  `templates/raft/`) until RAFT's own PyPI name is settled.
  With direnv, a git-ignored `.envrc.local` can set `TANGO_UV_SYNC_ARGS` so
  the automatic sync keeps optional groups installed.
- **`grouped_subsurface` variant `raft`**: RAFT simulates the loop's wells and
  the surrounding rock (`templates/AGS_ORC_electric_raft.yml`, same
  site and plant as the numerical example). `tango_core.external.raft_wrapper.RaftWrapper`
  (the config's `raft:` block) drives RAFT one trial per injection-enthalpy
  iteration and accepts the last one per timestep, converting between
  tango's enthalpy and RAFT's temperature. RAFT's config template and mesh
  (`templates/raft/`, made by hand; the example's mesh is committed
  to git) are checked against the tango config rather than
  overridden. Its `state`/`history` record, per timestep, RAFT's inlet
  and outlet values, the solves and wall time the timestep took, RAFT's
  step statistics for the accepted trial (internal steps, attempts, cuts,
  and the size of every internal step), and RAFT's profile along the well
  (pressure, temperature, and enthalpy at each node; mass flow, Reynolds
  number, and heat transfer coefficient for each element). The step sizes
  and profiles are lists per timestep, so they are in `.results.yml`, not
  the CSV. `raft.verbosity` (`quiet`, `lite`, `full`) sets RAFT's own console
  output, separately from tango's `--log-level`. With `tango_core run
  --save-dir`, RAFT keeps its own output (matrix and well VTKs at the
  template's `output_vtk`, its flow log) in `<stem>.raft/`; without it, RAFT
  writes no VTKs and keeps nothing.
  The RAFT template sets `NR_tol` to 1e-8 instead of RAFT's 1e-7: RAFT
  divides its residual by the mesh's 12,054 nodes, so at 1e-7 the
  production flow could be off by ~1.2e-3 of the injected rate, above
  tango's 1e-3 check.
- **RAFT failures that used to pass silently now raise:** a step RAFT
  accepted at `timestep_min` with an extrapolation error above `rel_error_T`
  (`ConvergenceError`). tango checks only what crosses the coupling: the
  production flow against the injected rate (1e-3, `ConfigError`) and a
  liquid outlet (`SaturationError`); RAFT's profile along the well is
  recorded but not checked, since it's RAFT's interior.
- **The RAFT template's well boundary conditions are checked, not switched.**
  `RaftWrapper.prepare` requires the template's well inlet group to take a
  flux and a temperature and its outlet group a pressure (all
  `function: external`, as in RAFT's own example template) and raises
  `ConfigError` naming any mismatch; it used to overwrite them silently.
- **Grouped subsurface docs page** (`docs/components/grouped-subsurface.md`),
  with `grouped_subsurface`'s config keys, its segment and `raft:` blocks,
  and its outputs generated by `tools/gen_reference.py`, which now documents
  nested config blocks.
- **CI runs one simulated year on the real RAFT** (job "tests with RAFT",
  needs the `RAFT_DEPLOY_KEY` secret), so a change in RAFT's coupling API
  fails CI.
- `FluidState.with_PQ()`/`update_PQ()`: saturation states.
- `Component.accept_timestep()`: called once per timestep after the final
  solve, before `record()`; a no-op unless a component keeps state outside
  tango (e.g. in an external simulator).
- **Docs site** — `mkdocs.yml` (read by Zensical), a `docs` dependency
  group, `just docs` / `just docs-build`, and `.github/workflows/docs.yml`,
  which builds on every PR and deploys to GitHub Pages once the site is
  confirmed org-private (`PAGES_PRIVATE`).
- **Architecture and runtime pages** — layer graph, config-to-objects,
  component circuit, nested loops, BC iteration and one-run diagrams under
  `docs/architecture/` and `docs/runtime/`; a `README.md` in each
  `src/tango_core/` subpackage; API reference from the docstrings.
- **README banner and diagrams** — a wordmark banner in the cold-to-hot
  gradient (`tools/readme_assets.py`), a hero and three editable
  `.drawio.svg` diagrams built around one system pictogram: what TANGO
  models, how you use it, and how the code is organized. All are generated by
  `just diagrams` from `tools/diagrams/`.
- **Component pages** (wells, reservoir, surface plant, economics), an
  **optimization guide**, and a **config reference** and **outputs
  reference** whose tables are generated from the code by
  `tools/gen_reference.py` (`just docs-gen`; checked in CI). 155 field
  docstrings were drafted for them and are marked
  `TODO(docs): drafted, review.` until reviewed.
- **Glossary** (`docs/guides/glossary.md`) and an **internal docs preview**
  (`mkdocs.internal.yml`, `just docs-internal`) that adds the task log,
  roadmap, and archive; until the public release, the org-private Pages
  site deploys this build.
- **`AGENTS.md`** at the root, in `docs/` and in `src/tango_core/components/`;
  `CLAUDE.md` and `GEMINI.md` point to it.
- **Project files** — `SECURITY.md` (private vulnerability reporting on
  GitHub), `CITATION.cff`, `.editorconfig`, and GitHub templates for pull
  requests, bugs, features and tasks.
- **GitHub Actions CI** (`.github/workflows/tests.yml`) — format check, lint,
  mypy strict, the generated-docs check, and the pre-push test selection
  (`-m "not slow and not perf"`) on macOS, Linux and Windows, on every pull request and push to `main` and `develop`;
  `license-check.yml` gates releases; `.github/workflows/docs.yml` builds the docs
  site on every pull request.
- **Coverage matrix complete**: `AGS_ORC_electric.yml`,
  `hydro_direct_heat.yml`, `CPG_direct_heat.yml`, `CO2_EGS_direct_heat.yml`,
  `CO2_AGS_direct_heat.yml`, and the CO2 power cells, including direct-CO2
  plants `CO2_EGS_electric.yml` and `CO2_AGS_electric.yml` (the CO2 itself
  drives the turbine; LCOE 0.40 and 2.89 vs 1.55 and 10.9 for the binary
  versions). Matrix and per-config review checklist: GitLab #67.
- **Interactive P-h phase diagrams** (GitLab #56): `tango_core run
  --save-dir` writes one Plotly `<config>.phase_<fluid>.html` per working
  fluid, with a year slider, configurable isotherms/isentropes/isochores/
  quality lines (`--phase-diagram-config`), a shaded two-phase region, a
  phase-color legend, and wells drawn along their computed profiles
  (including the downhole pump step). `just phase-diagrams` writes every
  config's into gitignored `scratch_output/<config>/`.
- **Run-time guards** in `GraphSurface`, as typed errors that optimizers
  treat as infeasible designs:
  - `PassivePressureRiseError`: a heat exchanger, valve, separator, mixer
    or cycle closer whose outlet pressure is above its inlet (TESPy solves
    a fixed absolute `p_out` above the real inlet as free compression).
  - `NegativeNetPowerError`: a turbine plant that consumes more power than
    it makes. Checked once per timestep, on the converged state.
  - `ValveCannotRaisePressureError`: a `PumpOrValve` on its Valve leg whose
    pressure would rise. The only power-state error that retries the node
    as a pump; any other is reported as itself.
  - `NegativeNetThermalError`: a heat plant whose produced fluid has cooled
    so far (e.g. a depleted reservoir) that its `net_thermal` exchangers
    would heat it. Checked once per timestep, on the converged state.
  - `TESPyConvergenceError`: an unconverged TESPy solve, except TESPy's
    measured ~1 J/kg stall on a pump drawing exactly saturated liquid,
    which is used with a warning naming the pump.
- **`subcooling_K`** surface-node key (TESPy `Td_bp`, `td_bubble` since
  TESPy 0.11): an outlet that many
  kelvin below saturation at its actual pressure.
- **Third-party license tooling**: `tools/check_licenses.py` records the
  dependency graph (direct/indirect, depth, scope), evaluates license
  expressions, supports reviewed approvals, and draws a draw.io dependency
  tree; a `license_check` CI job runs on MRs into `main` and on release
  tags.
- **`docs/SOURCES.md`**, a verified bibliography that code and configs cite
  by key; `docs/` is now user-facing (shipped in the wheel), with developer
  docs in `dev_docs/`. `dev_docs/tespy_limitations.md` lists what TESPy
  solves without complaint and TANGO's guards.

### Changed

- **Breaking: `tango_core run` needs `--save-dir DIR` or `--no-save`.** Running
  without either (or with both) now stops with an argparse error, so results
  are never lost by forgetting `--save-dir`; `--no-save` writes nothing, for
  tests and quick checks (GitHub #125).
- **One name: `tango_core`.** The import package is `tango_core`
  (`import tango_core`, `src/tango_core/`), matching the distribution
  `tango-core`, and the command is `tango_core` (`tango_core run`,
  `tango_core validate`, `tango_core init`, `tango_core --version`).
  `import tango` and `tango_cli` are gone, with no alias; update imports
  and scripts. The CLI module is `tango_core.cli`, and the source hash DVC
  tracks is `src/tango_core.hash`.
- **Python 3.12 and 3.13** are supported as well as 3.11
  (`requires-python = ">=3.11,<3.14"`); a CI job installs the package as
  a PyPI user would and runs the tests on both. numpy is capped below 2.5,
  which removed `numpy.row_stack` that pymoo 0.6.1.3 still calls.
- **Fewer runtime dependencies.** Installing `tango-core` no longer pulls
  in packages its code doesn't use (`pip`, `pexpect`, `python-arango`,
  `tqdm`, `msgpack`, `oyaml`, `termcolor`, `tabulate`, `openpyxl`,
  `seaborn`, `polars`, `jinja2`, `networkx`, `fluprodia`), type stubs, or
  DVC plugins; the pinned `pip<24` no longer downgrades pip. The `dev`
  extra is gone: development tools are an unpublished dependency group that
  `uv sync` installs.
- **Smaller source archive (sdist).** It now holds the package source,
  tests, templates, applications, and the release files (license, README,
  changelog, citation) instead of every file in the repository, and leaves
  out what the wheel leaves out: the on-hold app and the DVC locks; the
  wheel is unchanged.
- **SPDX license headers.** Every Python file starts with
  `SPDX-FileCopyrightText` and `SPDX-License-Identifier` lines, and
  `REUSE.toml` covers the other files, so the repository complies with the
  REUSE specification. A `reuse lint` prek hook keeps it that way.
- **License: Apache-2.0.** TANGO is open source under the Apache License,
  Version 2.0 (`LICENSE.txt`), copyright 2025 ETH Zurich. The proprietary
  license and the internal distribution notice (`NOTICE`) are gone. The
  package metadata declares the SPDX expression `Apache-2.0`, and
  `tango_core --version` prints the copyright and license line.
- **`example_configs/` is now `templates/`.** `tango_core init` copies it to
  `DEST/templates/`, and the wheel ships it as `tango_core/templates/`.
- **Forge** — GitHub (`GEG-ETHZ/TANGO-core`) replaces gitlab.ethz.ch for
  code, issues, pull requests, CI and releases. Install and clone commands,
  contributor workflow and release steps point to GitHub;
  `.gitlab-ci.yml` and `.gitlab/` are removed.
- **README** — rewritten as a landing page: overview, diagrams,
  requirements, installation, quickstart, documentation map, help, citation
  and license. Detailed install, run and Euler steps moved to
  `docs/guides/`.
- **CONTRIBUTING, directory READMEs, deep dives** — restructured with
  consistent titles and verified commands. `tests/README.md`
  now states correctly that the pre-push hook skips `slow` and `perf`
  tests.
- **Historical docs** — progress summaries, refactor notes and the phase
  0/1 diagrams moved to `docs/archive/`, off the site.
- **Developer docs are back in `docs/`.** The task log, roadmap, design
  notes and archive sit next to the site pages; the public build excludes
  them and the internal preview includes them. `dev_docs/` is gone. The
  wheel still ships only `docs/SOURCES.md` from `docs/`.
- **`tango_core run --save-dir`** writes the full results as
  `<name>.results.yml` (was `<name>.yml`, the same name as the input file).
- **CSV headers carry units**: every `.smry.csv`/`.econ.csv` column ends in
  its unit, e.g. `production_well_T_outlet [K]`, `LCOE [USD/kWh]`.
- **Phase diagrams** number every state point in flow order, with a
  "State points" key under the plot, and open on the final year instead of
  animating through every year on load.
- **TESPy 0.7.1 → 0.11.2** (GitLab #75). LCOE results for every example
  config are unchanged to 1e-6. ORC designs that used to fail to converge at
  random now solve every time. The `subcooling_K` surface-node key now maps
  to TESPy's `td_bubble`.
- **Linked config values have one source.** A quantity that several
  components need is written once and the rest derived
  (`tango_core.workflows.linked_quantities`); a config that gives a copy which
  disagrees raises `ConfigError` instead of running with it. Doublet:
  `reservoir.reservoir_depth` and the pump depth
  (`production_well_upper.well_length`) set the injection well's length, the
  lower production segment, `well_eff_diameter` and `hydro_static_pressure`
  (= brine density x g x depth; 2% lower than the old hand-entered 50 MPa in
  the hydro configs, 24.5 vs 25 MPa in CPG). AGS: the injection well's length
  sets the production well and the loop's depth, and the loop length sets
  `layout.well_spacing`. Every example config drops its redundant copies.
- **Numerical wells:** `num_cells` and `cell_length` are linked to
  `well_length` (give either, both if they agree, or neither for the
  default). Derived values (`T_r`, cross-section, ...) are no longer written
  by `to_dict()`, and a config that supplies one that disagrees raises
  instead of being silently overwritten; `LumpedReservoir`'s derived values
  work the same way. `set_well_length()` changes a length with an explicit
  choice of what follows it.
- **Surface-node keys are checked:** an unknown key (a typo, a renamed key)
  raises `ConfigError` instead of being ignored. The TESPy starting-pressure
  guess is now `p0_megapascals_out{N}`, in MPa like `p_out_megapascals`; the
  old `p0_out{N}` was passed to TESPy unconverted in bar, so the ORC
  configs' and opt apps' MPa values were 10x too low.
- **Realistic component efficiencies** in every example config, each with
  a citation: turbines 0.85 and surface pumps 0.75 (DiPippo 2016),
  downhole pumps 0.55 overall ESP string (van 't Spijker & Ungemach 2016).
  Three marginal examples were adjusted to stay net-positive
  (`EGS_electric.yml` deepened to a hypothetical 5000 m; `CPG_electric.yml`
  at 125 kg/s; `CO2_AGS_ORC_electric.yml` at 20 years).
- **Descriptive surface node names** in the example configs (e.g.
  `evaporator`, `preheater`, `flash_valve`, `separator`, `brine_pump`,
  `condensate_pump`, `district_heating_hx`; every `PumpOrValve` is
  `circulation_control`). Application parameter paths that address these
  nodes changed accordingly.
- **Binary (ORC) plant configs carry `ORC` in their file names.**
- **Condensers subcool by 1 K** (`subcooling_K: 1.0`) instead of ending at
  exactly saturated liquid, except four ORC condensers and
  `CPG_electric.yml`'s, which already sit at or below their cooling limit.
- `tango_core init` copies every application by default (`--app` narrows,
  `--no-apps` skips).
- The pre-push remote-freshness hook passes when you have rewritten your
  own pushed commits (amend/rebase), and still blocks when someone else
  pushed.

### Removed

- **The sweep apps** (`run_AGS_direct_heat_sweep`, `run_EGS_direct_heat_sweep`,
  `run_hydro_df_electric_sweep`, `sweep_demo_AGS_direct_heat`). The `opt_*`
  apps cover their configs; `Workflow`'s docstring shows the sweep pattern.
  `just apps` drops its `--slow` flag, which only ran their full grids.
- **`auto-pressure`, `auto-flow` and `auto-both` injection modes**, with
  `sim_config.max_mass_rate` and the `hydro_sf_electric_autopressure.yml`
  and `hydro_sf_electric_autoflow.yml` examples. They iterated pressure or
  flow toward a fracking threshold within each timestep; `auto-pressure`
  could cycle without converging, and `auto-both` was never implemented.
  Find operating points with the `applications/opt_*/` searches instead,
  which treat fracking as a constraint under `manual-fracking-check`.

### Fixed

- **Phase diagrams color each stretch of a well by its own phase.** A well's
  profile was drawn in one color, taken from its middle node, so an 8 km AGS
  well was colored "supercritical" along its whole length, including the top
  ~2.3 km below the critical pressure. The line now changes color where it
  crosses the critical pressure or the saturation curve. A `grouped_subsurface`
  is drawn as its three legs, labeled `injection_well`, `horizontal_well`, and
  `production_well`, and the `raft` variant's legs follow RAFT's recorded
  profile instead of one straight line.
- **Mass rate around a closed circuit is checked.** The BC iteration fed the
  surface outlet's mass rate back as the next pass's injected rate; a
  component that lost mass would have lowered the injected rate on every
  pass without an error. It now raises `ConfigError` (GitHub #63). No example
  config is affected: every component conserves mass.
- **Optimizations used the base design's well resolution.** `Minimization`
  built its template with `Workflow.to_dict()`, which pinned each numerical
  well's cell count, so AGS designs with longer wells were simulated with
  far coarser cells (an 8000 m loop in 10 cells of 800 m instead of 40 of
  200 m; up to 1.3% in LCOE). The template is now the config as written.
- **Sweeps:** the EGS direct-heat sweep never moved the lower production
  segment's starting depth with the reservoir depth, so its rock
  temperatures stayed at the base design's; the hydro_df sweep varied the
  reservoir depth and the well lengths independently; all three sweeps
  inherited the pinned cell counts above. They now build from the YAML and
  set only source values; the hydro_df one-at-a-time design drops from 59
  to 55 rows.
- **Parallel optimizations on TESPy 0.11:** `Minimization` and the surrogate
  sweep take a config dict (`base_cfg`), not a `Workflow`, so nothing
  unpicklable is sent to worker processes.
- **hydro_df's two flash-pressure parameters** give the same design in
  either application order.
- **Energy was lost at every component boundary for CO2**: components
  passed temperature and each rebuilt enthalpy from (T, P), and near CO2's
  critical point the tabular property backend lost up to ~42 kJ/kg per
  hand-off (~1.1 MW in `CO2_EGS_direct_heat.yml`). `Stream` now carries
  specific enthalpy. The wellhead-to-plant pipe now drops pressure at
  constant enthalpy (it was isothermal).
- **Production wells had their rock temperatures upside down**: the
  rock-temperature profile increased in depth along the flow, which is
  reversed for upward flow. Small effect for hydrothermal/EGS/CPG (within
  ~1%), large for closed AGS loops (`CO2_AGS_ORC_electric` LCOE 55.1 ->
  10.9).
- **The injection-enthalpy loop could accept an open loop**: its relaxed
  guess never reached the injection well, and convergence was checked
  against that unused guess (loop open by up to ~3.6 kJ/kg). Every config
  now closes within 1 kJ/kg every year.
- **`AUTO_PRESSURE`/`AUTO_BOTH` depleted the reservoir once per outer
  iteration** instead of once per timestep.
- **Free compression in two heat configs**: `CPG_direct_heat.yml` and
  `CO2_EGS_direct_heat.yml` had heat exchangers raising pressure for free,
  which had been letting them reinject dense CO2. Both now use a pressure
  ratio and an injection cooler; `CPG_direct_heat.yml` runs at 75 kg/s and
  its reservoir now supplies the heat (its CO2 had been reinjected hotter
  than the reservoir, so all delivered heat was pump work).
- **The `PumpOrValve` fallback reported the wrong error**: a negative-net-
  power or free-compression failure was retried as a pump and surfaced as
  "negative pump power".
- **A CO2 EGS power example ran away**: reinjected CO2 sat on its
  pseudo-critical density drop; `CO2_EGS_ORC_electric.yml` now cools it
  before reinjection.

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
[In Development]: https://github.com/GEG-ETHZ/TANGO-core/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/GEG-ETHZ/TANGO-core/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/GEG-ETHZ/TANGO-core/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/GEG-ETHZ/TANGO-core/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/GEG-ETHZ/TANGO-core/compare/old-tango-main-2026-06-08...v1.0.0
