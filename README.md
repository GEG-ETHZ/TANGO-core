# Techno-economic ANalysis of Geoenergy Operations (TANGO)
![Tango Logo](./tango-logo.svg)

## Prerequisites

Before using or developing TANGO, you need to have Python and `uv` installed.

1.  **Install Python**: You need Python >= 3.11 installed on your system.
    -   **macOS**: `brew install python@3.11` (or latest available)
    -   **Linux (Ubuntu/Debian)**: `sudo apt update && sudo apt install python3 python3-pip python3-venv`
    -   **Windows**: Download the official installer from [python.org](https://www.python.org/downloads/windows/) or install via the Microsoft Store.
2.  **Install `uv`**: Follow the [official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).
    -   For macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
    -   For Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

## General users

### Installation

1.  Clone the repository or download the source code.
2.  Run `uv sync` to install dependencies.

### Examples

You can run anything in the `./examples/` folder with, e.g. `uv run tango_cli -f examples/flexible_SF_manual.yml`.

## Project Structure

```text
└── tango-core
    ├── README.md
    ├── pyproject.toml
    ├── .gitignore
    ├── .python-version
    ├── examples/    # Example TANGO configurations and scripts
    ├── scripts/     # Utility scripts
    ├── src/         # Installable Python package source code
    │   └── tango
    │       └── ...
    ├── tests/       # Unit and regression tests
    └── uv.lock
```

**Tip:** To regenerate this tree, run:
`tree -I '__pycache__|.venv|*.egg-info|.git'`

## Developers and Internal Users

Note that these instructions have been verified to work on Euler.

### Installation

1.  [install uv](https://docs.astral.sh/uv/getting-started/installation/)
2.  run `uv sync` to install dependencies (including developer dependencies).

### direnv (optional but recommended)

[direnv](https://direnv.net) automatically activates the project's venv and keeps dependencies in sync whenever you `cd` into the repo — no manual `source .venv/bin/activate` needed.

1. [Install direnv](https://direnv.net/docs/installation.html) and hook it into your shell.
2. Run `direnv allow .` once in the repo root to approve the `.envrc` file.

After that, entering the directory runs `uv sync` and activates the venv automatically.

### Running Checks
-   **Tests:** `uv run pytest -v` -- to be run from the root directory
-   **Linting:** `uv run ruff check .`
-   **Formatting:** `uv run ruff format .` (use `--check` to verify without modifying)
-   **Type checking:** `uv run mypy src/`

### Branching Strategy
Explained in [CONTRIBUTING.md](./CONTRIBUTING.md#branching-strategy).

### Running on Euler
Note that these instructions have been verified to work on Euler.

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
