from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from tango.components.well.numerical import NumericalProductionWellWithPump
from tango.core.errors import CoolPropError, SaturationError, TESPyError, WellPressureCollapseError
from tango.core.stream import Stream
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


def test_pump_less_well_reports_its_own_collapse() -> None:
    """A production well with no pump target re-raises its unaided march's failure instead of solving for a pump."""
    scenario = Path(__file__).parent / "fixtures" / "scenarios" / "hydro_sf_electric.yml"
    config = yaml.safe_load(scenario.read_text())
    components = Workflow(config)._orchestrator.components  # noqa: SLF001
    well = next(c for c in components.values() if isinstance(c, NumericalProductionWellWithPump))
    well.target_extraction_pressure = 0.0
    marches: list[float] = []

    def collapse_once(original: Callable[..., Any]) -> Callable[..., Any]:
        def march(h: float, P: float, *args: Any) -> Any:  # noqa: N803
            marches.append(P)
            if len(marches) == 1:
                raise WellPressureCollapseError("forced collapse of the unaided march")
            return original(h, P, *args)

        return march

    well._march = collapse_once(well._march)  # type: ignore[method-assign]  # noqa: SLF001
    with pytest.raises(WellPressureCollapseError, match="forced collapse of the unaided march"):
        well.solve(Stream.fresh(h=4.0e5, P=2.0e7, mass_rate=30.0))
    assert len(marches) == 1
