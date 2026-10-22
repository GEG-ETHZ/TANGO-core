from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from tango.core.errors import CoolPropError, SaturationError, TESPyError
from tango.workflows.workflow import Workflow  # noqa: E402

ERROR_CONFIG_DIR = Path(__file__).parent / "fixtures" / "coolprop_tespy_errors"


@dataclass
class ErrorCase:
    """Testcase class for simulations that should raise a coolProp error"""

    yml: str
    error_message: str | None = None
    notes: str = ""


@dataclass
class coolPropFailure(ErrorCase):
    """Takes standard ErrorCase and adds error_type = CoolPropError"""

    error_type = CoolPropError
    expect_fail: bool = True
    pass


@dataclass
class TESPyFailure(ErrorCase):
    """Takes standard ErrorCase and adds error_type = TESPyError"""

    error_type = TESPyError
    expect_fail: bool = True


@dataclass
class SaturationFailure(ErrorCase):
    """Takes standard ErrorCase and adds error_type = SaturationError"""

    error_type = SaturationError
    expect_fail: bool = True


FAIL_CASES: list[ErrorCase] = [
    SaturationFailure(
        yml="flexible_SF_negativePressure.yml",
        error_message=re.escape("the fluid is two-phase"),
        notes=(
            "The production well's pressure falls through the produced fluid's saturation "
            "pressure on the way up; the well march stops there with SaturationError instead "
            "of marching on into a negative pressure that CoolProp can't evaluate."
        ),
    ),
]


def run_simulation(case: ErrorCase) -> Workflow:
    """Load and run the flexible Single-Flash YAML config; return the completed Workflow."""
    print(f"Running: {case.yml} from directory {ERROR_CONFIG_DIR}")
    wf = Workflow.from_file(ERROR_CONFIG_DIR / case.yml)
    wf.run()
    print("Simulation complete.")
    return wf


@pytest.mark.parametrize(
    "case",
    FAIL_CASES,
    ids=[c.yml for c in FAIL_CASES],
)
def test_failure(case: ErrorCase, capsys) -> None:
    """Checks that a config raises a CoolPropFailure and the error_message in the test case is a regex match with the error message that is returned"""
    with pytest.raises(case.error_type, match=case.error_message):
        run_simulation(case)
