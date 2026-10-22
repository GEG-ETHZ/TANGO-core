#!/bin/bash
#SBATCH --job-name=tango_n_max_gen_study
#SBATCH --time=6:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem-per-cpu=500M

# ---------------------------------------------------------------------------
# One run of the n_max_gen study (dev_docs/pymoo_generation_budget.md): an
# opt_* app run far past its usual generation cap, recording every evaluated
# design and the generation it was evaluated in, so the front's improvement
# can be measured generation by generation afterwards.
#
# Unlike the apps' own *_job.sh scripts, this does NOT go through `dvc repro`
# and never touches the app's DVC-tracked outputs/. Everything goes to
# studies/n_max_gen/<app>/seed<seed>/ (gitignored). Every other setting
# comes from the app's params.yaml, as in a production run, except:
#   --n-max-gen   the study's generation cap (default 600)
#   --seed        one of several seeds, to tell real improvement from noise
#   --ftol/--xtol 0 and --termination-period n_max_gen, so pymoo's
#                 convergence check can't stop the run early (with tol 0
#                 alone, a front that doesn't change at all for one
#                 termination period would still stop it)
#
# Usage, from the repo root (the .out/.err directory must exist before
# sbatch runs, or SLURM silently writes nothing):
#   mkdir -p studies/n_max_gen
#   for app in opt_hydro_direct_heat opt_hydro_sf_electric opt_AGS_ORC_electric; do
#     for seed in 1 2 3; do
#       sbatch --job-name="nmg_${app}_s${seed}" \
#         --output="studies/n_max_gen/%x_%j.out" --error="studies/n_max_gen/%x_%j.err" \
#         tools/n_max_gen_study_job.sh "$app" "$seed"
#     done
#   done
# ---------------------------------------------------------------------------

# -e: stop at the first command that fails.
# -u: an unset variable is an error instead of an empty string.
# -o pipefail: a pipeline fails if any command in it fails, not just the last.
set -euo pipefail

if [ $# -lt 2 ] || [ $# -gt 3 ]; then
  echo "Usage: sbatch tools/n_max_gen_study_job.sh <opt_app> <seed> [n_max_gen, default 600]" >&2
  exit 1
fi
APP="$1"
SEED="$2"
N_MAX_GEN="${3:-600}"

# sbatch runs a copy of this script from a spool directory, so $0 doesn't
# point here; $SLURM_SUBMIT_DIR is where sbatch was run from, which must be
# the repo root.
REPO_ROOT="$(cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")/..}" && pwd)"
APP_SCRIPT="$REPO_ROOT/applications/$APP/$APP.py"
SAVE_DIR="$REPO_ROOT/studies/n_max_gen/$APP/seed$SEED"

if [ ! -f "$REPO_ROOT/pyproject.toml" ]; then
  echo "Submit from the repo root: $REPO_ROOT has no pyproject.toml." >&2
  exit 1
fi
if [ ! -f "$APP_SCRIPT" ]; then
  echo "No such app script: $APP_SCRIPT" >&2
  exit 1
fi
# The evaluations CSV is appended to, so a rerun into the same directory
# would mix two runs' rows.
if [ -e "$SAVE_DIR" ]; then
  echo "$SAVE_DIR already exists; move or delete it before rerunning." >&2
  exit 1
fi

echo "=========================================="
echo "Job started on: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-}"
echo "Running on node: ${SLURMD_NODENAME:-}"
echo "App: $APP  seed: $SEED  n_max_gen: $N_MAX_GEN"
echo "Commit: $(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
echo "Outputs -> $SAVE_DIR"
echo "=========================================="

# Show pymoo's per-generation table in the .out file as it happens.
export PYTHONUNBUFFERED=1

cd "$REPO_ROOT"
# Compute nodes have no internet, so a job can't install or rebuild anything.
if ! uv sync --check --offline --project "$REPO_ROOT" >/dev/null 2>&1; then
  echo "The uv environment is out of date for $REPO_ROOT." >&2
  echo "On the login node, run: cd $REPO_ROOT && just setup   (or: uv sync)" >&2
  exit 1
fi

mkdir -p "$SAVE_DIR"
uv run --project "$REPO_ROOT" python "$APP_SCRIPT" \
  --save-dir "$SAVE_DIR" \
  --n-max-gen "$N_MAX_GEN" \
  --seed "$SEED" \
  --ftol 0 \
  --xtol 0 \
  --termination-period "$N_MAX_GEN" \
  --capture-trajectory "$SAVE_DIR/evaluations.csv" \
  --skip-param-check \
  --no-plot

echo ""
echo "=========================================="
echo "Job completed on: $(date)"
echo "Total runtime: $SECONDS seconds"
echo "=========================================="
