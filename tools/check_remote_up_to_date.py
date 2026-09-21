"""Fail fast if the remote has commits we don't have locally.

Meant to run as the FIRST pre-push hook, ahead of mypy/pytest -- git's own
non-fast-forward rejection only happens during the network push itself,
which comes after all local pre-push hooks finish. Without this, a stale
branch fails the slow way: run the whole test suite, then get rejected.

The standard `pre-commit`/`prek` pre-push environment variables
(PRE_COMMIT_REMOTE_NAME, PRE_COMMIT_REMOTE_BRANCH, PRE_COMMIT_TO_REF) are
only set during an actual `git push` -- unset for `just check`, manual
`prek run`, etc. No-op then rather than erroring.

A deliberate force-push (rewriting history already on the remote) will
also trip this check -- that's intentional; use `git push --no-verify` if
you really mean it.
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    """Exit 1 if the pushed branch's remote-tracking ref has moved ahead of us."""
    remote = os.environ.get("PRE_COMMIT_REMOTE_NAME")
    remote_branch_ref = os.environ.get("PRE_COMMIT_REMOTE_BRANCH")
    local_sha = os.environ.get("PRE_COMMIT_TO_REF", "HEAD")

    if not remote or not remote_branch_ref:
        return 0

    branch = remote_branch_ref.removeprefix("refs/heads/")

    fetch = subprocess.run(["git", "fetch", "--quiet", remote, branch], capture_output=True)
    if fetch.returncode != 0:
        return 0  # new branch -- no remote ref yet to fetch at all

    tracking_ref = subprocess.run(
        ["git", "rev-parse", f"{remote}/{branch}"],
        capture_output=True,
        text=True,
    )
    if tracking_ref.returncode != 0:
        return 0  # new branch -- nothing on the remote to be behind

    remote_sha = tracking_ref.stdout.strip()
    is_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", remote_sha, local_sha],
    ).returncode

    if is_ancestor != 0:
        print(
            f"error: '{remote}/{branch}' has commits you don't have locally"
            " -- pull before pushing (fast pre-push check, before mypy/pytest run).",
            file=sys.stderr,
        )
        print(f"hint: git pull --rebase {remote} {branch}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
