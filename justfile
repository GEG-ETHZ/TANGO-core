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
    elif [[ "$args" == *"--templates"* ]]; then
        # Full-length regression coverage for every templates/*.yml
        # (see tests/regtest/test_templates.py's own module docstring
        # and CONTRIBUTING.md's "Every templates/ YAML is
        # regression-tested" Commandment) -- already included in --all
        # above (no -m filter there), this is just a fast, direct way to
        # run only this slice without the rest of the suite.
        args="${args/--templates/}"
        uv run pytest -v tests/regtest/test_templates.py tests/regtest/test_lcoe_regression.py $args
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
        echo "just test: pytest rejected an argument above (usage error) — check for a typo of --all/--templates/--perf/--fast, or an invalid pytest flag." >&2
    fi
    exit "$status"

# Update src/tango.hash from what's staged under src/tango/, and stage it, so the next commit passes the hash hook first time
hash-src:
    uv run python tools/hash_tango.py --stage

# Run all quality checks in CI order: format → lint → typecheck → test
check: fmt lint typecheck test

# Runs configs one at a time; pass names to run only those: `just phase-diagrams CO2_EGS_electric hydro_sf_electric`.
# Write each template's P-h phase diagrams (plus full results) to scratch_output/<config>/
[unix]
phase-diagrams *configs:
    #!/usr/bin/env sh
    # -u: an unset variable is an error instead of an empty string.
    # No -e: a config that fails is recorded and the loop moves on; failures
    # are reported together at the end.
    set -u
    if [ -n "{{configs}}" ]; then set -- {{configs}}; else set -- $(ls templates/*.yml | xargs -n1 basename); fi
    failed=""
    for c in "$@"; do
        c="${c%.yml}"; out="scratch_output/$c"
        rm -rf "$out"; mkdir -p "$out"
        echo "== $c"
        if uv run tango_cli run --save-dir "$out" "templates/$c.yml" > "$out/run.log" 2>&1; then
            ls "$out"/*.phase_*.html 2>/dev/null | sed 's/^/   /'
        else
            echo "   FAILED -- see $out/run.log"; failed="$failed $c"
        fi
    done
    if [ -n "$failed" ]; then echo "Failed:$failed"; exit 1; fi

[windows]
phase-diagrams *configs:
    $names = if ("{{configs}}") { "{{configs}}".Split(" ", [StringSplitOptions]::RemoveEmptyEntries) } else { Get-ChildItem templates/*.yml | ForEach-Object { $_.BaseName } }; $failed = @(); foreach ($c in $names) { $c = $c -replace '\.yml$', ''; $out = "scratch_output/$c"; Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue; New-Item -ItemType Directory -Path $out | Out-Null; Write-Output "== $c"; uv run tango_cli run --save-dir $out "templates/$c.yml" *> "$out/run.log"; if ($LASTEXITCODE -eq 0) { Get-ChildItem "$out/*.phase_*.html" | ForEach-Object { "   $($_.FullName)" } } else { Write-Output "   FAILED -- see $out/run.log"; $failed += $c } }; if ($failed.Count -gt 0) { Write-Output "Failed: $($failed -join ' ')"; exit 1 }

# Needs the draw.io desktop app (its CLI does the export): /Applications/draw.io.app on macOS, or
# `drawio` on PATH on Linux (headless Linux also needs xvfb-run). Fonts aren't embedded, which keeps
# each SVG ~40 KB instead of ~500 KB; viewers fall back to their default sans-serif.
# Writes the README banner (docs/assets/) and the editable diagrams (docs/diagrams/*.drawio.svg), then
# exports every docs/diagrams/src/*.drawio to docs/diagrams/<name>.svg.
# Regenerate the README banner and every diagram under docs/diagrams/; needs the drawio CLI
[unix]
diagrams:
    #!/usr/bin/env sh
    set -eu
    uv run python tools/readme_assets.py
    uv run python tools/diagrams/build.py
    if [ -x /Applications/draw.io.app/Contents/MacOS/draw.io ]; then
        drawio=/Applications/draw.io.app/Contents/MacOS/draw.io
    elif command -v drawio >/dev/null 2>&1; then
        drawio=drawio
    else
        echo "draw.io not found: install the draw.io desktop app (https://github.com/jgraph/drawio-desktop/releases)"; exit 1
    fi
    for src in docs/diagrams/src/*.drawio; do
        out="docs/diagrams/$(basename "$src" .drawio).svg"
        "$drawio" --export --format svg --embed-svg-fonts false --border 10 --output "$out" "$src" >/dev/null 2>&1 || { echo "export failed: $src"; exit 1; }
        echo "$src -> $out"
    done

# templates/*.yml regression coverage lives in `just test --all` (see CONTRIBUTING.md's
# "Every templates/ YAML is regression-tested" Commandment), not duplicated here.
# Smoke-test every script in applications/
[unix]
apps:
    #!/usr/bin/env sh
    # -e: stop at the first command that fails.
    # -u: an unset variable is an error instead of an empty string.
    set -eu
    uv run python applications/demo_hydro_sf_electric/demo_hydro_sf_electric.py
    uv run python applications/demo_well_mesh_convergence/demo_well_mesh_convergence.py
    # Every opt_* app: --smoke runs a 2-generation, population-6 search plus
    # the app's own relaxations (see tango.pymoo_api.OptApp.smoke_args), into
    # a throwaway --save-dir, never outputs/. --no-plot then --plot-only
    # exercises the two-stage optimize/plot DVC split. Not tied to --slow: the
    # full-size runs are `just slurm` / `dvc repro`. Apps under
    # applications/_on_hold/ are skipped (see applications/README.md).
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
                echo "Usage: just slurm [--parallel] [--list] [app ...]"
                echo ""
                echo "Submit full-size Euler (SLURM) runs: sbatch each app's applications/<app>/<app>_job.sh"
                echo "from its own directory. Every name is checked before anything is submitted."
                echo ""
                echo "  app ...     apps to submit, e.g. opt_AGS_ORC_electric opt_hydro_sf_electric"
                echo "              (default: every app under applications/ that has a *_job.sh)"
                echo "  --list      print the apps that have a job script (the default set), then exit"
                echo "  --parallel  submit all jobs to run at the same time. Default: one at a time, each"
                echo "              starting when the previous one ends, whether it succeeded or not"
                echo "              (--dependency=afterany), since each job already uses its whole"
                echo "              48-core allocation"
                echo ""
                echo "Refuses to submit if the uv environment is out of date (compute nodes have no"
                echo "internet, so jobs can't sync it); run \`just setup\` first in that case."
                echo ""
                echo "Also refuses if any requested app already has a job queued or running (squeue lists"
                echo "tango_<app>): two jobs for one app share this checkout and collide on DVC's locks."
                exit 0 ;;
            --list) for f in applications/*/*_job.sh; do basename "$(dirname "$f")"; done; exit 0 ;;
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
    # Two jobs for the same app in this one checkout collide on DVC's locks
    # (each job runs `dvc repro` here), so a second submission while the first
    # is still queued or running fails both. Job names are tango_<app> (see
    # each *_job.sh's --job-name).
    queued=" $(squeue -h -u "$USER" -o %j | tr '\n' ' ') "
    busy=""
    for a in "$@"; do
        a="${a%/}"; a="${a##*/}"
        case "$queued" in *" tango_$a "*) busy="$busy $a" ;; esac
    done
    if [ -n "$busy" ]; then
        echo "Already queued or running (squeue -u $USER):$busy"
        echo "Nothing submitted. Wait for those jobs, or scancel them, then resubmit."
        exit 1
    fi
    prev=""
    for a in "$@"; do
        a="${a%/}"; a="${a##*/}"
        if [ -z "$parallel" ] && [ -n "$prev" ]; then dep="--dependency=afterany:$prev"; else dep=""; fi
        job=$(cd "applications/$a" && sbatch --parsable $dep "${a}_job.sh")
        job="${job%%;*}"
        printf '%-36s job %s%s\n' "$a" "$job" "${dep:+ (after $prev)}"
        prev="$job"
    done

