# Running on Euler

This guide runs a TANGO sweep as a SLURM job on ETH's Euler cluster. The example is the hydrothermal double-flash sweep in `applications/run_hydro_df_electric_sweep/`; the other applications follow the same pattern with their own `*_job.sh` scripts.

## Prerequisites

1. [SSH access to GitHub](https://docs.github.com/en/authentication/connecting-to-github-with-ssh) from your laptop, with access to `GEG-ETHZ/TANGO-core`.
2. [Passwordless SSH access to Euler](https://gitlab.ethz.ch/geg/computing-guide/-/wikis/HPC#setting-up-passwordless-ssh-access-to-euler-from-your-laptop), with the host alias `euler`.
3. macOS or Linux on your laptop, for `rsync`.

## 1. Copy TANGO to Euler

The supported path clones on your laptop and copies the checkout to Euler with `rsync`:

```bash
mkdir -p ~/git/projects && cd ~/git/projects
git clone git@github.com:GEG-ETHZ/TANGO-core.git tango-core
rsync -ahPuv --exclude .pixi --exclude .mypy_cache --exclude .venv \
  ~/git/projects/tango-core/ euler:~/tango-core/
```

Cloning directly on Euler needs GitHub SSH access set up on Euler as well and is not covered here.

## 2. Install the tools on Euler

Log in with `ssh euler`, then install `uv` and `just` for your user account (no `sudo` needed):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin
```

Make sure `~/.local/bin` is on your `PATH`. If it is not, add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` and log in again.

## 3. Submit the job

```bash
rsync -ahPv ~/tango-core/applications/ /cluster/scratch/$USER/tango-applications/
cd /cluster/scratch/$USER/tango-applications/run_hydro_df_electric_sweep
sbatch --cpus-per-task=16 run_hydro_df_electric_sweep_job.sh
```

The job script sets the number of parallel workers from the CPU allocation (CPUs minus 3), writes it to `params.yaml` and runs the DVC pipeline. Requesting fewer than 48 CPUs keeps the job from counting against the group's Euler quota.

## 4. Monitor and analyze

```bash
myjobs                                                   # job status
uv run --project ~/tango-core run_hydro_df_electric_analysis.py   # once the job has finished
```

SLURM writes the job's output to `run_hydro_df_electric_sweep_<jobid>.out` and `.err` in the submit directory.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `uv: command not found` in the job log | `~/.local/bin` is not on `PATH` in non-interactive shells. Add the `export` line to `~/.bashrc`. |
| `fatal: not a git repository` | The job script must be submitted from its own application directory; it locates the repository from `$SLURM_SUBMIT_DIR`, not from git. |
| The job is queued for a long time | Request fewer CPUs, or check the Euler status page. |
