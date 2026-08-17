#!/bin/bash
#SBATCH --job-name=tango_next_run_hydro_df_electric_sweep
#SBATCH --time=48:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem-per-cpu=1G
#SBATCH --output=run_hydro_df_electric_sweep_%j.out
#SBATCH --error=run_hydro_df_electric_sweep_%j.err

# ---------------------------------------------------------------------------
# Runs the DVC pipeline for the tango_next double-flash sensitivity sweep.
# The design is now a fixed one-at-a-time (OFAT) low/high sweep (see
# generate.py's module docstring) — not a tunable sample count, so there's
# no --n-samples here anymore. n_workers is computed from the SLURM CPU
# allocation and written into params.yaml before calling dvc repro so DVC
# tracks it correctly.
#
# Example:
#   sbatch --cpus-per-task=16 run_hydro_df_electric_sweep_job.sh
# ---------------------------------------------------------------------------

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
PARAMS_FILE="$(dirname "$0")/params.yaml"

CPUS="${SLURM_CPUS_PER_TASK:-48}"
N_WORKERS=$(( CPUS - 3 ))

# --- Write params.yaml so DVC picks up the right value ---
uv run --project "$REPO_ROOT" python - <<EOF
import yaml, pathlib
p = pathlib.Path("$PARAMS_FILE")
params = yaml.safe_load(p.read_text())
params["n_workers"] = $N_WORKERS
p.write_text(yaml.dump(params, default_flow_style=False, sort_keys=False))
EOF

echo "=========================================="
echo "Job started on: $(date)"
echo "Job ID: $SLURM_JOB_ID"
echo "Running on node: $SLURMD_NODENAME"
echo "CPUs: $CPUS  |  workers: $N_WORKERS"
echo "Working directory: $PWD"
echo "=========================================="
echo "System information:"
echo "Hostname: $(hostname)"
echo "Operating System: $(uname -a)"
echo "CPU info: $(lscpu | grep 'Model name' | head -1)"
echo "Memory info: $(free -h | grep 'Mem:')"
echo ""

cd "$REPO_ROOT"
uv run dvc repro applications/tango_next/run_hydro_df_electric_sweep/dvc.yaml

echo ""
echo "=========================================="
echo "Job completed on: $(date)"
echo "Total runtime: $SECONDS seconds"
echo "=========================================="
