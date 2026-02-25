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
# Configurable parameters — three-tier override (lowest → highest priority):
#   1. Hardcoded defaults below
#   2. Environment variables:  SWEEP_CPUS, SWEEP_N_SAMPLES
#   3. CLI flags:              --cpus <N>  --n-samples <N>
#
# Examples:
#   # Use env vars (useful in SLURM job arrays or CI):
#   SWEEP_N_SAMPLES=500 sbatch run_flexible_DF_manual_sweep_job.sh
#
#   # Use CLI flags (highest priority, overrides env vars):
#   bash run_flexible_DF_manual_sweep_job.sh --cpus 16 --n-samples 200
# ---------------------------------------------------------------------------

# --- Defaults (override via env vars or CLI flags) ---
CPUS="${SWEEP_CPUS:-${SLURM_CPUS_PER_TASK:-48}}"
N_SAMPLES="${SWEEP_N_SAMPLES:-10000}"

# --- CLI argument parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --cpus)       CPUS="$2";      shift 2 ;;
    --n-samples)  N_SAMPLES="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--cpus <N>] [--n-samples <N>]"
      echo ""
      echo "  --cpus      Number of CPUs / workers+3  (env: SWEEP_CPUS,      default: 48)"
      echo "  --n-samples Number of LHS samples       (env: SWEEP_N_SAMPLES, default: 10000)"
      exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

N_WORKERS=$(( CPUS - 3 ))

# Print job information
echo "=========================================="
echo "Job started on: $(date)"
echo "Job ID: $SLURM_JOB_ID"
echo "Running on node: $SLURMD_NODENAME"
echo "CPUs: $CPUS  |  workers: $N_WORKERS  |  n-samples: $N_SAMPLES"
echo "Working directory: $PWD"
echo "=========================================="

# Print system information
echo "System information:"
echo "Hostname: $(hostname)"
echo "Operating System: $(uname -a)"
echo "CPU info: $(lscpu | grep 'Model name' | head -1)"
echo "Memory info: $(free -h | grep 'Mem:')"
echo ""

# LHS Parameter Sweep for TANGO simulations
# Parameter bounds are defined per-parameter in PARAMETER_BOUNDS dict.

# options:
#   -h, --help            show this help message and exit
#   --n-samples N_SAMPLES
#                         Number of LHS samples to generate (default: 100)
#   --n-workers N_WORKERS
#                         Number of parallel workers (default: 8)
#   --seed SEED           Random seed for reproducibility (default: 42)
#   --regenerate          Regenerate design matrix even if it exists (default: False)
#   --log-level {DEBUG,INFO,WARNING,ERROR,NONE}
#                         Log level for TANGO simulations (default: NONE)
#   --quiet, -q           Suppress progress output (default: False)
#   --progress-interval PROGRESS_INTERVAL
#                         Print progress every N completions (default: n_workers)
#   --sweep-dir SWEEP_DIR
#                         Directory for sweep outputs (default: ../examples/run_flexible_DF_manual_sweep)

# Quick test run (small sample size matching workers)
# uv run ../../examples/run_flexible_DF_manual_sweep.py --regenerate --progress-interval 8 \
#   --sweep-dir ./ --n-workers $N_WORKERS --n-samples $N_WORKERS

# Production run
uv run --project ~/tango-core/ ../../examples/run_flexible_DF_manual_sweep.py --regenerate --progress-interval "$N_WORKERS" \
  --sweep-dir ./ --n-workers "$N_WORKERS" --n-samples "$N_SAMPLES"

echo ""
echo "=========================================="
echo "Job completed on: $(date)"
echo "Total runtime: $SECONDS seconds"
echo "=========================================="
