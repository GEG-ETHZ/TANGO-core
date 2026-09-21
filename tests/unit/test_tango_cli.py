"""Regression tests for tango_cli's argument parsing.

Covers ``--log-level``'s before/after-subcommand placement specifically —
an easy regression to reintroduce, since argparse's subparser default
handling is subtle: a plausible-looking fix (giving each subparser its own
``--log-level`` with a real default, or having the top-level parser
inherit the same ``SUPPRESS``-defaulted parent as the subparsers) silently
discards whichever value was given at the OTHER position instead of
raising — see ``_build_parser``'s docstring in ``tango_cli.py`` for
the two confirmed-broken variants.
"""

from __future__ import annotations

from tango.tango_cli import _build_parser


def test_log_level_before_subcommand() -> None:
    """``--log-level DEBUG run f.yml`` — value comes from before the subcommand."""
    args = _build_parser().parse_args(["--log-level", "DEBUG", "run", "f.yml"])
    assert args.log_level == "DEBUG"


def test_log_level_after_subcommand() -> None:
    """``run f.yml --log-level DEBUG`` — value comes from after the subcommand."""
    args = _build_parser().parse_args(["run", "f.yml", "--log-level", "DEBUG"])
    assert args.log_level == "DEBUG"


def test_log_level_default_when_omitted() -> None:
    """No ``--log-level`` anywhere — falls back to INFO, not SUPPRESS/unset."""
    args = _build_parser().parse_args(["run", "f.yml"])
    assert args.log_level == "INFO"


def test_log_level_after_validate_subcommand() -> None:
    """``--log-level`` after the subcommand works for ``validate`` too, not just ``run``."""
    args = _build_parser().parse_args(["validate", "f.yml", "--log-level", "WARNING"])
    assert args.log_level == "WARNING"
