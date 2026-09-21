# Tests

- `tests/unit/` — fast, isolated tests. Runs in **GitLab CI** on every MR/push
  to `main`/`develop` (`.gitlab-ci.yml`'s `test` job), and locally on every
  `git push` via the `prek` pre-push hook.
- `tests/regtest/` — regression/integration tests (full simulation runs,
  including a fixed historical LCOE reference value). Currently takes 1h+
  end-to-end, which exceeds the GitLab runner timeout — see the 2026-07-16
  pipeline failure (job #1857142, killed after 1h0m0s partway through
  `test_tango.py`). **Not run in CI.** It does run locally via the
  `prek` pre-push hook (`uv run pytest`, no path restriction, covers
  everything under `tests/`), so it still gates every push — just not the
  server-side pipeline.

## Known gap / future task

`tests/regtest/` is slow enough that CI can't run it without hitting the
runner timeout, so CI coverage is currently narrower than local pre-push
coverage. Pick one of:

1. Speed up `tests/regtest/` (parallelize, cut redundant cases, mock slow
   physics calls where correctness isn't what's being tested) until the
   full suite runs comfortably in CI.
2. Keep the fast/slow split permanent: `tests/unit/` runs automatically
   (CI + pre-push) and `tests/regtest/` runs only locally via pre-push plus
   an optional, manually-triggered CI job (`rules: when: manual`) for
   deliberate full-suite runs — but never automatically on every push.

Until one of these is done, treat a green CI pipeline as "unit tests pass,"
not "full suite passes" — the regression suite's guarantees currently only
come from the local pre-push hook.
