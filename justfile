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
    # -u: an unset variable is an error instead of an empty string.
    # -o pipefail: a pipeline fails if any command in it fails, not just the last.
    # No -e: pytest's exit status is captured below and reported, not aborted on.
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

# Update src/tango.hash from what's staged under src/tango/, and stage it, so the next commit passes the hash hook first time
[unix]
hash-src:
    #!/usr/bin/env sh
    # -e: stop at the first command that fails.
    # -u: an unset variable is an error instead of an empty string.
    set -eu
    # The hash covers the STAGED src/tango/ tree (git's index), the same thing
    # the hash-tango pre-commit hook hashes, so stage your src/tango/ changes
    # first. tools/hash_tango.py exits 1 when it rewrites the file (that's how
    # it blocks a commit as a hook); here that just means "updated".
    status=0
    uv run python tools/hash_tango.py || status=$?
    if [ "$status" -gt 1 ]; then exit "$status"; fi
    git add src/tango.hash
    if [ "$status" -eq 1 ]; then echo "Staged the updated src/tango.hash."; else echo "src/tango.hash already up to date."; fi

# Run all quality checks in CI order: format → lint → typecheck → test
check: fmt lint typecheck test

# Runs configs one at a time; pass names to run only those: `just phase-diagrams CO2_EGS_electric hydro_sf_electric`.
# Write each example config's P-h phase diagrams (plus full results) to scratch_output/<config>/
[unix]
phase-diagrams *configs:
    #!/usr/bin/env sh
    # -u: an unset variable is an error instead of an empty string.
    # No -e: a config that fails is recorded and the loop moves on; failures
    # are reported together at the end.
    set -u
    if [ -n "{{configs}}" ]; then set -- {{configs}}; else set -- $(ls example_configs/*.yml | xargs -n1 basename); fi
    failed=""
    for c in "$@"; do
        c="${c%.yml}"; out="scratch_output/$c"
        rm -rf "$out"; mkdir -p "$out"
        echo "== $c"
        if uv run tango_cli run --save-dir "$out" "example_configs/$c.yml" > "$out/run.log" 2>&1; then
            ls "$out"/*.phase_*.html 2>/dev/null | sed 's/^/   /'
        else
            echo "   FAILED -- see $out/run.log"; failed="$failed $c"
        fi
    done
    if [ -n "$failed" ]; then echo "Failed:$failed"; exit 1; fi

[windows]
phase-diagrams *configs:
    $names = if ("{{configs}}") { "{{configs}}".Split(" ", [StringSplitOptions]::RemoveEmptyEntries) } else { Get-ChildItem example_configs/*.yml | ForEach-Object { $_.BaseName } }; $failed = @(); foreach ($c in $names) { $c = $c -replace '\.yml$', ''; $out = "scratch_output/$c"; Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue; New-Item -ItemType Directory -Path $out | Out-Null; Write-Output "== $c"; uv run tango_cli run --save-dir $out "example_configs/$c.yml" *> "$out/run.log"; if ($LASTEXITCODE -eq 0) { Get-ChildItem "$out/*.phase_*.html" | ForEach-Object { "   $($_.FullName)" } } else { Write-Output "   FAILED -- see $out/run.log"; $failed += $c } }; if ($failed.Count -gt 0) { Write-Output "Failed: $($failed -join ' ')"; exit 1 }

# example_configs/*.yml regression coverage lives in `just test --all` (see CONTRIBUTING.md's
# "Every example_configs/ YAML is regression-tested" Commandment), not duplicated here.
# Smoke-test every script in applications/ (--slow: the sweeps' real design grids instead of --smoke)
[unix]
apps *args:
    #!/usr/bin/env sh
    # -e: stop at the first command that fails.
    # -u: an unset variable is an error instead of an empty string.
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
    # here on purpose, the same way each opt_* app's --smoke relaxes any
    # constraint a tiny population would miss.
    tmp=$(mktemp -d); uv run python applications/opt_hydro_df_electric_surrogate/run_trajectory.py --pop-size 8 --n-gen 2 --save-dir "$tmp" --quiet; uv run python applications/opt_hydro_df_electric_surrogate/train_surrogate.py --save-dir "$tmp" --cv-folds 2; uv run python applications/opt_hydro_df_electric_surrogate/optimize_surrogate.py --n-max-gen 2 --pop-size 6 --save-dir "$tmp" --no-plot --quiet; uv run python applications/opt_hydro_df_electric_surrogate/validate_surrogate.py --save-dir "$tmp" --tolerance 1.0 --no-plot
    # Every opt_* app (not the surrogate pipeline above): --smoke runs a
    # 2-generation, population-6 search plus the app's own relaxations (see
    # tango.pymoo_api.OptApp.smoke_args), into a throwaway --save-dir, never
    # outputs/. --no-plot then --plot-only exercises the two-stage
    # optimize/plot DVC split. Not tied to --slow: the full-size runs are
    # `just slurm` / `dvc repro`.
    for app in applications/opt_*/; do \
        name=$(basename "$app"); script="$app$name.py"; \
        grep -q "APP = OptApp(" "$script" 2>/dev/null || continue; \
        echo "== $name"; tmp=$(mktemp -d); \
        uv run python "$script" --smoke --save-dir "$tmp" --log-level ERROR --no-plot --quiet && \
        uv run python "$script" --save-dir "$tmp" --log-level ERROR --plot-only || exit 1; \
    done

# Runs sbatch on each app's *_job.sh from its own directory (the job scripts find the repo through
# $SLURM_SUBMIT_DIR), after checking every name. See `just slurm --help` for the full usage.
# Submit full-size Euler (SLURM) runs, one job at a time (`just slurm --help` for options)
[unix]
slurm *args:
    #!/usr/bin/env sh
    # -e: stop at the first command that fails, so nothing is submitted after an error.
    # -u: an unset variable is an error instead of an empty string.
    set -eu
    parallel=""
    apps=""
    for arg in {{args}}; do
        case "$arg" in
            -h|--help)
                echo "Usage: just slurm [--parallel] [app ...]"
                echo ""
                echo "Submit full-size Euler (SLURM) runs: sbatch each app's applications/<app>/<app>_job.sh"
                echo "from its own directory. Every name is checked before anything is submitted."
                echo ""
                echo "  app ...     apps to submit, e.g. opt_AGS_ORC_electric run_AGS_direct_heat_sweep"
                echo "              (default: every app under applications/ that has a *_job.sh)"
                echo "  --parallel  submit all jobs to run at the same time. Default: one at a time, each"
                echo "              starting when the previous one ends, whether it succeeded or not"
                echo "              (--dependency=afterany), since each job already uses its whole"
                echo "              48-core allocation"
                echo ""
                echo "Refuses to submit if the uv environment is out of date (compute nodes have no"
                echo "internet, so jobs can't sync it); run \`just setup\` first in that case."
                exit 0 ;;
            --parallel) parallel=1 ;;
            -*) echo "unknown option: $arg (see just slurm --help)"; exit 1 ;;
            *) apps="$apps $arg" ;;
        esac
    done
    command -v sbatch >/dev/null || { echo "sbatch not found -- run this on Euler"; exit 1; }
    # Compute nodes have no internet, so jobs can't install or rebuild anything
    # (e.g. after a `git pull` that changed pyproject.toml); catch that here,
    # before queueing jobs that would each fail the same way.
    uv sync --check --offline >/dev/null 2>&1 || { echo "The uv environment is out of date: run \`just setup\` (or \`uv sync\`) first, then resubmit."; exit 1; }
    if [ -n "$apps" ]; then set -- $apps; else set -- $(ls applications/*/*_job.sh | xargs -n1 dirname | xargs -n1 basename); fi
    for a in "$@"; do
        a="${a%/}"; a="${a##*/}"
        [ -f "applications/$a/${a}_job.sh" ] || { echo "no job script: applications/$a/${a}_job.sh"; exit 1; }
    done
    prev=""
    for a in "$@"; do
        a="${a%/}"; a="${a##*/}"
        if [ -z "$parallel" ] && [ -n "$prev" ]; then dep="--dependency=afterany:$prev"; else dep=""; fi
        job=$(cd "applications/$a" && sbatch --parsable $dep "${a}_job.sh")
        job="${job%%;*}"
        printf '%-36s job %s%s\n' "$a" "$job" "${dep:+ (after $prev)}"
        prev="$job"
    done

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
    # opt_hydro_df_electric_surrogate's --tolerance is relaxed, and for what
    # each opt_* app's --smoke does.
    $tmp0 = Join-Path $env:TEMP ([guid]::NewGuid()); New-Item -ItemType Directory -Path $tmp0 | Out-Null; uv run python applications/opt_hydro_df_electric_surrogate/run_trajectory.py --pop-size 8 --n-gen 2 --save-dir $tmp0 --quiet; uv run python applications/opt_hydro_df_electric_surrogate/train_surrogate.py --save-dir $tmp0 --cv-folds 2; uv run python applications/opt_hydro_df_electric_surrogate/optimize_surrogate.py --n-max-gen 2 --pop-size 6 --save-dir $tmp0 --no-plot --quiet; uv run python applications/opt_hydro_df_electric_surrogate/validate_surrogate.py --save-dir $tmp0 --tolerance 1.0 --no-plot
    Get-ChildItem applications -Directory -Filter "opt_*" | ForEach-Object { $script = Join-Path $_.FullName "$($_.Name).py"; if ((Test-Path $script) -and (Select-String -Path $script -Pattern "APP = OptApp\(" -Quiet)) { Write-Output "== $($_.Name)"; $tmp = Join-Path $env:TEMP ([guid]::NewGuid()); New-Item -ItemType Directory -Path $tmp | Out-Null; uv run python $script --smoke --save-dir $tmp --log-level ERROR --no-plot --quiet; if ($LASTEXITCODE -ne 0) { exit 1 }; uv run python $script --save-dir $tmp --log-level ERROR --plot-only; if ($LASTEXITCODE -ne 0) { exit 1 } } }
