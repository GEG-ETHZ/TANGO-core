set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# One-time (idempotent) setup after cloning: install deps, approve .envrc (macOS/Linux), and install git hooks
setup: _setup-direnv
    uv sync
    uv run prek install --hook-type pre-commit --hook-type pre-push --hook-type post-checkout --overwrite

[unix]
_setup-direnv:
    #!/usr/bin/env sh
    if ! command -v direnv >/dev/null 2>&1; then
        echo ""
        echo "Note: direnv not found (optional — install it for automatic environment activation on cd)."
        echo "  macOS:  brew install direnv"
        echo "  Linux:  sudo apt install direnv"
        echo "  Then add the shell hook: https://direnv.net/docs/hook.html"
        echo ""
    else
        grep -q 'direnv hook' ~/.zshrc 2>/dev/null || grep -q 'direnv hook' ~/.bashrc 2>/dev/null || {
            echo ""
            echo "Note: direnv is installed but not hooked into your shell."
            echo "Add one of the following (as appropriate) to your shell rc file and restart your shell:"
            echo "  ~/.zshrc:   eval \"\$(direnv hook zsh)\""
            echo "  ~/.bashrc:  eval \"\$(direnv hook bash)\""
            echo "  See: https://direnv.net/docs/hook.html"
            echo ""
        }
        direnv allow . || {
            echo ""
            echo "Warning: 'direnv allow .' failed — run it manually after checking your .envrc."
            echo ""
        }
    fi

[windows]
_setup-direnv:
    @echo "Note: direnv is not available on Windows — skipping."

# Format Python code with ruff
fmt:
    uv run ruff format .

# Lint Python code with ruff
lint:
    uv run ruff check .

# Type-check tango (legacy old-tango package removed; tests/ isn't clean enough for mypy yet)
typecheck:
    # TODO: expand to `uv run mypy .` once tests/ are clean
    uv run mypy src/tango/

# Run test suite. No args/--fast: fast subset (matches pre-push). --perf: perf tests only. --all: everything.
test *args:
    #!/usr/bin/env bash
    set -uo pipefail
    # For anything else, pass your own -m straight through, e.g.
    # `just test -m "perf"` or `just test -m "slow"`.
    args="{{args}}"
    if [[ "$args" == *"--all"* ]]; then
        args="${args/--all/}"
        uv run pytest -v $args
    elif [[ "$args" == *"--example-configs"* ]]; then
        # Full-length regression coverage for every example_configs/*.yml
        # (see tests/regtest/test_example_configs.py's own module docstring
        # and CONTRIBUTING.md's "Every example_configs/ YAML is
        # regression-tested" Commandment) -- already included in --all
        # above (no -m filter there), this is just a fast, direct way to
        # run only this slice without the rest of the suite.
        args="${args/--example-configs/}"
        uv run pytest -v tests/regtest/test_example_configs.py tests/regtest/test_lcoe_regression.py $args
    elif [[ "$args" == *"--perf"* ]]; then
        args="${args/--perf/}"
        uv run pytest -v -m "perf" $args
    else
        args="${args/--fast/}"
        uv run pytest -v -m "not perf and not slow" $args
    fi
    status=$?
    # pytest's own arg parser is the only thing that can validate free-form
    # pytest flags (-m/-k/-x/file paths/...) — exit 4 is specifically its
    # USAGE_ERROR code (a bad/unrecognized flag, as opposed to a real test
    # failure = 1), so only THIS case gets an extra line pointing back at
    # `just test`, not every failure.
    if [ "$status" -eq 4 ]; then
        echo "" >&2
        echo "just test: pytest rejected an argument above (usage error) — check for a typo of --all/--example-configs/--perf/--fast, or an invalid pytest flag." >&2
    fi
    exit "$status"

# Run all quality checks in CI order: format → lint → typecheck → test
check: fmt lint typecheck test

