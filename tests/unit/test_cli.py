# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for tango_core's argument parsing.

Covers ``--log-level``'s before/after-subcommand placement specifically —
an easy regression to reintroduce, since argparse's subparser default
handling is subtle: a plausible-looking fix (giving each subparser its own
``--log-level`` with a real default, or having the top-level parser
inherit the same ``SUPPRESS``-defaulted parent as the subparsers) silently
discards whichever value was given at the OTHER position instead of
raising — see ``_build_parser``'s docstring in ``cli.py`` for
the two confirmed-broken variants.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tango_core.cli import _build_parser


def test_log_level_before_subcommand() -> None:
    """``--log-level DEBUG run f.yml`` — value comes from before the subcommand."""
    args = _build_parser().parse_args(["--log-level", "DEBUG", "run", "f.yml", "--no-save"])
    assert args.log_level == "DEBUG"


def test_log_level_after_subcommand() -> None:
    """``run f.yml --log-level DEBUG`` — value comes from after the subcommand."""
    args = _build_parser().parse_args(["run", "f.yml", "--no-save", "--log-level", "DEBUG"])
    assert args.log_level == "DEBUG"


def test_log_level_default_when_omitted() -> None:
    """No ``--log-level`` anywhere — falls back to INFO, not SUPPRESS/unset."""
    args = _build_parser().parse_args(["run", "f.yml", "--no-save"])
    assert args.log_level == "INFO"


def test_log_level_after_validate_subcommand() -> None:
    """``--log-level`` after the subcommand works for ``validate`` too, not just ``run``."""
    args = _build_parser().parse_args(["validate", "f.yml", "--log-level", "WARNING"])
    assert args.log_level == "WARNING"


def test_no_save_writes_nothing() -> None:
    """``--no-save`` leaves ``save_dir`` unset, so ``_cmd_run`` writes nothing."""
    args = _build_parser().parse_args(["run", "f.yml", "--no-save"])
    assert args.no_save
    assert args.save_dir is None


@pytest.mark.parametrize(
    "extra",
    [[], ["--save-dir", "out", "--no-save"]],
    ids=["neither", "both"],
)
def test_run_needs_exactly_one_of_save_dir_and_no_save(
    extra: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``run`` without ``--save-dir``/``--no-save``, or with both, fails naming the two flags."""
    with pytest.raises(SystemExit) as excinfo:
        _build_parser().parse_args(["run", "f.yml", *extra])
    assert excinfo.value.code == 2
    assert "--save-dir" in capsys.readouterr().err


def test_save_dir_parses_path() -> None:
    """``--save-dir DIR`` parses to a Path, not a bare string."""
    args = _build_parser().parse_args(["run", "f.yml", "--save-dir", "out/here"])
    assert args.save_dir == Path("out/here")
