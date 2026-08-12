#!/bin/bash
#SBATCH --job-name=tango_next_opt_hydro_df_electric
#SBATCH --time=24:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem-per-cpu=1G
#SBATCH --output=opt_hydro_df_electric_%j.out
#SBATCH --error=opt_hydro_df_electric_%j.err

# ---------------------------------------------------------------------------
# Runs the tango_next hydro_df_electric pymoo optimization (mass flow rate +
# injection pressure -> minimize LCOE, maximize mean net power) on Euler.
#
# -p/--n-processes is derived from the SLURM CPU allocation (a few cores
# reserved for the main driver process/OS overhead), NOT hardcoded --
# opt_hydro_df_electric.py itself defaults to -p 1 (serial) if nothing
# overrides it, so this wrapper's whole job is turning "however many CPUs
# SLURM gave this job" into the right -p value.
#
# Outputs default to /cluster/scratch/$USER/opt_hydro_df_electric/outputs
# (scratch: fast, high-quota, and keeps job output out of the actual repo
# checkout) rather than opt_hydro_df_electric.py's own default (relative
# to its own location, meant for local/interactive use).
#
# Any extra arguments are forwarded directly to opt_hydro_df_electric.py,
# appended AFTER this script's own defaults below -- argparse keeps the
# LAST occurrence of a repeated flag, so passing e.g. -p or --save-dir
# yourself here still overrides the computed defaults.
#
# Examples:
#   sbatch opt_hydro_df_electric_job.sh
#   sbatch opt_hydro_df_electric_job.sh --n-max-gen 100 --pop-size 80
#   sbatch --cpus-per-task=16 opt_hydro_df_electric_job.sh -p 12 --clean
# ---------------------------------------------------------------------------

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
REPO_ROOT="$(cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")}/../../.." && pwd)"

CPUS="${SLURM_CPUS_PER_TASK:-48}"
N_WORKERS=$(( CPUS - 3 ))
if [ "$N_WORKERS" -lt 1 ]; then
  N_WORKERS=1
fi

echo "=========================================="
echo "Job started on: $(date)"
echo "Job ID: $SLURM_JOB_ID"
echo "Running on node: $SLURMD_NODENAME"
echo "CPUs: $CPUS  |  workers (-p): $N_WORKERS"
echo "Working directory: $PWD"
echo "=========================================="
echo "System information:"
echo "Hostname: $(hostname)"
echo "Operating System: $(uname -a)"
echo "CPU info: $(lscpu | grep 'Model name' | head -1)"
echo "Memory info: $(free -h | grep 'Mem:')"
echo ""

SCRATCH_OUTPUT_DIR="/cluster/scratch/$USER/opt_hydro_df_electric/outputs"

cd "$REPO_ROOT"
uv run --project "$REPO_ROOT" python applications/tango_next/opt_hydro_df_electric/opt_hydro_df_electric.py \
  -p "$N_WORKERS" \
  --verbose \
  --save-dir "$SCRATCH_OUTPUT_DIR" \
  "$@"

echo ""
echo "=========================================="
echo "Job completed on: $(date)"
echo "Total runtime: $SECONDS seconds"
echo "=========================================="
