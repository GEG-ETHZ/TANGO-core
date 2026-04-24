#!/bin/bash
#SBATCH --job-name=run_flexible_DF_manual_sweep
#SBATCH --time=48:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
# #SBATCH --cpus-per-task=64
# #SBATCH --cpus-per-task=19
#SBATCH --mem-per-cpu=1G
#SBATCH --output=run_flexible_DF_manual_sweep_%j.out
#SBATCH --error=run_flexible_DF_manual_sweep_%j.err

# ---------------------------------------------------------------------------
# Runs the DVC pipeline for the flexible_DF_manual parameter sweep.
# n_workers is computed from the SLURM CPU allocation; n_samples can be
# overridden via env var or CLI flag. Both are written into params.yaml
# before calling dvc repro so DVC tracks them correctly.
#
# Examples:
#   SWEEP_N_SAMPLES=500 sbatch run_flexible_DF_manual_sweep_job.sh
#   sbatch --cpus-per-task=16 run_flexible_DF_manual_sweep_job.sh --n-samples 200
# ---------------------------------------------------------------------------

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
PARAMS_FILE="$(dirname "$0")/params.yaml"

# --- Defaults ---
CPUS="${SLURM_CPUS_PER_TASK:-48}"
N_SAMPLES="${SWEEP_N_SAMPLES:-10000}"

# --- CLI argument parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --n-samples)  N_SAMPLES="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--n-samples <N>]"
      echo "  --n-samples  Number of samples (env: SWEEP_N_SAMPLES, default: 10000)"
      echo "  CPUs are always taken from SLURM_CPUS_PER_TASK (#SBATCH --cpus-per-task)"
      exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

N_WORKERS=$(( CPUS - 3 ))

# --- Write params.yaml so DVC picks up the right values ---
# n_workers is not tracked by DVC for staleness (runtime-only), but the
# script reads it from params.yaml, so we still update it here.
uv run --project "$REPO_ROOT" python - <<EOF
import yaml, pathlib
p = pathlib.Path("$PARAMS_FILE")
params = yaml.safe_load(p.read_text())
params["n_samples"] = $N_SAMPLES
params["n_workers"] = $N_WORKERS
p.write_text(yaml.dump(params, default_flow_style=False, sort_keys=False))
EOF

echo "=========================================="
echo "Job started on: $(date)"
echo "Job ID: $SLURM_JOB_ID"
echo "Running on node: $SLURMD_NODENAME"
echo "CPUs: $CPUS  |  workers: $N_WORKERS  |  n-samples: $N_SAMPLES"
echo "Working directory: $PWD"
echo "=========================================="
echo "System information:"
echo "Hostname: $(hostname)"
echo "Operating System: $(uname -a)"
echo "CPU info: $(lscpu | grep 'Model name' | head -1)"
echo "Memory info: $(free -h | grep 'Mem:')"
echo ""

cd "$REPO_ROOT"
uv run dvc repro applications/run_flexible_DF_manual_sweep/dvc.yaml

echo ""
echo "=========================================="
echo "Job completed on: $(date)"
echo "Total runtime: $SECONDS seconds"
echo "=========================================="
