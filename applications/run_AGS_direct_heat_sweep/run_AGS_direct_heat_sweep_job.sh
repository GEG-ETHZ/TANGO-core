#!/bin/bash
#SBATCH --job-name=tango_run_AGS_direct_heat_sweep
#SBATCH --time=48:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem-per-cpu=1G
#SBATCH --output=run_AGS_direct_heat_sweep_%j.out
#SBATCH --error=run_AGS_direct_heat_sweep_%j.err

# ---------------------------------------------------------------------------
# Runs the DVC pipeline for the tango Triemli AGS direct-heat sweep.
# n_workers comes from params.yaml, which this job never rewrites, so Euler's
# checkout stays clean for `git pull`; keep it a few below --cpus-per-task. Unlike the
# DF manual sweep, the design grid itself (well depth / mass flow / loop
# length / loop diameter) is fixed in common.py, not a params.yaml value —
# there is no n_samples to override here.
#
# Example:
#   sbatch run_AGS_direct_heat_sweep_job.sh
# ---------------------------------------------------------------------------

# Stop at the first failing command (including inside a pipeline) and on any
# unset variable, so a failed run exits nonzero and shows as FAILED in sacct
# instead of COMPLETED.
set -euo pipefail

# NOT git-based (`git -C ... rev-parse --show-toplevel`) -- that assumes a
# git checkout, which isn't confirmed for every Euler checkout of this repo
# (the documented workflow (README.md's "Running on Euler") is rsync-based
# and doesn't necessarily bring `.git` along), and it fails under a real
# sbatch job regardless: `sbatch` COPIES the submitted script into a spool
# directory and executes THAT copy, so `$0`/its dirname point at the spool
# copy, not this script's real location -- confirmed the hard way on a real
# Euler submission ("fatal: not a git repository" + the resulting empty
# REPO_ROOT breaking everything downstream). $SLURM_SUBMIT_DIR is the
# reliable one -- SLURM sets it to the directory `sbatch` was invoked FROM,
# which is always this script's own directory in the documented workflow.
# Falls back to `dirname "$0"` only for local testing outside SLURM, where
# $SLURM_SUBMIT_DIR is unset.
REPO_ROOT="$(cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")}/../.." && pwd)"
APP_DIR="$REPO_ROOT/applications/run_AGS_direct_heat_sweep"
PARAMS_FILE="$APP_DIR/params.yaml"

echo "=========================================="
echo "Job started on: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-}"
echo "Running on node: ${SLURMD_NODENAME:-}"
echo "Using params from: $PARAMS_FILE"
echo "Working directory: $PWD"
echo "=========================================="
echo "System information:"
echo "Hostname: $(hostname)"
echo "Operating System: $(uname -a)"
echo "CPU info: $(lscpu | grep 'Model name' | head -1)"
echo "Memory info: $(free -h | grep 'Mem:')"
echo ""

cd "$REPO_ROOT"
# --wait-for-lock: every job runs `dvc repro` in this one checkout, and DVC
# takes a repo-wide lock while it sets up and records each stage (not while
# the stage's command runs). Without it, jobs that start together give up
# after ~3 s and fail.
uv run dvc --wait-for-lock repro applications/run_AGS_direct_heat_sweep/dvc.yaml

echo ""
echo "=========================================="
echo "Job completed on: $(date)"
echo "Total runtime: $SECONDS seconds"
echo "=========================================="
