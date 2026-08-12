#!/bin/bash
#SBATCH --job-name=tango_next_opt_hydro_df_electric
#SBATCH --time=24:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem-per-cpu=500M
#SBATCH --output=opt_hydro_df_electric_%j.out
#SBATCH --error=opt_hydro_df_electric_%j.err

# ---------------------------------------------------------------------------
# Runs the tango_next hydro_df_electric pymoo optimization (mass flow rate +
# injection pressure + target extraction pressure -> minimize LCOE, maximize
# mean net power) via `dvc repro`, matching the sibling run_*_sweep_job.sh
# scripts' convention exactly: write SLURM-derived/CLI-overridden values into
# params.yaml, then let DVC decide what's stale and run it. Output lands in
# this app's own outputs/ inside the repo checkout (gitignored, never
# committed) -- NOT scratch: DVC's `outs:` hard-requires the resolved real
# path to sit inside the git repo tree (confirmed empirically -- pointing
# outputs/ at a symlink into /cluster/scratch/... makes `dvc repro` fail
# with "is outside of git repository"), and this app's real output volume
# is small (~30 tiny per-design YAMLs, one CSV, a few plots, ~5MB total),
# so there's no actual need for scratch's speed/quota headroom here.
#
# n_processes is derived from the SLURM CPU allocation (a few cores reserved
# for the main driver process/OS overhead), NOT hardcoded. Only --n-max-gen
# and --pop-size are exposed here (mirroring run_hydro_df_electric_sweep_job.sh's
# --n-samples-only surface) -- for ftol/xtol/seed, edit params.yaml directly;
# dvc repro picks up any params.yaml change regardless of how it got there.
#
# Examples:
#   sbatch opt_hydro_df_electric_job.sh
#   sbatch opt_hydro_df_electric_job.sh --n-max-gen 100 --pop-size 80
#   sbatch --cpus-per-task=16 opt_hydro_df_electric_job.sh --pop-size 60
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
APP_DIR="$REPO_ROOT/applications/tango_next/opt_hydro_df_electric"
PARAMS_FILE="$APP_DIR/params.yaml"

# --- Defaults ---
CPUS="${SLURM_CPUS_PER_TASK:-48}"
N_MAX_GEN="${OPT_N_MAX_GEN:-200}"
POP_SIZE="${OPT_POP_SIZE:-40}"

# --- CLI argument parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --n-max-gen)  N_MAX_GEN="$2"; shift 2 ;;
    --pop-size)   POP_SIZE="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--n-max-gen <N>] [--pop-size <N>]"
      echo "  --n-max-gen  Max generations (env: OPT_N_MAX_GEN, default: 200)"
      echo "  --pop-size   Population size (env: OPT_POP_SIZE, default: 40)"
      echo "  n_processes is always derived from SLURM_CPUS_PER_TASK (#SBATCH --cpus-per-task)"
      echo "  For ftol/xtol/seed, edit params.yaml directly before submitting."
      exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

N_WORKERS=$(( CPUS - 3 ))
if [ "$N_WORKERS" -lt 1 ]; then
  N_WORKERS=1
fi

# --- Write params.yaml so DVC picks up the right values ---
uv run --project "$REPO_ROOT" python - <<EOF
import yaml, pathlib
p = pathlib.Path("$PARAMS_FILE")
params = yaml.safe_load(p.read_text())
params["n_max_gen"] = $N_MAX_GEN
params["pop_size"] = $POP_SIZE
params["n_processes"] = $N_WORKERS
p.write_text(yaml.dump(params, default_flow_style=False, sort_keys=False))
EOF

echo "=========================================="
echo "Job started on: $(date)"
echo "Job ID: $SLURM_JOB_ID"
echo "Running on node: $SLURMD_NODENAME"
echo "CPUs: $CPUS  |  n_processes: $N_WORKERS  |  n-max-gen: $N_MAX_GEN  |  pop-size: $POP_SIZE"
echo "Working directory: $PWD"
echo "Outputs -> $APP_DIR/outputs"
echo "=========================================="
echo "System information:"
echo "Hostname: $(hostname)"
echo "Operating System: $(uname -a)"
echo "CPU info: $(lscpu | grep 'Model name' | head -1)"
echo "Memory info: $(free -h | grep 'Mem:')"
echo ""

cd "$REPO_ROOT"
uv run --project "$REPO_ROOT" dvc repro applications/tango_next/opt_hydro_df_electric/dvc.yaml

echo ""
echo "=========================================="
echo "Job completed on: $(date)"
echo "Total runtime: $SECONDS seconds"
echo "=========================================="