# Smoke-test every script in applications/. --slow: real multi-thousand-design grids, not --smoke.
# example_configs/*.yml regression coverage lives in `just test --all` (see CONTRIBUTING.md's
# "Every example_configs/ YAML is regression-tested" Commandment), not duplicated here.
[unix]
apps *args:
    #!/usr/bin/env sh
    set -eu
    # applications/run_*/ pipelines use --smoke (tiny corner-of-hypercube design
    # matrix, written to a fresh OS tempdir every run — never outputs/) instead
    # of their real multi-thousand-design grids — this checks the pipeline code
    # still runs end to end, not that every design converges (some corner
    # designs are expected to fail physically/numerically, same as in a real
    # sweep — that's fine, a non-zero *script* exit code is the failure signal
    # this target cares about). --slow drops --smoke to run the real grids
    # instead — much longer, and DOES write to outputs/.
    smoke_flag="--smoke"
    set -- {{args}}
    while [ $# -gt 0 ]; do
        case "$1" in
            -h|--help)
                echo "just apps [--slow]"
                echo ""
                echo "Smoke-test every applications/ script."
                echo ""
                echo "  --slow    Run the real run_*_sweep design grids instead of their tiny --smoke corner-case grids"
                echo "            (much longer, and DOES write to outputs/, unlike the default --smoke runs)."
                exit 0
                ;;
            --slow) smoke_flag=""; shift ;;
            *) echo "just apps: unrecognized argument: $1 (accepts only --slow / --help)" >&2; exit 1 ;;
        esac
    done
    uv run python applications/demo_hydro_sf_electric/demo_hydro_sf_electric.py
    uv run python applications/sweep_demo_AGS_direct_heat/sweep_demo_AGS_direct_heat.py
    uv run python applications/demo_well_mesh_convergence/demo_well_mesh_convergence.py
    # run_*_sweep apps' own --smoke (tiny corner-of-hypercube grid, never
    # touches outputs/) — same $smoke_flag/--slow split as everything else
    # in this recipe.
    uv run python applications/run_AGS_direct_heat_sweep/run_AGS_direct_heat_sweep.py $smoke_flag --n-workers 4 --quiet
    uv run python applications/run_EGS_direct_heat_sweep/run_EGS_direct_heat_sweep.py $smoke_flag --n-workers 4 --quiet
    uv run python applications/run_hydro_df_electric_sweep/run_hydro_df_electric_sweep.py $smoke_flag --n-workers 2 --quiet
    # opt_hydro_df_electric_surrogate's 4-stage DVC pipeline (trajectory ->
    # train -> optimize -> validate), chained through one shared --save-dir
    # tempdir since each stage reads the previous one's output from there.
    # Tiny --pop-size/--n-gen at every stage, same "pipeline runs end to
    # end" goal as the other smoke coverage here, not real surrogate
    # accuracy — validate_surrogate.py's default 1% tolerance is what it's
    # FOR (catching a genuinely bad surrogate) and WILL legitimately fail
    # on this little training data, so --tolerance 1.0 (100%) is relaxed
    # here on purpose, the same way opt_AGS_direct_heat.py's
    # --min-production-temperature-c is relaxed above.
    tmp=$(mktemp -d); uv run python applications/opt_hydro_df_electric_surrogate/run_trajectory.py --pop-size 8 --n-gen 2 --save-dir "$tmp" --quiet; uv run python applications/opt_hydro_df_electric_surrogate/train_surrogate.py --save-dir "$tmp" --cv-folds 2; uv run python applications/opt_hydro_df_electric_surrogate/optimize_surrogate.py --n-max-gen 2 --pop-size 6 --save-dir "$tmp" --no-plot --quiet; uv run python applications/opt_hydro_df_electric_surrogate/validate_surrogate.py --save-dir "$tmp" --tolerance 1.0 --no-plot
    # opt_*.py has no --smoke flag of its own (not a generate/sweep pipeline)
    # -- tiny --n-max-gen/--pop-size + a fresh tempdir --save-dir gets the
    # same "pipeline still runs end to end" coverage without the real
    # ~200-gen/40-pop search or touching outputs/. Not tied to --slow: there's
    # no "real" variant to switch to here (that's what the Euler job script /
    # `dvc repro` are for).
    # Each app runs --no-plot then --plot-only against the same --save-dir,
    # exercising the two-stage optimize/plot DVC split (see each app's
    # dvc.yaml) instead of only the default combined path.
    # opt_AGS_direct_heat.py's production_temperature_constraint's real
    # threshold (105 degC) is tuned for the actual search, not this tiny
    # smoke population -- at --pop-size 6/--n-max-gen 2, it's easy for
    # every evaluated design to miss it by chance, leaving an empty
    # Pareto front that only proves the search ran, not that plotting on
    # a real result works. --min-production-temperature-c relaxes it so
    # this smoke run reliably gets several real designs through the WHOLE
    # pipeline (search + plot), not just an empty-input no-op.
    tmp=$(mktemp -d); uv run python applications/opt_AGS_direct_heat/opt_AGS_direct_heat.py --n-max-gen 2 --pop-size 6 --min-production-temperature-c 50 --save-dir "$tmp" --log-level ERROR --no-plot; uv run python applications/opt_AGS_direct_heat/opt_AGS_direct_heat.py --save-dir "$tmp" --log-level ERROR --plot-only
    tmp=$(mktemp -d); uv run python applications/opt_hydro_df_electric/opt_hydro_df_electric.py --n-max-gen 2 --pop-size 6 --save-dir "$tmp" --log-level ERROR --no-plot; uv run python applications/opt_hydro_df_electric/opt_hydro_df_electric.py --save-dir "$tmp" --log-level ERROR --plot-only
    tmp=$(mktemp -d); uv run python applications/opt_hydro_sf_electric/opt_hydro_sf_electric.py --n-max-gen 2 --pop-size 6 --save-dir "$tmp" --log-level ERROR --no-plot; uv run python applications/opt_hydro_sf_electric/opt_hydro_sf_electric.py --save-dir "$tmp" --log-level ERROR --plot-only

