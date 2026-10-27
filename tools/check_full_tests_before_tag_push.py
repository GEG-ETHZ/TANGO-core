"""Require a clean `just test --all` before pushing a version-release tag.

Release tags (``vX.Y.Z``) are the agreed trigger for "periodically" in
CONTRIBUTING.md's "Every templates/ YAML is regression-tested"
Commandment — a release should never ship without the full suite
(including ``tests/regtest/``'s full-length, slow-marked runs) having
actually passed, not just the fast subset every ordinary push already
runs via this repo's other pre-push hooks.

Not a CI job: ``tests/regtest/`` takes over an hour, so CI
(``.github/workflows/tests.yml``) runs only ``tests/unit/``, and a
tag-triggered CI job would hit the same runtime limit. A local pre-push
hook, gated on the pushed ref, is the only currently-practical
enforcement point.

Uses ``prek``'s ``PRE_COMMIT_LOCAL_BRANCH``/``PRE_COMMIT_REMOTE_BRANCH``
env vars (the same mechanism ``check_remote_up_to_date.py`` already
relies on) rather than reading git's raw pre-push stdin protocol
directly. Confirmed empirically (2026-09-23, via ``prek hook-impl`` fed a
synthetic pre-push stdin line) that ``prek`` sets these reliably even for
a brand-new tag pointing at an already-pushed commit -- the realistic
release-tag case, where the tagged commit itself introduces nothing new.
This is NOT guaranteed of every pre-commit-framework implementation (the
upstream Python ``pre-commit`` project's own ref-resolution logic bails
out early for exactly this "nothing new to push" case and may never
expose ``PRE_COMMIT_REMOTE_BRANCH`` at all) -- if this repo ever migrates
off ``prek`` back to ``pre-commit``, re-verify this before trusting it.

Only set during an actual `git push` (unset for `just check`, manual
`prek run`, etc.) -- see ``check_remote_up_to_date.py``'s own docstring
for the same caveat. No-op then rather than erroring.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

_TAG_PATTERN = re.compile(r"^refs/tags/v\d+\.\d+\.\d+$")


def main() -> int:
    """Exit 1 if this push includes a vX.Y.Z tag and `just test --all` fails."""
    local_branch = os.environ.get("PRE_COMMIT_LOCAL_BRANCH", "")
    remote_branch = os.environ.get("PRE_COMMIT_REMOTE_BRANCH", "")

    if not (_TAG_PATTERN.match(local_branch) or _TAG_PATTERN.match(remote_branch)):
        return 0  # not a version-release tag push (or hook run outside `git push`) -- no-op

    tag = local_branch or remote_branch
    print(
        f"Pushing release tag '{tag}' -- running `just test --all` first "
        "(full suite, including tests/regtest/'s full-length runs; this can take a while).",
        file=sys.stderr,
    )
    result = subprocess.run(["just", "test", "--all"])
    if result.returncode != 0:
        print(
            f"error: `just test --all` failed -- refusing to push release tag '{tag}'. "
            "Fix the failure (or use `git push --no-verify` if you really mean to skip this).",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
