#!/bin/bash
#SBATCH --job-name=tango_opt_hydro_df_electric_surrogate
#SBATCH --time=24:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem-per-cpu=500M
#SBATCH --output=opt_hydro_df_electric_surrogate_%j.out
#SBATCH --error=opt_hydro_df_electric_surrogate_%j.err

# ---------------------------------------------------------------------------
# Runs the full hydro_df_electric surrogate pipeline (LHS sample -> real-sim
# sweep -> train random-forest surrogate -> NSGA2 against the surrogate ->
# real-sim validation) via `dvc repro`. Same conventions as the sibling
# opt_hydro_df_electric_job.sh: params.yaml is the single source of truth
# for every hyperparameter, this job does NOT rewrite it and does NOT accept
# CLI overrides -- edit params.yaml directly before submitting.
#
# n_train_workers/n_validate_workers are therefore NOT auto-derived from
# --cpus-per-task -- keep both in sync with whatever --cpus-per-task you
# submit with (leave a few cores headroom for the main driver process/OS),
# same as opt_hydro_df_electric_job.sh's own n_processes convention.
#
# The whole point of this pipeline is a DIRECT comparison against the real
# opt_hydro_df_electric_job.sh run: optimize_surrogate.py's NSGA2 config
# defaults to that app's own params.yaml values unless THIS app's
# params.yaml explicitly overrides them (see that file's own comments) --
# so diff the two jobs' printed elapsed times for the actual surrogate
# speedup, and check outputs/surrogate_validation.csv for accuracy.
#
# Example:
#   sbatch opt_hydro_df_electric_surrogate_job.sh
# ---------------------------------------------------------------------------

# Stop at the first failing command (including inside a pipeline) and on any
# unset variable, so a failed run exits nonzero and shows as FAILED in sacct
# instead of COMPLETED.
set -euo pipefail

# See opt_hydro_df_electric_job.sh for why $SLURM_SUBMIT_DIR (not git or
# $0/dirname) is the reliable way to resolve REPO_ROOT under a real sbatch
# job.
REPO_ROOT="$(cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")}/../.." && pwd)"
APP_DIR="$REPO_ROOT/applications/opt_hydro_df_electric_surrogate"
PARAMS_FILE="$APP_DIR/params.yaml"

if [ $# -gt 0 ]; then
  echo "This job takes no arguments -- edit $PARAMS_FILE directly before submitting." >&2
  exit 1
fi

echo "=========================================="
echo "Job started on: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-}"
echo "Running on node: ${SLURMD_NODENAME:-}"
echo "Using params from: $PARAMS_FILE"
echo "Working directory: $PWD"
echo "Outputs -> $APP_DIR/outputs"
echo "=========================================="
echo "System information:"
echo "Hostname: $(hostname)"
echo "Operating System: $(uname -a)"
echo "CPU info: $(lscpu | grep 'Model name' | head -1)"
echo "Memory info: $(free -h | grep 'Mem:')"
echo ""

# See opt_hydro_df_electric_job.sh for why this matters under SLURM's
# --output redirection (block-buffered stdout otherwise looks stalled).
export PYTHONUNBUFFERED=1

cd "$REPO_ROOT"
uv run --project "$REPO_ROOT" dvc repro applications/opt_hydro_df_electric_surrogate/dvc.yaml

echo ""
echo "=========================================="
echo "Job completed on: $(date)"
echo "Total runtime: $SECONDS seconds"
echo "=========================================="