[windows]
apps:
    uv run python applications/demo_hydro_sf_electric/demo_hydro_sf_electric.py
    uv run python applications/sweep_demo_AGS_direct_heat/sweep_demo_AGS_direct_heat.py
    uv run python applications/demo_well_mesh_convergence/demo_well_mesh_convergence.py
    # No --slow support on Windows yet (see [unix] apps above) -- always --smoke.
    uv run python applications/run_AGS_direct_heat_sweep/run_AGS_direct_heat_sweep.py --smoke --n-workers 4 --quiet
    uv run python applications/run_EGS_direct_heat_sweep/run_EGS_direct_heat_sweep.py --smoke --n-workers 4 --quiet
    uv run python applications/run_hydro_df_electric_sweep/run_hydro_df_electric_sweep.py --smoke --n-workers 2 --quiet
    # See the [unix] demos recipe's comment above the equivalent line for why
    # opt_hydro_df_electric_surrogate's --tolerance is relaxed and why
    # --min-production-temperature-c is relaxed below.
    $tmp0 = Join-Path $env:TEMP ([guid]::NewGuid()); New-Item -ItemType Directory -Path $tmp0 | Out-Null; uv run python applications/opt_hydro_df_electric_surrogate/run_trajectory.py --pop-size 8 --n-gen 2 --save-dir $tmp0 --quiet; uv run python applications/opt_hydro_df_electric_surrogate/train_surrogate.py --save-dir $tmp0 --cv-folds 2; uv run python applications/opt_hydro_df_electric_surrogate/optimize_surrogate.py --n-max-gen 2 --pop-size 6 --save-dir $tmp0 --no-plot --quiet; uv run python applications/opt_hydro_df_electric_surrogate/validate_surrogate.py --save-dir $tmp0 --tolerance 1.0 --no-plot
    $tmp1 = Join-Path $env:TEMP ([guid]::NewGuid()); New-Item -ItemType Directory -Path $tmp1 | Out-Null; uv run python applications/opt_AGS_direct_heat/opt_AGS_direct_heat.py --n-max-gen 2 --pop-size 6 --min-production-temperature-c 50 --save-dir $tmp1 --log-level ERROR --no-plot; uv run python applications/opt_AGS_direct_heat/opt_AGS_direct_heat.py --save-dir $tmp1 --log-level ERROR --plot-only
    $tmp2 = Join-Path $env:TEMP ([guid]::NewGuid()); New-Item -ItemType Directory -Path $tmp2 | Out-Null; uv run python applications/opt_hydro_df_electric/opt_hydro_df_electric.py --n-max-gen 2 --pop-size 6 --save-dir $tmp2 --log-level ERROR --no-plot; uv run python applications/opt_hydro_df_electric/opt_hydro_df_electric.py --save-dir $tmp2 --log-level ERROR --plot-only
    $tmp3 = Join-Path $env:TEMP ([guid]::NewGuid()); New-Item -ItemType Directory -Path $tmp3 | Out-Null; uv run python applications/opt_hydro_sf_electric/opt_hydro_sf_electric.py --n-max-gen 2 --pop-size 6 --save-dir $tmp3 --log-level ERROR --no-plot; uv run python applications/opt_hydro_sf_electric/opt_hydro_sf_electric.py --save-dir $tmp3 --log-level ERROR --plot-only

# Preview the docs site on localhost with live reload
docs:
    uv run --group docs zensical serve

# Build the docs site into site/ (what CI runs on every pull request)
docs-build:
    uv run --group docs zensical build --clean

# Preview the internal docs (adds the task log, roadmap and archive); never deploy this build
docs-internal:
    uv run --group docs zensical serve -f mkdocs.internal.yml

# Regenerate the README banner (docs/assets/) and the editable diagrams (docs/diagrams/); needs the drawio CLI
diagrams:
    uv run python tools/readme_assets.py
    uv run python tools/diagrams/build.py

# Regenerate the config-key and output tables of the docs from the code
docs-gen:
    uv run python tools/gen_reference.py
