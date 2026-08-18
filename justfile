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

# Type-check tango_next (src/tango/ isn't clean enough for mypy yet)
typecheck:
    # TODO: expand to `uv run mypy .` once src/tango/ and tests/ are clean
    uv run mypy src/tango_next/

# Run test suite. No args/--fast: fast subset (matches pre-push). --perf: perf tests only. --all: everything.
test *args:
    #!/usr/bin/env bash
    set -euo pipefail
    # For anything else, pass your own -m straight through, e.g.
    # `just test -m "perf"` or `just test -m "slow or old_tango"`.
    args="{{args}}"
    if [[ "$args" == *"--all"* ]]; then
        args="${args/--all/}"
        uv run pytest -v $args
    elif [[ "$args" == *"--perf"* ]]; then
        args="${args/--perf/}"
        uv run pytest -v -m "perf" $args
    else
        args="${args/--fast/}"
        uv run pytest -v -m "not old_tango and not perf and not slow" $args
    fi

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
    # Also runs every examples/tango_next/*.yml file through `tango_next_cli run`
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
            *) shift ;;
        esac
    done
    uv run python applications/tango_next/demo_hydro_sf_electric/demo_hydro_sf_electric.py
    uv run python applications/tango_next/sweep_demo_AGS_direct_heat/sweep_demo_AGS_direct_heat.py
    uv run python applications/run_AGS_direct_heat_sweep/run_AGS_direct_heat_sweep.py $smoke_flag --n-workers 4 --quiet
    uv run python applications/run_AGS_sweep/run_AGS_sweep.py $smoke_flag --n-workers 4 --quiet
    uv run python applications/run_EGS_direct_heat_sweep/run_EGS_direct_heat_sweep.py $smoke_flag --n-workers 4 --quiet
    uv run python applications/run_flexible_DF_manual_sweep/run_flexible_DF_manual_sweep.py $smoke_flag --n-workers 2 --quiet
    find examples/tango_next -maxdepth 1 -name '*.yml' -print0 | xargs -0 -n1 -P "$p" uv run tango_next_cli --log-level WARNING run
    # opt_*.py has no --smoke flag of its own (not a generate/sweep pipeline)
    # -- tiny --n-max-gen/--pop-size + a fresh tempdir --save-dir gets the
    # same "pipeline still runs end to end" coverage without the real
    # ~200-gen/40-pop search or touching outputs/. Not tied to --slow: there's
    # no "real" variant to switch to here (that's what the Euler job script /
    # `dvc repro` are for).
    # Each app runs --no-plot then --plot-only against the same --save-dir,
    # exercising the two-stage optimize/plot DVC split (see each app's
    # dvc.yaml) instead of only the default combined path.
    tmp=$(mktemp -d); uv run python applications/tango_next/opt_AGS_direct_heat/opt_AGS_direct_heat.py --n-max-gen 2 --pop-size 6 --save-dir "$tmp" --log-level ERROR --no-plot; uv run python applications/tango_next/opt_AGS_direct_heat/opt_AGS_direct_heat.py --save-dir "$tmp" --log-level ERROR --plot-only
    tmp=$(mktemp -d); uv run python applications/tango_next/opt_hydro_df_electric/opt_hydro_df_electric.py --n-max-gen 2 --pop-size 6 --save-dir "$tmp" --log-level ERROR --no-plot; uv run python applications/tango_next/opt_hydro_df_electric/opt_hydro_df_electric.py --save-dir "$tmp" --log-level ERROR --plot-only
    tmp=$(mktemp -d); uv run python applications/tango_next/opt_hydro_sf_electric/opt_hydro_sf_electric.py --n-max-gen 2 --pop-size 6 --save-dir "$tmp" --log-level ERROR --no-plot; uv run python applications/tango_next/opt_hydro_sf_electric/opt_hydro_sf_electric.py --save-dir "$tmp" --log-level ERROR --plot-only

[windows]
demos:
    uv run python applications/tango_next/demo_hydro_sf_electric/demo_hydro_sf_electric.py
    uv run python applications/tango_next/sweep_demo_AGS_direct_heat/sweep_demo_AGS_direct_heat.py
    uv run python applications/run_AGS_direct_heat_sweep/run_AGS_direct_heat_sweep.py --smoke --n-workers 4 --quiet
    uv run python applications/run_AGS_sweep/run_AGS_sweep.py --smoke --n-workers 4 --quiet
    uv run python applications/run_EGS_direct_heat_sweep/run_EGS_direct_heat_sweep.py --smoke --n-workers 4 --quiet
    uv run python applications/run_flexible_DF_manual_sweep/run_flexible_DF_manual_sweep.py --smoke --n-workers 2 --quiet
    Get-ChildItem examples/tango_next/*.yml | ForEach-Object { uv run tango_next_cli --log-level WARNING run $_.FullName }
    $tmp1 = Join-Path $env:TEMP ([guid]::NewGuid()); New-Item -ItemType Directory -Path $tmp1 | Out-Null; uv run python applications/tango_next/opt_AGS_direct_heat/opt_AGS_direct_heat.py --n-max-gen 2 --pop-size 6 --save-dir $tmp1 --log-level ERROR --no-plot; uv run python applications/tango_next/opt_AGS_direct_heat/opt_AGS_direct_heat.py --save-dir $tmp1 --log-level ERROR --plot-only
    $tmp2 = Join-Path $env:TEMP ([guid]::NewGuid()); New-Item -ItemType Directory -Path $tmp2 | Out-Null; uv run python applications/tango_next/opt_hydro_df_electric/opt_hydro_df_electric.py --n-max-gen 2 --pop-size 6 --save-dir $tmp2 --log-level ERROR --no-plot; uv run python applications/tango_next/opt_hydro_df_electric/opt_hydro_df_electric.py --save-dir $tmp2 --log-level ERROR --plot-only
    $tmp3 = Join-Path $env:TEMP ([guid]::NewGuid()); New-Item -ItemType Directory -Path $tmp3 | Out-Null; uv run python applications/tango_next/opt_hydro_sf_electric/opt_hydro_sf_electric.py --n-max-gen 2 --pop-size 6 --save-dir $tmp3 --log-level ERROR --no-plot; uv run python applications/tango_next/opt_hydro_sf_electric/opt_hydro_sf_electric.py --save-dir $tmp3 --log-level ERROR --plot-only
