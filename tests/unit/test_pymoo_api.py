"""Unit tests for ``tango.pymoo_api``'s CLI/config plumbing.

Narrow by design: ``pymoo_api.py``'s actual optimization behavior is
exercised end-to-end by each ``opt_*.py`` app (real ``Workflow`` runs) --
this file only covers the ``termination_period`` CLI <-> ``PymooConfig``
wiring, where a plain read of the code doesn't substitute for actually
parsing argv and checking the result.
"""

from __future__ import annotations

from pathlib import Path

from tango.pymoo_api import PymooConfig, build_pymoo_parser


def test_pymoo_config_termination_period_default_matches_pymoo_default() -> None:
    """``PymooConfig.termination_period`` defaults to 50, matching pymoo's own
    ``DefaultMultiObjectiveTermination``'s ``period`` default -- so a caller
    that never touches this field gets pymoo's own default behavior,
    unchanged.
    """
    assert PymooConfig().termination_period == 50


def test_build_pymoo_parser_exposes_termination_period_flag_with_default() -> None:
    """``--termination-period`` is a real CLI flag, defaulting to
    ``PymooConfig``'s own default when neither ``params.yaml`` nor an
    explicit flag overrides it.
    """
    parser = build_pymoo_parser(description="test", default_output_dir=Path("outputs"))
    args = parser.parse_args([])
    assert args.termination_period == 50


def test_build_pymoo_parser_termination_period_flag_is_overridable() -> None:
    """An explicit CLI flag overrides the default."""
    parser = build_pymoo_parser(description="test", default_output_dir=Path("outputs"))
    args = parser.parse_args(["--termination-period", "10"])
    assert args.termination_period == 10


def test_build_pymoo_parser_termination_period_flag_reads_from_params() -> None:
    """A ``params.yaml``-sourced ``params`` dict overrides ``PymooConfig``'s
    own default (same precedence as every other pymoo hyperparameter here --
    see ``build_pymoo_parser``'s own docstring).
    """
    parser = build_pymoo_parser(
        description="test",
        default_output_dir=Path("outputs"),
        params={"termination_period": 15},
    )
    args = parser.parse_args([])
    assert args.termination_period == 15
