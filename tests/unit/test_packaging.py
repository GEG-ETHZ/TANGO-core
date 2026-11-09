# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""The wheel's ``force-include`` list in ``pyproject.toml`` ships every template and application file.

The list names each ``templates/`` and ``applications/`` file one by one, so a
new or renamed file that isn't added to it is silently missing from the
published package until ``tango_core init`` fails to copy it.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _application_left_out(path: str) -> bool:
    """Whether a tracked ``applications/`` file stays out of the wheel by design.

    The reasons are in the comment above the list in ``pyproject.toml``.
    """
    return (
        path.startswith("applications/_on_hold/")
        or path == "applications/README.md"
        or path.endswith(("/dvc.lock", "/outputs/.gitignore", "/REDESIGN_TODO.md"))
    )


def _template_left_out(path: str) -> bool:
    """Whether a tracked ``templates/`` file stays out of the wheel: none do.

    The RAFT example (``AGS_ORC_electric_raft.yml``, ``templates/raft/``) ships
    too, so ``tango_core init`` copies a runnable RAFT case; RAFT itself is
    installed separately.
    """
    del path
    return False


def _tracked_files(directory: str) -> set[str]:
    """Every git-tracked file under ``directory``; skips outside a git checkout (e.g. an unpacked sdist)."""
    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("needs a git checkout of the repository")
    listing = subprocess.run(
        ["git", "ls-files", directory],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return set(listing.splitlines())


@pytest.mark.parametrize(
    ("directory", "left_out"),
    [("templates/", _template_left_out), ("applications/", _application_left_out)],
)
def test_force_include_lists_every_file(directory: str, left_out: Callable[[str], bool]) -> None:
    """force-include matches ``git ls-files <directory>`` minus the deliberate exclusions."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as file:
        force_include = tomllib.load(file)["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    listed = {source: target for source, target in force_include.items() if source.startswith(directory)}
    expected = {path for path in _tracked_files(directory) if not left_out(path)}

    assert sorted(expected - listed.keys()) == [], "add these to force-include in pyproject.toml"
    assert sorted(listed.keys() - expected) == [], "remove these from force-include, or track them in git"
    misplaced = sorted(source for source, target in listed.items() if target != f"tango_core/{source}")
    assert misplaced == [], "each target should be tango_core/<source path>"
