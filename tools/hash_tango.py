"""Regenerate src/tango.hash — a single tracked file whose content
changes whenever any file under src/tango/ changes.

Used as a lightweight DVC dependency (see applications/*/dvc.yaml's
``sweep`` stage) so sweep pipelines invalidate whenever tango itself
changes, without DVC having to hash the entire source tree on every
``dvc repro``.

Run automatically by the ``hash-tango`` pre-commit hook
(.pre-commit-config.yaml) whenever a staged change touches src/tango/.
If the hash changes, this exits 1 (same pattern as ruff --fix / end-of-file-
fixer) so the commit is blocked until the regenerated file is re-staged.

Usage: uv run python tools/hash_tango.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
HASH_FILE = REPO_ROOT / "src" / "tango.hash"


def compute_hash() -> str:
    """Hash of the staged src/tango/ tree (mode + path + blob hash per file).

    Uses git's own index/object-hashing rather than re-hashing file contents
    ourselves, so renames, permission changes, and additions/deletions are
    all picked up for free.
    """
    ls_files = subprocess.run(
        ["git", "ls-files", "-s", "src/tango"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return subprocess.run(
        ["git", "hash-object", "--stdin"],
        input=ls_files,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()


def main() -> int:
    """Write the current hash if it differs from what's on disk."""
    new_hash = compute_hash() + "\n"
    old_hash = HASH_FILE.read_text() if HASH_FILE.exists() else None
    if old_hash == new_hash:
        return 0
    HASH_FILE.write_text(new_hash)
    print(f"Updated {HASH_FILE.relative_to(REPO_ROOT)} — re-stage and commit again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