# Run on your laptop, from the checkout to sync into. Euler host and repo default to `euler` and
# ~/tango-core; override with TANGO_EULER_HOST / TANGO_EULER_DIR. See `just slurm-fetch --help`.
# Copy finished Euler results (outputs, logs, dvc.lock, DVC cache) back here (`just slurm-fetch --help` for options)
[unix]
slurm-fetch *args:
    #!/usr/bin/env sh
    # -e: stop at the first command that fails. -u: an unset variable is an error.
    set -eu
    host="${TANGO_EULER_HOST:-euler}"
    remote="${TANGO_EULER_DIR:-tango-core}"
    dry=""
    push=""
    apps=""
    for arg in {{args}}; do
        case "$arg" in
            -h|--help)
                echo "Usage: just slurm-fetch [--dry-run] [--push] [--list] [app ...]"
                echo ""
                echo "Copy each app's outputs/, job logs (*.out/*.err), and dvc.lock from the Euler checkout"
                echo "($host:$remote) into this checkout, then Euler's DVC cache, which \`dvc push\` needs."
                echo "Each app's files are mirrored (--delete), so a file removed on Euler is removed here."
                echo "The DVC cache is only added to, never pruned."
                echo ""
                echo "  app ...     apps to fetch (default: every app under applications/ that has a *_job.sh)"
                echo "  --dry-run   show what would change, change nothing"
                echo "  --push      run \`uv run dvc push\` afterwards"
                echo "  --list      print the apps that have a job script (the default set), then exit"
                echo ""
                echo "Refuses if any requested app still has a job queued or running on Euler (squeue lists"
                echo "tango_<app>): its outputs would be half-written. Override the host or repo path with"
                echo "TANGO_EULER_HOST / TANGO_EULER_DIR."
                exit 0 ;;
            -n|--dry-run) dry="-n" ;;
            --list) for f in applications/*/*_job.sh; do basename "$(dirname "$f")"; done; exit 0 ;;
            --push) push=1 ;;
            -*) echo "unknown option: $arg (see just slurm-fetch --help)"; exit 1 ;;
            *) apps="$apps $arg" ;;
        esac
    done
    if command -v sbatch >/dev/null 2>&1; then echo "Run this on your laptop, not on Euler."; exit 1; fi
    if [ -n "$apps" ]; then set -- $apps; else set -- $(ls applications/*/*_job.sh | xargs -n1 dirname | xargs -n1 basename); fi
    for a in "$@"; do
        a="${a%/}"; a="${a##*/}"
        [ -d "applications/$a" ] || { echo "no such app: applications/$a"; exit 1; }
    done
    queued=" $(ssh "$host" 'squeue -h -u "$USER" -o %j' | tr '\n' ' ') "
    busy=""
    for a in "$@"; do
        a="${a%/}"; a="${a##*/}"
        case "$queued" in *" tango_$a "*) busy="$busy $a" ;; esac
    done
    if [ -n "$busy" ]; then
        echo "Still queued or running on $host:$busy"
        echo "Nothing fetched. Wait for those jobs to finish, or leave those apps out."
        exit 1
    fi
    for a in "$@"; do
        a="${a%/}"; a="${a##*/}"
        echo "== $a"
        # Captured rather than piped, so a failing rsync still stops the recipe.
        changes=$(rsync -a $dry --itemize-changes --delete \
            --include='outputs/***' --include='*.out' --include='*.err' --include='dvc.lock' --exclude='*' \
            "$host:$remote/applications/$a/" "applications/$a/")
        # Spell out rsync's change codes; skip directories whose only change is a timestamp.
        printf '%s\n' "$changes" | awk '
            { code = $1; name = substr($0, length(code) + 1); sub(/^ +/, "", name) }
            code ~ /^\*deleting/ { print "  deleted  " name; n++; next }
            code ~ /^>f\+/       { print "  new      " name; n++; next }
            code ~ /^>f/         { print "  updated  " name; n++; next }
            code ~ /^cd\+/       { print "  new dir  " name; n++; next }
            END { if (!n) print "  no changes" }'
    done
    echo "== DVC cache"
    rsync -a $dry "$host:$remote/.dvc/cache/" ".dvc/cache/"
    # Silence google-api-core's Python-version FutureWarning and gRPC's fork-handler INFO lines.
    if [ -n "$push" ] && [ -z "$dry" ]; then
        PYTHONWARNINGS='ignore::FutureWarning' GRPC_VERBOSITY=ERROR uv run dvc push
    fi

