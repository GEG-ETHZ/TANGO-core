#!/bin/bash
#SBATCH --job-name=run_flexible_DF_manual_sweep
#SBATCH --time=04:00:00
#SBATCH --ntasks=1
# #SBATCH --cpus-per-task=48
#SBATCH --cpus-per-task=19
#SBATCH --mem-per-cpu=1G
#SBATCH --output=run_flexible_DF_manual_sweep_%j.out
#SBATCH --error=run_flexible_DF_manual_sweep_%j.err

# Print job information
echo "=========================================="
echo "Job started on: $(date)"
echo "Job ID: $SLURM_JOB_ID"
echo "Running on node: $SLURMD_NODENAME"
echo "Number of CPUs: $SLURM_CPUS_PER_TASK"
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

# options:
#   -h, --help            show this help message and exit
#   --scale-min SCALE_MIN
#                         Minimum scale factor for parameters (default: 0.2)
#   --scale-max SCALE_MAX
#                         Maximum scale factor for parameters (default: 10.0)
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
#                         Print progress every N completions (default: n_workers) (default: None)
#   --sweep-dir SWEEP_DIR
#                         Directory for sweep outputs (default: ../examples/run_flexible_DF_manual_sweep) (default: None)

N_WORKERS=$((SLURM_CPUS_PER_TASK - 3))
# Run this first to verify behavior
pixi run python ../../examples/run_flexible_DF_manual_sweep.py --regenerate --progress-interval 8 --sweep-dir ./ --n-workers $N_WORKERS --n-samples $N_WORKERS

# pixi run python ../../examples/run_flexible_DF_manual_sweep.py --regenerate --progress-interval 10 --sweep-dir ./ --n-workers $N_WORKERS --n-samples 10000

echo ""
echo "=========================================="
echo "Job completed on: $(date)"
echo "Total runtime: $SECONDS seconds"
echo "=========================================="
