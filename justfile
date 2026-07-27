set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# One-time setup after cloning: install deps, approve .envrc (macOS/Linux), and install git hooks
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

# Type-check with mypy
# TODO: expand to `uv run mypy .` once src/tango/ and tests/ are clean
typecheck:
    uv run mypy src/tango_next/

# Run test suite
test:
    uv run pytest -v

# Run all quality checks in CI order: format → lint → typecheck → test
check: fmt lint typecheck test

# Smoke-test every demo/example/application script — fast, not full sweeps.
# applications/run_*/ pipelines use --smoke (tiny corner-of-hypercube design
# matrix, written to a fresh OS tempdir every run — never outputs/) instead
# of their real multi-thousand-design grids — this checks the pipeline code
# still runs end to end, not that every design converges (some corner
# designs are expected to fail physically/numerically, same as in a real
# sweep — that's fine, a non-zero *script* exit code is the failure signal
# this target cares about).
demos:
    uv run python examples/tango_next/demo_flexible_sf.py
    uv run python examples/tango_next/sweep_demo_AGS_direct_heat.py
    uv run python applications/run_AGS_direct_heat_sweep/run_AGS_direct_heat_sweep.py --smoke --n-workers 4 --quiet
    uv run python applications/run_AGS_sweep/run_AGS_sweep.py --smoke --n-workers 4 --quiet
    uv run python applications/run_EGS_direct_heat_sweep/run_EGS_direct_heat_sweep.py --smoke --n-workers 4 --quiet
    uv run python applications/run_flexible_DF_manual_sweep/run_flexible_DF_manual_sweep.py --smoke --n-workers 2 --quiet