# Works on Euler and on a laptop that rsynced the logs back. Never touches the log of a job that
# squeue still lists. See `just slurm-clean --help`.
# Delete old SLURM job logs (*.out/*.err), keeping each app's newest (`just slurm-clean --help` for options)
[unix]
slurm-clean *args:
    #!/usr/bin/env sh
    # -e: stop at the first command that fails. -u: an unset variable is an error.
    set -eu
    keep_newest=1
    dry_run=""
    partials=""
    for arg in {{args}}; do
        case "$arg" in
            -h|--help)
                echo "Usage: just slurm-clean [--all] [--partials] [--dry-run]"
                echo ""
                echo "Delete SLURM job logs (<app>_<jobid>.out/.err) in applications/<app>/ and"
                echo "applications/_on_hold/<app>/. By default each app keeps its newest job's logs."
                echo "Logs of jobs that squeue still lists (pending or running) are never deleted."
                echo ""
                echo "  --all       delete every app's logs, including the newest"
                echo "  --partials  also delete each app's outputs/pareto_results_partial.csv and"
                echo "              outputs/pareto_configs_partial/ (an interrupted run's progress), except"
                echo "              for apps with a job still queued or running"
                echo "  --dry-run   list what would be deleted, delete nothing"
                exit 0 ;;
            --all) keep_newest="" ;;
            --partials) partials=1 ;;
            -n|--dry-run) dry_run=1 ;;
            *) echo "unknown option: $arg (see just slurm-clean --help)"; exit 1 ;;
        esac
    done
    # Jobs that are still pending or running, and their apps (job name tango_<app>);
    # squeue only exists on Euler.
    active=" "
    active_apps=" "
    if command -v squeue >/dev/null 2>&1; then
        active=" $(squeue -h -u "$USER" -o %i | tr '\n' ' ') "
        active_apps=" $(squeue -h -u "$USER" -o %j | sed 's/^tango_//' | tr '\n' ' ') "
    fi
    n=0
    for dir in applications/*/ applications/_on_hold/*/; do
        [ -d "$dir" ] || continue
        # Job IDs from <app>_<jobid>.out/.err, newest (largest) last.
        ids=$(ls "$dir" | sed -n -E 's/.*_([0-9]+)\.(out|err)$/\1/p' | sort -un)
        [ -n "$ids" ] || continue
        newest=$(printf '%s\n' "$ids" | tail -n 1)
        for id in $ids; do
            if [ -n "$keep_newest" ] && [ "$id" = "$newest" ]; then continue; fi
            case "$active" in *" $id "*) echo "keeping $dir*_$id.* (job $id is still queued or running)"; continue ;; esac
            for f in "$dir"*_"$id".out "$dir"*_"$id".err; do
                [ -e "$f" ] || continue
                if [ -n "$dry_run" ]; then echo "would delete $f"; else rm -- "$f"; fi
                n=$((n + 1))
            done
        done
    done
    if [ -n "$partials" ]; then
        for dir in applications/*/ applications/_on_hold/*/; do
            app=$(basename "$dir")
            case "$active_apps" in *" $app "*) echo "keeping $app's partial outputs (it has a job queued or running)"; continue ;; esac
            for f in "${dir}outputs/pareto_results_partial.csv" "${dir}outputs/pareto_configs_partial"; do
                [ -e "$f" ] || continue
                if [ -n "$dry_run" ]; then echo "would delete $f"; else rm -r -- "$f"; fi
                n=$((n + 1))
            done
        done
    fi
    if [ -n "$dry_run" ]; then echo "$n files would be deleted"; else echo "deleted $n files"; fi

