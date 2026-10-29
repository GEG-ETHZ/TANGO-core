"""Fail fast if the remote has commits we don't have locally.

Meant to run as the FIRST pre-push hook, ahead of mypy/pytest -- git's own
non-fast-forward rejection only happens during the network push itself,
which comes after all local pre-push hooks finish. Without this, a stale
branch fails the slow way: run the whole test suite, then get rejected.

The standard `pre-commit`/`prek` pre-push environment variables
(PRE_COMMIT_REMOTE_NAME, PRE_COMMIT_REMOTE_BRANCH, PRE_COMMIT_TO_REF) are
only set during an actual `git push` -- unset for `just check`, manual
`prek run`, etc. No-op then rather than erroring.

Rewriting your own already-pushed commits (``git commit --amend``, a
rebase) passes: if the remote tip is a commit in your local reflog, it's one
you made or checked out yourself, so the remote holds nothing you haven't
seen, and the push needs ``--force-with-lease`` as usual. A remote tip that
isn't in your reflog means someone else pushed, and the check still fails.
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

    if is_ancestor != 0 and _in_local_reflog(remote_sha):
        print(
            f"note: '{remote}/{branch}' is a commit from your own reflog (rewritten history, e.g. an"
            " amend or rebase) -- not blocking; push with --force-with-lease.",
            file=sys.stderr,
        )
        return 0

    if is_ancestor != 0:
        print(
            f"error: '{remote}/{branch}' has commits you don't have locally"
            " -- pull before pushing (fast pre-push check, before mypy/pytest run).",
            file=sys.stderr,
        )
        print(f"hint: git pull --rebase {remote} {branch}", file=sys.stderr)
        return 1

    return 0


def _in_local_reflog(sha: str) -> bool:
    """True if ``sha`` appears in the reflog of ``HEAD`` or any local branch.

    Remote-tracking refs are deliberately excluded: their reflogs record
    every fetch, including the one ``main()`` just did, so the remote tip
    would always be found there.
    """
    branches = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)", "refs/heads"],
        capture_output=True,
        text=True,
    ).stdout.split()
    for ref in ["HEAD", *branches]:
        reflog = subprocess.run(
            ["git", "log", "--walk-reflogs", "--format=%H", ref],
            capture_output=True,
            text=True,
        )
        if reflog.returncode == 0 and sha in reflog.stdout.split():
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
