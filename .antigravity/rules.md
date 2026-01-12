# 🚀 Antigravity Rules & Conventions

This document defines the strict rules and conventions that the Antigravity
Agent must follow when working on this repository.

## Commit Workflow & Permissions

- **Never Auto-Commit**: You are strictly forbidden from committing changes
  automatically without explicit user approval.
- **Suggestion Workflow**: When you are ready to commit, you must propose the
  commit to the user by providing 3 distinct commit message options:
  1. **Verbose**: A detailed explanation of *what* and *why*.
  2. **Brief**: A concise summary suitable for a quick scan.
  3. **Short**: A one-line message (Subject only).

## Dependency Management

### Python

- Add new python dependendcies in the dependendcies section of pyproject.toml
  unless you have explicit approval otherwise.
- use `pathlib.Path` in favor of `os.path`
- treat paths as `Path` (after `from pathlib import Path`) instead of strings,
  unless there is clear benefit to using a string

---

## pre-approved auto-run commands

the following commands are considered safe and should be executed with
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
