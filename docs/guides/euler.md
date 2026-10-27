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

## 3. Submit the jobs

From anywhere in `~/tango-core`, name the applications to run:

```bash
just slurm opt_AGS_ORC_electric run_hydro_df_electric_sweep
```

With no names, `just slurm` submits every application under `applications/` that has a `*_job.sh`. The jobs run one after another, each on a whole 48-core allocation. Each job runs its application's `dvc repro` inside the checkout, so its results land in that application's own `outputs/`. Hyperparameters such as population size and worker count come from each application's `params.yaml`; edit and commit that file rather than passing arguments to the job. `just slurm --help` lists the options.

## 4. Monitor and fetch the results

Run `myjobs` on Euler to check status. Each job writes `<app>_<jobid>.out` and `.err` in its application directory, and a failed job shows as FAILED in `sacct`.

When the jobs finish, copy the results back from your laptop, inside your local checkout:

```bash
just slurm-fetch opt_AGS_ORC_electric run_hydro_df_electric_sweep
```

This copies each application's `outputs/`, job logs and `dvc.lock`, plus Euler's DVC cache. Run `dvc push` afterwards so the results are kept; `just slurm-fetch --help` lists the options.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `uv: command not found` in the job log | `~/.local/bin` is not on `PATH` in non-interactive shells. Add the `export` line to `~/.bashrc`. |
| `fatal: not a git repository` | The job script must be submitted from its own application directory; it locates the repository from `$SLURM_SUBMIT_DIR`, not from git. `just slurm` does this for you. |
| The job is queued for a long time | Request fewer CPUs, or check the Euler status page. |
