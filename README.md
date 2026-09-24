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

TANGO is a private GitLab repository, so you'll need GitLab git access set
up first (SSH or HTTPS; see the ["Setup ssh to connect to
gitlab"](https://gitlab.ethz.ch/geg/computing-guide/-/wikis/git#setting-up-ssh-for-git)
guide). Given that:

1.  **Scaffold a new project** with the GEG cookiecutter template
    (`gitlab.ethz.ch/geg/templates/python-template`):
    ```bash
    uvx --from cookiecutter cookiecutter git@gitlab.ethz.ch:geg/templates/python-template.git
    ```
    Follow its prompts (project name, author, etc.) — see that template's own
    README for details.
2.  **Add `tango-core` from GitLab, pinned to a release tag**, from inside the
    new project:
    ```bash
    uv add "tango-core@git+ssh://git@gitlab.ethz.ch/geg/tango-projects/tango-core.git" --tag v1.0.1
    ```
    (there's no standalone `--git` flag — the git source is part of the
    package spec itself, as shown; `--tag` alongside it still works to pin
    the ref.)

    Swap `v1.0.1` for whichever tag you want to pin to (see
    [`CONTRIBUTING.md`'s release section](./CONTRIBUTING.md#cutting-an-internal-geg-only-release)
    for how those are cut); `uv add` records the exact tag (and resolved
    commit) in `pyproject.toml`/`uv.lock`, so builds stay reproducible until
    you deliberately bump it. The distribution is named `tango-core`
    (matching the repo), but the importable module is still `tango` —
    `import tango` / `from tango.workflows.workflow import Workflow` etc.
    work unchanged.
3.  To move to a newer release later, re-run the same command with a new
    `--tag` value (or `uv lock --upgrade-package tango-core` if already
    pinned to a branch rather than a tag).

Because this is an internal-only distribution (see [`NOTICE`](./NOTICE) and
[`LICENSE.txt`](./LICENSE.txt)), only GEG group members with GitLab access
to `tango-projects/tango-core` can complete step 2 — there is no public
fallback.

Once installed, get a starting set of example configs to build your own
inputs from:

```bash
uv run tango_cli init .
```

This copies the `example_configs/` bundled with the installed `tango`
version into your project directory. Pass `--app` (repeatable) to also
copy one of `applications/`'s sweep/optimization/demo pipelines, or
`--list-apps` to see which are available:

```console
$ uv run tango_cli init --help
usage: tango_cli init [-h] [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                      [--app APP] [--list-apps]
                      [DEST]

Copy tango's bundled example_configs/ into DEST (created if needed) as a
starting point for your own analysis. Fails if DEST/example_configs already
exists, to avoid silently overwriting local edits. Pass --app one or more
times to also copy one of applications/'s sweep/optimization/demo pipelines.

positional arguments:
  DEST                  Directory to copy example_configs/ into. Default:
                        current directory.

options:
  -h, --help            show this help message and exit
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Logging verbosity. Use DEBUG to see per-iteration
                        convergence output. Default: INFO.
  --app APP             Also copy DEST/applications/APP. Repeatable. See
                        --list-apps for the available names, or
                        applications/README.md in the repository for what each
                        one does.
  --list-apps           Print the available --app names and exit, without
                        copying anything.
```

### Examples

You can run anything in the `./example_configs/` folder with, e.g. `uv run tango_cli run example_configs/hydro_sf_electric.yml`.

Run `tango_cli --version` any time to see the exact `tango` version
installed, along with TANGO's confidentiality/distribution notice.

## Project Structure

```text
└── tango-core
    ├── README.md
    ├── pyproject.toml
    ├── .gitignore
    ├── .python-version
    ├── applications/     # Multi-run pipelines (sweeps, optimizations, demos) — scripts only
    ├── CHANGELOG.md
    ├── CONTRIBUTING.md
    ├── docs/             # Design docs, architecture notes, task tracker
    ├── example_configs/  # Actively-maintained configs backing tests/applications
    ├── justfile          # Task runner (see `just --list`)
    ├── LICENSE.txt
    ├── NOTICE
    ├── src/              # Installable Python package source code
    │   └── tango
    │       └── ...
    ├── tests/            # Unit and regression tests
    ├── tools/            # Repo maintenance scripts (git hooks, DVC helpers)
    └── uv.lock
```

**Tip:** To regenerate this tree, run:
`tree -I '__pycache__|.venv|*.egg-info|.git'`

## What's in `tests/`, `example_configs/`, and `applications/`

These directories serve different purposes and are easy to mix up:

- **`tests/`** — automated, CI-gated correctness checks, run via `uv run pytest`.
  `tests/unit/` covers individual components/utilities in isolation;
  `tests/regtest/` is regression/integration coverage that runs full
  simulations end-to-end, including a fixed historical LCOE reference value
  (`tests/regtest/test_lcoe_regression.py`). If you break something, one of
  these should catch it — that's the whole point of running them before every
  push (see [Running Checks](#running-checks) and the pre-push git hook).

- **[`example_configs/`](example_configs/README.md)** — the actively-maintained
  config set: every config here backs either a unit/regression test, an
  application in `applications/`, or both — treat it as the current source
  of truth for what a valid `tango` config looks like. Runnable directly via
  `uv run tango_cli run example_configs/<file>.yml`. See that directory's own
  README for what each config is.

- **[`applications/`](applications/README.md)** — multi-run parameter-sweep
  pipelines built on top of an `example_configs/` config, not single
  simulations. Each `run_*_sweep/`
  directory is a self-contained generate → sweep → summarize (→ plot)
  pipeline with its own `common.py` (grid/LHS bounds), `dvc.yaml` (DVC-cached
  stages — see below), `params.yaml` (tunable knobs DVC tracks for
  staleness), a `--clean` CLI flag (wipes generated outputs), and a SLURM
  `*_job.sh` script for running on Euler/HPC. Every app also supports
  `--smoke` for a fast end-to-end pipeline check (tiny sample count, writes
  to a throwaway tempdir, never touches `outputs/`) — use that before
  trusting a fresh clone or a code change, without waiting for a full sweep.

  Running a sweep via DVC (from the app's own directory):
  ```bash
  cd applications/run_hydro_df_electric_sweep
  uv run dvc repro    # runs only stale stages, caches the rest
  ```
  On Euler/other SLURM clusters, submit the job script instead (see
  [Running on Euler](#running-on-euler)):
  ```bash
  sbatch --cpus-per-task=16 run_hydro_df_electric_sweep_job.sh --n-samples 200
  ```

## Developers and Internal Users

### Installation

1.  [install uv](https://docs.astral.sh/uv/getting-started/installation/)
2.  Clone the repository (`git clone git@gitlab.ethz.ch:geg/tango-projects/tango-core.git`).
3.  run `uv sync` to install dependencies (including developer dependencies).

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
    - Option 2: (CURRENTLY NOT FULLY WORKING so let's do the rsync approach) Setup git on Euler (this option is a bit more setup but a bit easier long term)
        1. While logged into Euler, [Setup ssh to connect to gitlab](https://gitlab.ethz.ch/geg/computing-guide/-/wikis/git#setting-up-ssh-for-git)
        1. Clone this repo: `git clone git@gitlab.ethz.ch:geg/tango-projects/tango-core.git`
1. You should already be logged into Euler at this point, and run `cd ~/tango-core/`
1. Run `git checkout develop`
1. Run `curl -LsSf https://astral.sh/uv/install.sh | sh` to
    [install `uv`](https://docs.astral.sh/uv/getting-started/installation/) for your Euler
    user account
1. Run `curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin`
    to install [`just`](https://github.com/casey/just) for your Euler user account (no `sudo`
    needed — installs a prebuilt binary into `~/.local/bin`). Make sure `~/.local/bin` is on your
    `PATH` (add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` if it isn't already).
1. Run `rsync -ahPv ~/tango-core/applications/ /cluster/scratch/<username>/tango-applications/` to get the demo files into your working directory
1. Run `cd /cluster/scratch/<username>/tango-applications/run_hydro_df_electric_sweep`
1. Run `sbatch --cpus-per-task=16 run_hydro_df_electric_sweep_job.sh --n-samples 39` to kick off a slurm job with 16 CPUs, 13 workers, and 39 design evaluations
    Note: by using fewer than 48 CPUs, we're able to avoid having this count against our Euler quota
1. Run `myjobs` to check status
1. When the job is finished, run `uv run --project ~/tango-core run_hydro_df_electric_analysis.py`
