# Tests

The test suite checks that TANGO's building blocks behave as specified and that full simulations keep producing the reference results. The suite has two tiers: fast unit tests and slower regression tests. They run at three points: continuous integration, the pre-push hook and the release-tag gate.

## Layout

| Path | Scope | Typical runtime |
|---|---|---|
| `tests/unit/` | One class or function at a time: `LockedState`, serialization round-trips, state/history parity, convergence snapshots, CLI parsing, the optimization and surrogate APIs | Seconds |
| `tests/regtest/` | Full simulations end to end: every template against a golden LCOE, configuration validation, error handling, LCOE regression, results export | Up to more than an hour for the full set |
| `tests/regtest/fixtures/` | Deliberately invalid configurations for the validation tests | — |

| File | Checks |
|---|---|
| `unit/test_locked_state.py` | `LockedState` read/write guards |
| `unit/test_serde_roundtrip.py` | Every component serializes and reloads unchanged |
| `unit/test_state_history_parity.py` | Every `*State` field has a `*History` counterpart ([rule](https://github.com/GEG-ETHZ/TANGO-core/blob/main/CONTRIBUTING.md#rule-state-history-parity)) |
| `unit/test_convergence_snapshot.py` | `snapshot_convergence_state` / `restore_convergence_state` |
| `unit/test_cli.py` | `tango_core` argument parsing |
| `unit/test_pymoo_api.py`, `unit/test_surrogate_api.py` | Optimization and surrogate pipeline plumbing |
| `regtest/test_templates.py` | Every `templates/*.yml` at full length, against its golden LCOE; fails if a configuration is not listed |
| `regtest/test_lcoe_regression.py` | Economic component behavior and the reference LCOE |
| `regtest/test_config_validation.py` | Invalid configurations raise `ConfigError` with a clear message |
| `regtest/test_error_handling.py` | Runtime failures raise the right `TangoError` subclass |
| `regtest/test_results_export.py` | `write_results` output files |
| `regtest/test_cmg.py` | Placeholder for a future CMG adapter; empty |

## Markers

| Marker | Meaning |
|---|---|
| `slow` | Full-length numeric reference checks. A reduced-timestep companion covers the same code path by default. |
| `perf` | Wall-clock timing assertions; unreliable under parallel load. |

## Where tests run

| Trigger | Command | Covers |
|---|---|---|
| GitHub Actions CI (pull requests, `main`) | `uv run python -X warn_default_encoding -m pytest -m "not slow and not perf" tests/` | The pre-push selection, on Linux, macOS, and Windows |
| GitHub Actions CI, RAFT job (pushes to `main`/`develop`, manual run) | The CI selection with RAFT installed, then `tests/regtest/test_raft_integration.py` | The pre-push selection plus one year on the real RAFT, on Linux |
| Pre-push hook | `uv run python -X warn_default_encoding -m pytest -m "not perf and not slow"` | Unit and regression tests, without `slow` and `perf` |
| Release-tag push | `just test --all` (enforced by `tools/check_full_tests_before_tag_push.py`) | Everything; refuses to run without RAFT (`just setup-raft`) |

A green CI pipeline therefore means the pre-push selection passes on every platform. The RAFT job skips pull requests because its year on the real RAFT is slow; to run it on a branch, start the `tests` workflow from the Actions tab. Apart from that one RAFT year, the `slow` and `perf` tests run only at the release-tag gate.

All three run Python with `-X warn_default_encoding`, and `pytest.ini` turns the resulting warning into a failure for TANGO and test code: a text file opened without `encoding="utf-8"` reads as cp1252 on Windows and can fail there. Plain `uv run pytest` skips this check.

## Running locally

```bash
just test                     # same selection as the pre-push hook
just test --all               # everything, including slow and perf
just test --templates         # only the templates regression slice
uv run pytest tests/unit -x   # unit tests, stop at the first failure
```

## Writing a test

1. Unit tests go in `tests/unit/`. They build objects directly and do not run a full simulation.
2. A test that runs a full simulation goes in `tests/regtest/`. If it needs the real number of timesteps, mark it `@pytest.mark.slow` and add a reduced-timestep companion.
3. A new template must be added to `_CONFIGS` in `regtest/test_templates.py`, with its golden LCOE.
4. Name tests after the behavior they check, for example `test_max_mass_rate_is_rejected`.

## Known limitation

The regression tier does not run in CI. The options are to speed it up until it fits the runner's time limit, or to add a manually triggered CI job for it. See "CI test subset" in [`docs/TANGO_vision_and_roadmap/README.md`](https://github.com/GEG-ETHZ/TANGO-core/blob/main/docs/TANGO_vision_and_roadmap/README.md).