[windows]
apps:
    uv run python applications/demo_hydro_sf_electric/demo_hydro_sf_electric.py
    uv run python applications/demo_well_mesh_convergence/demo_well_mesh_convergence.py
    # See the [unix] demos recipe's comment above the equivalent loop for what
    # each opt_* app's --smoke does.
    Get-ChildItem applications -Directory -Filter "opt_*" | ForEach-Object { $script = Join-Path $_.FullName "$($_.Name).py"; if ((Test-Path $script) -and (Select-String -Path $script -Pattern "APP = OptApp\(" -Quiet)) { Write-Output "== $($_.Name)"; $tmp = Join-Path $env:TEMP ([guid]::NewGuid()); New-Item -ItemType Directory -Path $tmp | Out-Null; uv run python $script --smoke --save-dir $tmp --log-level ERROR --no-plot --quiet; if ($LASTEXITCODE -ne 0) { exit 1 }; uv run python $script --save-dir $tmp --log-level ERROR --plot-only; if ($LASTEXITCODE -ne 0) { exit 1 } } }

# Preview the docs site on localhost with live reload
docs:
    uv run --group docs zensical serve

# Build the docs site into site/ (what CI runs on every pull request)
docs-build:
    uv run --group docs zensical build --clean

# Preview the internal docs (adds the task log, roadmap, and archive), the build docs.yml deploys
docs-internal:
    uv run --group docs zensical serve -f mkdocs.internal.yml

# Regenerate the README banner (docs/assets/) and the editable diagrams (docs/diagrams/); needs the drawio CLI.
# The [unix] recipe above also exports the topology diagrams.
[windows]
diagrams:
    uv run python tools/readme_assets.py
    uv run python tools/diagrams/build.py

# Regenerate the config-key and output tables of the docs from the code
docs-gen:
    uv run python tools/gen_reference.py
