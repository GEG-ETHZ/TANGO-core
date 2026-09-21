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
        echo "just test: pytest rejected an argument above (usage error) — check for a typo of --all/--perf/--fast, or an invalid pytest flag." >&2
    fi
    exit "$status"

# Run all quality checks in CI order: format → lint → typecheck → test
check: fmt lint typecheck test

# Smoke-test every demo/example/application script. --slow: real multi-thousand-design grids, not --smoke.
[unix]
demos *args:
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
    #
    # Also runs every example_configs/*.yml file through `tango_cli run`
    # (not just the two explicitly-named demo scripts above) so a new example
    # YAML gets smoke coverage automatically without a justfile edit.
    # `-p N` (unix only) controls how many of those YAML runs go in parallel —
    # `just demos -p 4`; omit for sequential (default). Windows has no `-p` or
    # `--slow` support yet (sequential, --smoke only) — see `_setup-direnv`
    # above for the same unix/windows split pattern.
    p=1
    smoke_flag="--smoke"
    set -- {{args}}
    while [ $# -gt 0 ]; do
        case "$1" in
            -p) p="$2"; shift 2 ;;
            --slow) smoke_flag=""; shift ;;
            *) echo "just demos: unrecognized argument: $1 (accepts only -p N / --slow)" >&2; exit 1 ;;
        esac
    done
    uv run python applications/demo_hydro_sf_electric/demo_hydro_sf_electric.py
    uv run python applications/sweep_demo_AGS_direct_heat/sweep_demo_AGS_direct_heat.py
    uv run python applications/demo_well_mesh_convergence/demo_well_mesh_convergence.py
    find example_configs -maxdepth 1 -name '*.yml' -print0 | xargs -0 -n1 -P "$p" uv run tango_cli --log-level WARNING run
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
demos:
    uv run python applications/demo_hydro_sf_electric/demo_hydro_sf_electric.py
    uv run python applications/sweep_demo_AGS_direct_heat/sweep_demo_AGS_direct_heat.py
    uv run python applications/demo_well_mesh_convergence/demo_well_mesh_convergence.py
    Get-ChildItem example_configs/*.yml | ForEach-Object { uv run tango_cli --log-level WARNING run $_.FullName }
    # No -p/--slow support on Windows yet (see [unix] demos above) -- always --smoke.
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
