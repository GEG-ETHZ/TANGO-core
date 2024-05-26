#!/bin/bash
#SBATCH --job-name=my_python_job
#SBATCH --output=output.log
#SBATCH --error=error.log
#SBATCH --partition=your_partition
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --time=1:00:00

# Load any necessary modules (if needed)
# module load python/3.9.5

# Activate your virtual environment (if needed)
source .virtualenvs/WorkflowOrchestrator/bin/activate

#script_path = "$1"
#input_file_path = "$1"

# Run your Python script
python /cluster/home/tonishi/software/remote/TANGO/src/cli.py -f "$1" #TODO: generalize