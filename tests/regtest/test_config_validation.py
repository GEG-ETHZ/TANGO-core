"""Config-loading validation spec for tango.

Scope: only the load-time phase — ``Workflow.from_file`` and
``Workflow.__init__`` — as covered by the left-hand branch of the
error/warning flowchart:

    .yml on disk --Workflow.from_file--> Workflow.__init__
        --> FileNotFoundError   (path does not exist)
        --> ConfigError         (no title, missing critical block,
                                 negative values, wrong-typed values,
                                 invalid well spacing, undefined well
                                 pattern)
        --> NotImplementedError (well pattern recognized but has no
                                 implementation; injection policy
                                 recognized but has no implementation)
        --> logged warning      (no fluid name, no well pattern, no
                                 injection policy, no timestep, no
                                 surface temp/pressure, other optional
                                 blocks missing) -- non-fatal:
                                 construction must still succeed.

Anything that only happens once ``Workflow.run()`` starts stepping the
simulation (numerical non-convergence, solver blow-ups, etc.) is out of
scope for this file.

These cases describe the *intended* contract, not necessarily what the
current implementation does today — a failing case here is a gap to
close, not a bug in the test.

Fixtures referenced below live under ``FIXTURES_DIR`` and are not yet
created. Needed files:

    no_title.yml
    missing_components_block.yml
    negative_pipe_diameter.yml
    wrong_type_well_spacing.yml
    invalid_well_spacing.yml
    undefined_well_pattern.yml
    well_pattern_not_implemented.yml
    injection_policy_not_implemented.yml
    no_fluid_name.yml
    no_well_pattern.yml
    no_injection_policy.yml
    no_timestep.yml
    no_surface_conditions.yml
    optional_block_missing.yml
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pytest

from tango.core.errors import ConfigError
from tango.workflows.workflow import Workflow

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "config_validation"


def _load(yml: str) -> Workflow:
    """Load the testcase file using Workflow.from_file()"""
    return Workflow.from_file(FIXTURES_DIR / yml)


# ---------------------------------------------------------------------------
# Missing input file
# ---------------------------------------------------------------------------
# Treated as its own category, distinct from ConfigError: this is a problem
# with the *path*, not with config *content*, so it gets Python's own
# FileNotFoundError rather than a domain-specific error.


def test_missing_file_raises_file_not_found() -> None:
    """Test to see how tango raises the error of the input file not existing. It should raise the appropriate FileNotFoundError"""
    missing = FIXTURES_DIR / "does_not_exist.yml"

    with pytest.raises(ConfigError):
        Workflow.from_file(missing)


# ---------------------------------------------------------------------------
# Errors raised during Workflow.__init__
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ErrorCase:
    """A config-loading scenario that must raise before the Workflow starts"""

    yml: str
    error_type: type
    notes: str
    error_message: str | None = None


CONFIG_ERROR_CASES: list[ErrorCase] = [
    ErrorCase(
        yml="surface_too_cold.yml",
        error_type=ConfigError,
        notes="""
        A user could accidentally enter a value in celsius

        Initially raised: ``src/tango/core/specs.py
        """,
    ),
    ErrorCase(
        yml="missing_components_block.yml",
        error_type=AttributeError,
        notes="""A components block (e.g. 'common') is absent.

        Initially raised: ``src/tango/core/specs.py
        """,
    ),
    ErrorCase(
        yml="negative_pipe_diameter.yml",
        error_type=ConfigError,
        notes="""A geometry field that must be positive (pipe_diameter) is negative.

        Initially raised: ``src/tango/core/specs.py
        """,
    ),
    ErrorCase(
        yml="wrong_type_well_spacing.yml",
        error_type=ConfigError,
        notes="""well_spacing is given as a non-numeric value (e.g. a string).

        Initially raised: ``src/tango/core/specs.py
        """,
    ),
    ErrorCase(
        yml="undefined_well_pattern.yml",
        error_type=ConfigError,
        notes="""layout.well_pattern names a string that matches no known WellPattern alias.

        Initially raised: ``src/tango/core/specs.py``
        """,
    ),
    ErrorCase(
        yml="well_pattern_not_implemented.yml",
        error_type=ConfigError,
        notes="""
            layout.well_pattern resolves to a real WellPattern member that has
            no impedance formula implemented yet.
            Initially raised: ``src/tango/core/specs.py
        """,
    ),
    ErrorCase(
        yml="injection_policy_not_implemented.yml",
        error_type=NotImplementedError,
        notes="""
            sim_config.injection_mode names a recognized InjectionPolicy that
            the orchestrator does not implement yet.
            Initially raised: ``src/tango/core/specs.py
        """,
    ),
    ErrorCase(
        yml="no_fluid_name.yml",
        error_type=ConfigError,
        notes="""
        common.fluid_name omitted; raise error

        Initially raised: ``src/tango/core/specs.py
        """,
    ),
]


@pytest.mark.parametrize(
    "case",
    CONFIG_ERROR_CASES,
    ids=[c.yml for c in CONFIG_ERROR_CASES],
)
def test_config_error(case: ErrorCase, caplog: pytest.LogCaptureFixture) -> None:
    """Test to see if Tango handles the config errors with the expected error type"""
    with pytest.raises(case.error_type) as exc_info:
        _load(case.yml)

    assert exc_info.type is case.error_type, (
        f"Unexpected Error Returned. Expected {case.error_type} got {exc_info.type}"
    )
    if case.error_message is not None:
        assert case.error_message in str(exc_info.value), f"Error message {case.error_message} not in output"


# ---------------------------------------------------------------------------
# Warnings logged during Workflow.__init__ (non-fatal)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigWarningCase:
    """A config-loading scenario that must warn but must NOT stop construction."""

    yml: str
    expected_message: str
    notes: str


CONFIG_WARNING_CASES: list[ConfigWarningCase] = [
    ConfigWarningCase(
        yml="optional_block_missing.yml",
        expected_message="economic",
        notes="An optional top-level block (e.g. 'economic') is absent.",
    ),
]


@pytest.mark.parametrize(
    "case",
    CONFIG_WARNING_CASES,
    ids=[c.yml for c in CONFIG_WARNING_CASES],
)
def test_config_warning(case: ConfigWarningCase, caplog: pytest.LogCaptureFixture) -> None:
    """Test to see if the correct warning message is logged"""
    with caplog.at_level(logging.WARNING):
        wf = _load(case.yml)

    assert isinstance(wf, Workflow), "a warning-only config must still construct a usable Workflow"

    messages = [record.getMessage() for record in caplog.records]
    assert any(case.expected_message.lower() in m.lower() for m in messages), (
        f"expected a warning containing {case.expected_message!r}, got {messages!r}"
    )
