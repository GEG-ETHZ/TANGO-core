"""Regenerate src/tango_core.hash — a single tracked file whose content
changes whenever any file under src/tango_core/ changes.

Used as a lightweight DVC dependency (see each opt app's dvc.yaml) so
application pipelines invalidate whenever tango itself changes, without DVC having to hash the entire source tree on every
``dvc repro``.

Run automatically by the ``hash-tango`` pre-commit hook
(.pre-commit-config.yaml) whenever a staged change touches src/tango_core/.
If the hash changes, this exits 1 (same pattern as ruff --fix / end-of-file-
fixer) so the commit is blocked until the regenerated file is re-staged.

With ``--stage`` (what ``just hash-src`` runs) it also stages the file and
exits 0, so the next commit passes the hook first time.

The hash must be identical on every platform: it is computed from git's own
output passed as bytes, and the file is written with Unix (LF) line endings,
so Windows' newline translation can't change either.

Usage: uv run python tools/hash_tango.py [--stage]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
HASH_FILE = REPO_ROOT / "src" / "tango_core.hash"


def compute_hash() -> str:
    """Hash of the staged src/tango_core/ tree (mode + path + blob hash per file).

    Uses git's own index/object-hashing rather than re-hashing file contents
    ourselves, so renames, permission changes, and additions/deletions are
    all picked up for free.
    """
    ls_files = subprocess.run(
        ["git", "ls-files", "-s", "src/tango_core"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    # Bytes, not text: in text mode Windows would turn every "\n" into "\r\n"
    # on the way into git, giving a different hash for the same tree.
    return (
        subprocess.run(
            ["git", "hash-object", "--stdin"],
            input=ls_files.encode(),
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )


def main(stage: bool = False) -> int:
    """Write the current hash if it differs from what's on disk; with ``stage``, also ``git add`` it.

    Returns:
        1 if the file changed and ``stage`` is off (blocks a commit, as a
        hook), otherwise 0.

    """
    new_hash = compute_hash() + "\n"
    # Compare without line endings: Git for Windows usually checks text files
    # out with CRLF, which must not count as a different hash.
    old_hash = HASH_FILE.read_bytes().decode().strip() if HASH_FILE.exists() else None
    rel = HASH_FILE.relative_to(REPO_ROOT)
    changed = old_hash != new_hash.strip()
    if changed:
        HASH_FILE.write_bytes(new_hash.encode())
    if stage:
        subprocess.run(["git", "add", str(rel)], cwd=REPO_ROOT, check=True)
        print(f"Staged the updated {rel}." if changed else f"{rel} already up to date.")
        return 0
    if changed:
        print(f"Updated {rel} — re-stage and commit again.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(stage="--stage" in sys.argv[1:]))
