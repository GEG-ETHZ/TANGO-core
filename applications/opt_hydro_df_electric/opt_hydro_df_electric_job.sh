#!/bin/bash
#SBATCH --job-name=tango_opt_hydro_df_electric
#SBATCH --time=24:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem-per-cpu=500M
#SBATCH --output=opt_hydro_df_electric_%j.out
#SBATCH --error=opt_hydro_df_electric_%j.err

# ---------------------------------------------------------------------------
# Runs the tango opt_hydro_df_electric pymoo optimization via `dvc repro`
# (see opt_hydro_df_electric.py's docstring for its decision variables and
# objectives). Like the sibling run_*_sweep_job.sh scripts, this job does
# NOT write anything into params.yaml and does NOT accept CLI overrides --
# params.yaml is the
# single source of truth for every hyperparameter (n_max_gen, pop_size,
# ftol, xtol, seed, n_processes, crossover_prob, mutation_prob). Edit
# params.yaml directly before submitting; `dvc repro` picks up whatever's
# committed there. This avoids the job silently rewriting params.yaml on
# every submission (which made it impossible to tell, after the fact, what
# values a given run actually used without checking job logs).
#
# n_processes is therefore NOT auto-derived from --cpus-per-task anymore --
# keep params.yaml's n_processes in sync with whatever --cpus-per-task you
# submit with (leave a few cores headroom for the main driver process/OS).
#
# Output lands in this app's own outputs/ inside the repo checkout
# (gitignored, never committed) -- NOT scratch: DVC's `outs:` hard-requires
# the resolved real path to sit inside the git repo tree (confirmed
# empirically -- pointing outputs/ at a symlink into /cluster/scratch/...
# makes `dvc repro` fail with "is outside of git repository"), and this
# app's real output volume is small (~30 tiny per-design YAMLs, one CSV, a
# few plots, ~5MB total), so there's no actual need for scratch's
# speed/quota headroom here.
#
# Example:
#   sbatch opt_hydro_df_electric_job.sh
# ---------------------------------------------------------------------------

# Stop at the first failing command (including inside a pipeline) and on any
# unset variable, so a failed run exits nonzero and shows as FAILED in sacct
# instead of COMPLETED.
set -euo pipefail

# NOT git-based (unlike the sibling sweep job scripts' `git -C ... rev-parse
# --show-toplevel`) -- that assumes a git clone, but the documented Euler
# workflow (README.md's "Running on Euler") is rsync-based and doesn't
# necessarily bring `.git` along, which made REPO_ROOT resolve to an empty
# string and `uv run --project ""` fail with a useless error.
#
# Also NOT `dirname "$0"`-based, despite this script's own location
# relative to the repo root being fixed: `sbatch` COPIES the submitted
# script into a spool directory (e.g. /var/spool/slurm/...) and executes
# THAT copy, so `$0` inside a real sbatch job does not point at this
# script's actual location at all (confirmed the hard way: worked when
# tested by running the script directly, broke under a real `sbatch`
# submission with "can't open file '/var/spool/slurm/applications/...'").
# $SLURM_SUBMIT_DIR is the reliable one -- SLURM sets it to the directory
# `sbatch` was invoked FROM, which the documented workflow always is
# (this script's own directory). Falls back to `dirname "$0"` only for
# local testing outside SLURM, where $SLURM_SUBMIT_DIR is unset.
REPO_ROOT="$(cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")}/../.." && pwd)"
APP_DIR="$REPO_ROOT/applications/opt_hydro_df_electric"
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

# Without this, Python fully block-buffers stdout when it isn't a TTY
# (exactly what SLURM's --output redirection is) -- pymoo's own
# per-generation progress table (and every plain print()) sits in an
# unflushed buffer and doesn't show up in the .out file until it fills or
# the process exits, making a long-running job look stalled even though
# outputs/pareto_results_partial.csv proves it's progressing fine.
export PYTHONUNBUFFERED=1

cd "$REPO_ROOT"
uv run --project "$REPO_ROOT" dvc repro applications/opt_hydro_df_electric/dvc.yaml

echo ""
echo "=========================================="
echo "Job completed on: $(date)"
echo "Total runtime: $SECONDS seconds"
echo "=========================================="
