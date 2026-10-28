# TANGO demo walkthrough

Live-demo runbook, split into two audiences. Not meant to be read cold —
it's the script for a presenter who already knows the material; each step
just has the commands and the one-liner to say while running them.

## 1. Users

### 1.1 Installation

Follow [README.md's "General users" → "Installation"](./README.md#general-users)
section directly:

1. Scaffold a project with the GEG cookiecutter template.
2. `uv add "tango-core@git+ssh://git@gitlab.ethz.ch/geg/tango-projects/tango-core.git" --tag v1.1.0`
   (swap in whatever the current release tag is).
3. `tango_core init .` to pull down `templates/` and every
   `applications/` pipeline into the new project (`--app` narrows this to
   specific apps, `--no-apps` skips them entirely — see `--help`).

This is a private GitLab-only distribution (see [NOTICE](../NOTICE)), version-pinned via
the tag.

### 1.2 Run a template

```bash
tango_core run --save-dir results templates/hydro_sf_electric.yml
```

Prints a one-line per-timestep summary and, because of `--save-dir`,
writes three files to `./results/`: the full serialized `.yml`, a
per-timestep `.smry.csv`, and a one-row `.econ.csv`. Every run needs
either `--save-dir` or `--no-save` (which writes nothing), so results are
never lost by forgetting the flag (see 1.3's `--help` output).
(Naming note: called `results/` here, not `tmp/`, since this repo's own
`tmp/` is gitignored scratch space — don't conflate the two.)

### 1.3 Get help

```bash
tango_core --help
tango_core run --help
tango_core init --help
```

Then one application, as a representative example of an app's own
richer `--help`:

```bash
uv run python applications/opt_hydro_df_electric/opt_hydro_df_electric.py --help
```

Every flag documents its own default and where that
default comes from (`params.yaml`/`PymooConfig`), and an explicit CLI
flag overrides `params.yaml` for that run only — nothing gets written
back to `params.yaml`.

### 1.4 Run applications

Three apps, one per family — enough to show breadth without burning the
whole slot re-running similar things:

**Demo (single run, rich plots)**
```bash
uv run python applications/demo_hydro_sf_electric/demo_hydro_sf_electric.py
```
Generates 4 PNGs in `applications/demo_hydro_sf_electric/outputs/` — this
is the answer to "what does tango give you beyond the bare YAML run."

**Optimization (pymoo/NSGA2)**
```bash
uv run python applications/opt_hydro_df_electric/opt_hydro_df_electric.py --n-max-gen 2 --pop-size 8 -p 8 --clean
```
Small enough to finish quickly live. Mention the real production run
(`params.yaml` defaults: 200 generations, population 45) is what
`dvc repro` runs for real, not something to execute on stage.

Skip live, mention only if asked: `opt_hydro_df_electric_surrogate`'s
4-stage chained pipeline (trajectory → train → optimize → validate) —
neat but too much setup for a demo slot.

### 1.5 View results

- `demo_hydro_sf_electric.py`'s 4 PNGs (from 1.4) — open them directly.
- `opt_hydro_df_electric.py`'s Pareto plots, written to
  `applications/opt_hydro_df_electric/outputs/` (`pareto_scatter.png`,
  `pareto_parallel_coordinates.html`, etc.) after the `--clean` run above.
- Contrast with 1.2: `tango_core run --save-dir` gives you raw data
  (YAML/CSV), never plots — rich plots are the applications' job, not
  the engine's.

### 1.6 Optional — debugging into `site-packages` (probably skip)

If there's time and appetite: set a breakpoint inside the installed
`tango_core` package itself (not your own project code) and step into it from
your editor. VS Code's Python debugger (`debugpy`) is the well-trodden
path for this — you'll likely need to disable `justMyCode` to step into
library code. Zed's debugger support is newer; not verified for this
specific flow, so don't attempt it live without having tried it
beforehand. Default to skipping this section if short on time.

---

## 2. Devs

### 2.1 Clone

```bash
git clone git@gitlab.ethz.ch:geg/tango-projects/tango-core.git
cd tango-core
just setup   # uv sync + git hook install (or: uv sync && uv run prek install ...)
```

### 2.2 `just apps`

```bash
just apps
```

Smoke-tests every script in `applications/` (demos, and optimizers at a
tiny population/generation count) — checks the pipeline code runs end to end, not that every design
converges. `templates/` regression coverage does **not** live here
anymore — that moved to `just test --templates` (see below), so
`apps`'s job is purely `applications/` scripts now.

### 2.3 `just test --all`

```bash
just test --all
```

Runs the full pytest suite, including
`tests/regtest/test_templates.py`'s full-length (real
`sim_config.num_tsteps`, not a reduced smoke count) regression coverage
for every `templates/*.yml` — golden LCOE values, injection-well
physics invariants, surface net-power/thermal sanity checks. Locally this
finishes in well under a minute; note that this suite is deliberately
*not* run in GitLab CI (the runner is too slow for it), so this is the
one command that actually exercises everything, and it's the same
command a pre-push hook forces to pass before a `vX.Y.Z` release tag can
be pushed.

### 2.4 Pre-commit / pre-push hooks (explain, don't run)

- Fast checks (ruff, `hash-tango`, `no-commit-to-branch`) run on every
  commit and push.
- Slower checks (mypy, the fast pytest subset) run only on push.
- A release-tag-specific hook additionally runs the *full* `just test
  --all` and blocks the push if it fails — but only when the pushed ref
  is a `vX.Y.Z` tag, so ordinary pushes stay fast.
- See `.pre-commit-config.yaml` / `tools/check_full_tests_before_tag_push.py`.

### 2.5 GitLab CI pipeline (explain, don't run)

- `lint` + `test` jobs run on MRs and on `main`; `test` only runs
  `tests/unit/` (not `tests/regtest/`) because the runner is too slow for
  the full suite — that's exactly why 2.3/2.4 exist as the local
  enforcement point instead.
- A `tag` stage job auto-tags a deleted source branch's tip
  (`bak/$BRANCH`) after a squash merge, to keep CHANGELOG comparison
  links working — unrelated to release tagging.
