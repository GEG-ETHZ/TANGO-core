# Techno-economic ANalysis of Geoenergy Operations (TANGO)
![Tango Logo](./tango-logo.svg)

## General users

### Installation

If you have not previously done so, install `uv`: https://docs.astral.sh/uv/getting-started/installation/.

### Examples

You can run anything in the `./examples/` folder with, e.g. `uv run tango_cli -f examples/flexible_SF_manual.yml`. A future update will also provide run scripts.

## Developers and Internal Users

Note that these instructions have been verified to work on Euler.

### Installation

If you have not previously done so, install `uv`: https://docs.astral.sh/uv/getting-started/installation/.

### Testing

Run `uv run pytest -v` in the root directory
(i.e. the same directory as this file) to verify everything works. This will
automatically create an environment, install all the dependencies, and run
`pytest` within the environment with developer dependencies installed.

### Branching Strategy
See [CONTRIBUTING](./CONTRIBUTING.md)

### Running on Euler
1. [Setup ssh to connect to gitlab](https://gitlab.ethz.ch/geg/computing-guide/-/wikis/git#setting-up-ssh-for-git)
1. [Setup ssh to connect to Euler](https://gitlab.ethz.ch/geg/computing-guide/-/wikis/HPC#setting-up-passwordless-ssh-access-to-euler-from-your-laptop)
1. Get TANGO onto Euler:
    - Option 1: Clone `tango-core` locally and then use rsync to move it to Euler (Mac or linux only)
        1. Starting on your own laptop, run `ls ~/git/projects/` to check if this directory exists
        1. if `ls ~/git/projects/` exists, run `cd ~/git/projects/`, and if not, first run `mkdir -p ~/git/projects/` and then `cd ~/git/projects/`
        1. Clone this repo: `git clone git@gitlab.ethz.ch:geg/tango-projects/tango-core.git`
        1. run `rsync -ahPuv --exclude .pixi --exclude .mypy_cache --exclude .venv ~/git/projects/tango-core/ euler:~/tango-core/`
        1. Log into euler: `ssh euler`
    - Option 2: (CURRENLY NOT FULLY WORKING so let's do the rsync approach) Setup git on Euler (this option is a bit more setup but a bit easier long term)
        1. While logged into Euler, [Setup ssh to connect to gitlab](https://gitlab.ethz.ch/geg/computing-guide/-/wikis/git#setting-up-ssh-for-git)
        1. Clone this repo: `git clone git@gitlab.ethz.ch:geg/tango-projects/tango-core.git`
1. You should already be logged into Euler at this point, and run `cd ~/tango-core/`
1. Run `git checkout develop`
1. Run `curl -LsSf https://astral.sh/uv/install.sh | sh` to
    [install `uv`](https://docs.astral.sh/uv/getting-started/installation/) for your Euler
    user account
1. Run `rsync -ahPv ~/tango-core/applications/ /cluster/scratch/<username>/tango-applications/` to get the demo files into your working directory
1. Run `cd /cluster/scratch/<username>/tango-applications/run_flexible_DF_manual_sweep`
1. Run `sbatch --cpus-per-task=16 run_flexible_DF_manual_sweep_job.sh --n-samples 39` to kick off a slurm job with 16 CPUs, 13 workers, and 39 design evaluations
    Note: by using fewer than 48 CPUs, we're able to avoid having this count against our Euler quota
1. Run `myjobs` to check status
1. When the job is finished, run `uv run --project ~/tango-core run_flexible_DF_manual_analysis.py`
