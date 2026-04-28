# Changelog

All notable changes to TANGO are documented here.
TANGO does not yet follow [Semantic Versioning](https://semver.org/) — everything is
pre-release. Once the first public release (`1.0.0`) is cut, the project will
adopt SemVer strictly.

## [In Development] — MR !48: Refactor, HPC Sweep Support & Quality Improvements

This MR consolidates a large set of improvements spanning code quality, HPC-friendly parameter sweeps, addon path
  robustness, dependency management, and developer tooling.

[Link to MR !48](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/merge_requests/48)

---

### Added

- **Latin Hypercube Sampling (LHS) parameter sweep** — new `applications/run_flexible_DF_manual_sweep/` application with
  a SLURM job script (`run_flexible_DF_manual_sweep_job.sh`) that runs parallelized LHS sweeps on Euler HPC; SLURM
  parameters (`CPUS_PER_TASK`, `n-samples`, etc.) are configurable via environment variables or CLI arguments.
- **`--sweep-dir` CLI flag** — added to the sweep script for HPC-compatible output path control.
- **`Runner.clone()` and `Runner.update_parameters()`** — new public API methods enabling deep-copy cloning of runners
  and in-place parameter modification without re-construction; `Runner._tango` renamed to `Runner.tango` (public).
- **Deterministic `run_id`** — `run_id` is now a deterministic hash derived from the specs rather than a random UUID,
  enabling reproducible run identification and caching.
- **`Runner.get_hash_from_specs()`** — new helper exposing the spec hash for downstream reuse.
- **`src/tango/units/registry.py`** — new unit registry replacing `eval`-based dynamic class loading with explicit
  `getattr` imports, eliminating circular dependencies and wildcard imports.
- **`src/tango/addons/utils.py`** — new shared utility module for add-ons introducing `resolve_addon_output_path()`
  using `pathlib.Path`.
- **`tango-logo.svg`** — project logo added to the repository and referenced in `README.md`.
- **Parameter sensitivity scripts** — `examples/run_flexible_DF_manual_sensitivity.py` and
  `examples/run_flexible_SF_manual_sensitivity.py` added for LCOE sensitivity analysis.
- **`TODO.md`** — added to track ideas and future implementation items.
- **Data leakage regression test** — `tests/regtest/test_data_leakage.py` added to guard against cross-run data leakage.
- **Add-on unit tests** — `tests/unit/test_addons.py` added with 13 tests covering path resolution and module loading.

### Changed

- **Removed `eval` from unit loading** — replaced with dynamic imports and `getattr`; wildcard (`*`) imports removed
  throughout `config.py`, `utils.py`, `orchestrator.py`, and unit modules.
- **Dependency injection for circular imports** — circular imports previously hidden by `eval` are now resolved via
  explicit dependency injection.
- **`CMGWorkflow` / `NativeWorkflow` common code extracted** — shared logic refactored into the base `Workflow` class in
  `src/tango/core/abstracts/workflow.py`.
- **`--debug` flag replaced by `--log-level`** — `set_logger` moved into `Runner`; TANGO can now run with zero output
  or configurable verbosity — [implementation (`set_logger` / `--log-level`)](src/tango/utils.py),
  [example script usage (`log_level="NONE"`)](examples/run_flexible_SF_manual.py).
- **`parse_args` renamed to `parse_tango_args`** — avoids shadowing `argparse.ArgumentParser.parse_args`.
- **`params_json` parameter removed from CLI** — it was unused and created ambiguity with `param_overrides`; `specs`
  and `param_overrides` now handle all override scenarios.
- **`id` → `unit_id`** — renamed to avoid shadowing the Python builtin `id`.
- **`wellbore` → `well`** — all instances renamed for consistency.
- **Explicit module loading for add-ons** — `Analyzer_interface.py` and `ThermaGraph_interface.py` replaced dynamic
  `importlib` imports with explicit module paths.
- **Add-on output paths** — `output_dir` field added to `ThermaGraphSpecs` and `AnalyzerSpecs`; `run_dir` is now wired
  from `NativeWorkflow` to add-on specs so that `--save-dir` is respected; all 116 YAML example files updated to use
  clean relative paths (e.g. `thermagraph_states.json`), removing all hardcoded `/Users/morteza/...` paths —
  [path resolution utility](src/tango/addons/utils.py),
  [ThermaGraph wiring](src/tango/addons/ThermaGraph/ThermaGraph_interface.py),
  [Analyzer wiring](src/tango/addons/Analyzer/Analyzer_interface.py).
- **Saving is now opt-in** — output files are no longer written automatically; the user controls whether and where files
  are saved — [CLI flags (`--save-dir`, `--no-save`)](src/tango/utils.py),
  [runner integration](src/tango/runner.py).
- **`MULTIPLE_UNIT_NODE_OPTIONS` import cleanup** — removed unused import from `utils.py`; now imported directly from
  `config.py` where needed.
- **Auto-formatting** — `ruff` applied across the codebase; additional `ruff` ignore rules added.

---

### Fixed

- **Flask server runtime artifacts** — redirected out of the source tree — [flask server](tango_flask_server.py).
- **Phase diagrams and ArangoDB sync** — resolved missing phase diagram generation and ArangoDB synchronisation issues
  in `native_workflow.py` and `arangodb_manager.py`.
- **Public/private variable conflation** — fixed conflation between public and private runner state, and corrected a
  spurious logging warning.
- **Duplicate validation output** — validation messages no longer print duplicates.
- **Extraction pressure validation** — cleaned up and generalised target extraction pressure validation logic.
- **Data leakage** — restricted data leakage pathways between simulation runs.
- **Regression tests no longer create `./gen_files`** — test artefacts are now written to `pytest`'s `tmp_path`.

- **Migrated to `uv`** — `uv.lock` generated; `start_flask_server.sh` and `.gitlab-ci.yml` updated to use `uv`; both
  `pixi run -e dev pytest -v` and `uv run pytest -v` confirmed working.
- **GitLab CI optimised** — pipeline restructured for faster feedback.
- **Pre-push hook** — added with rationale in `CONTRIBUTING.md`.
- **`laptop` tag** — added to GitLab runner configuration.
- **`.gitignore` updates** — GitLab runner directories and `./gen_files` excluded; deprecated environment files
  (`environment.yml`, `environment_fixed.yml`) removed.
- **Branching strategy documented** — added to `CONTRIBUTING.md`.
- **Agent rules** — `.antigravity/rules.md` added with repo- and Python-specific conventions.


- **`README.md`** — TANGO logo added; Euler HPC setup and `rsync`-based deployment instructions expanded; `pytest`
  command clarified.
- **`docs/state-management-framework-eval.md`** — state management framework evaluation document added (Polars
  DataFrame-based analysis).
- **`examples/run_flexible_SF_manual.py`** — updated to demonstrate the new `Runner.clone()` / `update_parameters()`
  API.
- **MVP template YAML files** — added under `examples/MVP_templates/`.
- **`examples/failing/readme.md`** — updated; deprecated standalone Python runner scripts in `examples/failing/` removed
  (now driven by YAML configs).

---

<!-- Version comparison links — verify and update when cutting a release -->
[Unreleased]: https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/commits/main
