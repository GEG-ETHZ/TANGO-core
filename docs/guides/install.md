# Install

There are two ways to install TANGO:

| You want to | Install as | Section |
|---|---|---|
| Use TANGO in your own analysis project, pinned to a release | A dependency | [Use a release](#use-a-release) |
| Change TANGO itself | A development checkout | [Develop TANGO](#develop-tango) |

## Prerequisites

| Requirement | Version | Install |
|---|---|---|
| Python | 3.11 (TANGO requires `>=3.11,<3.12`) | macOS: `brew install python@3.11` · Ubuntu/Debian: `sudo apt install python3.11 python3.11-venv` · Windows: [python.org](https://www.python.org/downloads/windows/) |
| uv | latest | macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh \| sh` · Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| GitHub SSH access | — | [Connect to GitHub with SSH](https://docs.github.com/en/authentication/connecting-to-github-with-ssh) |

TANGO is internal to the GEG group (see [`NOTICE`](https://github.com/GEG-ETHZ/TANGO-core/blob/main/NOTICE) and [`LICENSE.txt`](https://github.com/GEG-ETHZ/TANGO-core/blob/main/LICENSE.txt)). Installing it requires read access to the private GitHub repository [`GEG-ETHZ/TANGO-core`](https://github.com/GEG-ETHZ/TANGO-core); there is no public package.

## Use a release

1. Create a new project for your analysis:

   ```bash
   uv init --python 3.11 my-study && cd my-study
   ```

   In the new `pyproject.toml`, set `requires-python = ">=3.11,<3.12"`; TANGO supports Python 3.11 only, and `uv` refuses a dependency whose Python range is narrower than the project's.

2. From inside the new project, add TANGO pinned to a release tag:

   ```bash
   uv add "git+ssh://git@github.com/GEG-ETHZ/TANGO-core.git" --tag v1.1.0
   ```

   `uv` records the tag and the resolved commit in `pyproject.toml` and `uv.lock`, so the build stays reproducible until you change the tag. Replace `v1.1.0` with the release you need; releases are listed in [`CHANGELOG.md`](../project/changelog.md) and cut as described in [Contributing](../project/contributing.md#cutting-an-internal-geg-only-release).

3. Check the installation:

   ```bash
   uv run tango_cli --version
   ```

   Expected output starts with `tango 1.0.1`, followed by the internal distribution notice.

4. Copy the example configs into your project as a starting point:

   ```bash
   uv run tango_cli init .
   ```

   This copies the `example_configs/` that ship with the installed version. It fails if `example_configs/` already exists, so local edits are never overwritten. To also copy a sweep, optimization or demo pipeline, add `--app <name>` (repeatable); `--list-apps` prints the available names.

To upgrade, run the `uv add` command again with the new tag.

The distribution is named `tango-core`, but the import name is `tango`:

```python
from tango.workflows.workflow import Workflow
```

## Develop TANGO

1. Clone the repository and install everything, including the development tools and git hooks:

   ```bash
   git clone git@github.com:GEG-ETHZ/TANGO-core.git tango-core
   cd tango-core
   just setup
   ```

   Without [`just`](https://github.com/casey/just), run `uv sync`, then install the hooks as shown in [Contributing](../project/contributing.md#development-setup).

2. Optional: install [direnv](https://direnv.net/docs/installation.html) and hook it into your shell. `just setup` approves the repository's `.envrc`. From then on, entering the directory checks the lock file, syncs dependencies and activates the virtual environment.

3. Check the setup with a first run:

   ```bash
   uv run tango_cli run example_configs/hydro_sf_electric.yml
   ```

### Running checks

| Check | Command |
|---|---|
| Everything, in CI order (format, lint, type check, fast tests) | `just check` |
| Tests, fast subset | `just test` |
| Tests, full suite | `just test --all` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` (add `--check` to verify only) |
| Type check | `just typecheck` |
| Docs site | `just docs-build` |

Run every command from the repository root.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Permission denied (publickey)` during `uv add` or `git clone` | Your SSH key is not registered on GitHub, or your account lacks access to `GEG-ETHZ/TANGO-core`. Follow the SSH guide linked above, then ask a maintainer for access. |
| `requires-python` / no matching Python | TANGO needs Python 3.11 exactly. Install it, or let uv fetch it: `uv python install 3.11`. |
| `tango_cli init` fails because `example_configs` exists | Intended: it never overwrites. Choose another destination, or move the existing folder. |
