# Tasks

## 0. Prerequisites outside TANGO

- [ ] 0.1 Agree the interface with the model's authors: go through the open questions 1 to 7 in `design.md` and record the answers there.
- [ ] 0.2 Upstream pull requests to the authors' repository: regression tests and CI, installable package with loosened pins, docstrings. Record each PR and whether it was merged.
- [ ] 0.3 Resolve the version conflicts (D2): raise TANGO's pandas range to allow 3.x and move the lock to numpy 2; run `just check` and the regression tests (`just test --all`) on pandas 3.0.2, numpy 2.4 and scikit-learn 1.8.0 (the fast unit tests already pass). If the regression tests fail, check whether the models run on pandas 2.x instead; failing both, use the subprocess fallback. Tell the person before continuing.
- [ ] 0.4 Decide whether #17 (component-owned costs) lands first or this change uses the stopgap hook (D8).

## 1. Spike

- [ ] 1.1 In a throwaway environment, install the package (an upstream release, or a fork branch for the spike only) next to TANGO and evaluate the README examples through a prototype `SurrogateBackend`. Verify the outputs match the package's own.
- [ ] 1.2 Time 288 single-point evaluations and a full annual step under `SystemBCIteration`, and estimate a 25-year run. Record the numbers in `design.md` D6 and decide whether caching or the upstream batch API is needed before continuing.

## 2. Wrapper

- [ ] 2.1 Add `external/revorc_wrapper.py`: `RevOrcBackend` protocol, `OperatingPoints`/`Results` arrays, `SurrogateBackend`, lazy import raising `ConfigError` with the install command. Verify with unit tests using a stub backend, and with a test that simulates the missing package.
- [ ] 2.2 Add the interface checks (D7) and `SurfaceModelDomainError`. Verify with unit tests for each scenario under "Inputs are checked before the call" and "Results are checked after the call".
- [ ] 2.3 Add the `revorc` dependency group, pinned to an upstream release, and the mypy override. Verify `uv sync --group revorc` and `just check`.

## 3. Surface component

- [ ] 3.1 Add `RevOrcSurface` with its config fields (`n_modules`, ambient profile, mode schedule, `min_brine_outlet_T`, `out_of_range`, backend), `State` and `History`, registered as `("surface", "revorc")`. Verify config validation tests, including the geofluid and heat-pump-load scenarios.
- [ ] 3.2 Implement `solve`: inlet conversion, module split, representative hours for the step, one `evaluate` call, time-weighted recording, outlet stream. Verify the "modules", "representative days" and "mass rate" scenarios with a stub backend.
- [ ] 3.3 Add the test against the real package (skipped without the group) for the "published example" scenario.

## 4. Economics

- [ ] 4.1 Have `RevOrcSurface` report its plant cost per module, through #17's interface or the stopgap hook (D8). Verify the "plant CAPEX is not zero" scenario and that existing LCOE regression values do not change.

## 5. Template, docs and release

- [ ] 5.1 Add `templates/hydro_RevORC.yml` with a documented ambient profile and the default schedule, and run it for real once; or list it in `.agent/DEFERRED_VERIFICATION.md`.
- [ ] 5.2 Update `src/tango_core/components/README.md` and `docs/architecture/`, run `just docs-gen` and `just docs-build`.
- [ ] 5.3 Add a `CHANGELOG.md` entry under `[In Development]`.
