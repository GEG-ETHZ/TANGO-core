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
demos *args:
    #!/usr/bin/env bash
    set -euo pipefail
    # applications/run_*/ pipelines use --smoke (tiny corner-of-hypercube design
    # matrix, written to a fresh OS tempdir every run — never outputs/) instead
    # of their real multi-thousand-design grids — this checks the pipeline code
    # still runs end to end, not that every design converges (some corner
    # designs are expected to fail physically/numerically, same as in a real
    # sweep — that's fine, a non-zero *script* exit code is the failure signal
    # this target cares about). --slow drops --smoke to run the real grids
    # instead — much longer, and DOES write to outputs/.
    smoke_flag="--smoke"
    if [[ "{{args}}" == *"--slow"* ]]; then
        smoke_flag=""
    fi
    uv run python examples/tango_next/demo_flexible_sf.py
    uv run python examples/tango_next/sweep_demo_AGS_direct_heat.py
    uv run python applications/run_AGS_direct_heat_sweep/run_AGS_direct_heat_sweep.py $smoke_flag --n-workers 4 --quiet
    uv run python applications/run_AGS_sweep/run_AGS_sweep.py $smoke_flag --n-workers 4 --quiet
    uv run python applications/run_EGS_direct_heat_sweep/run_EGS_direct_heat_sweep.py $smoke_flag --n-workers 4 --quiet
    uv run python applications/run_flexible_DF_manual_sweep/run_flexible_DF_manual_sweep.py $smoke_flag --n-workers 2 --quiet
