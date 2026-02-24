# 🚀 Antigravity Rules & Conventions

This document defines the strict rules and conventions that the Antigravity
Agent must follow when working on this repository.

## Commit Workflow & Permissions

- **Never Commit**: Never run `git add`, `git commit`, or propose them via
  `run_command`. The user always handles commits themselves.
- **Suggestion Workflow**: When asked for a commit message, provide 3 options:
  1. **Verbose**: A detailed explanation of *what* and *why*.
  2. **Brief**: A concise summary suitable for a quick scan.
  3. **Short**: A one-line message (subject only).
- **Message Format**:
  ```
  high level description
  - bullet one explaining greater detail
  - bullet two explaining some other detail
      - sub-bullet if needed
  ```

## Dependency Management

### Python

- Add new python dependencies in the `dependencies` section of `pyproject.toml`
  unless you have explicit approval otherwise.
- use `pathlib.Path` in favor of `os.path`
- treat paths as `Path` (after `from pathlib import Path`) instead of strings,
  unless there is clear benefit to using a string
- Don't fix ruff or mypy complaints unless explicitly asked to do so.

## Running Things

- Run tests with `uv run pytest -v`
- Run python stuff with `uv run ...`
- Run the CLI with `uv run tango_cli -f <input.yml>`

---

## Pre-approved auto-run commands

The following commands are considered safe and should be executed with
`SafeToAutoRun: true`:

- `git status`
- `git diff`
- `git log`
- `ls`
- `cat`
- `grep`
- `find`
- `pwd`
- `npx markdownlint-cli`
