# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""``NumericalWell``'s linked ``well_length``/``num_cells``/``cell_length`` and its derived fields.

``well_length = num_cells * cell_length``: a config may give either of the
other two, both (they must agree) or neither (default resolution). A value
derived from the inputs is never silently replaced, and changing a length
in a config dict goes through ``set_well_length``, which makes the caller
say which of the other two follows.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from tango_core.components.well.numerical import (
    WellLengthSideEffect,
    default_num_cells,
    set_well_length,
)
from tango_core.core.errors import ConfigError
from tango_core.workflows.linked_quantities import expunge_linked_quantities
from tango_core.workflows.workflow import Workflow

_AGS = Path(__file__).resolve().parents[2] / "templates" / "AGS_direct_heat.yml"


def _config(**loop: Any) -> dict[str, Any]:
    """AGS_direct_heat.yml with a 707 m loop (10 cells by default), overridden by ``loop``."""
    cfg: dict[str, Any] = yaml.safe_load(_AGS.read_text())
    cfg["sim_config"]["num_tsteps"] = 1
    cfg["components"]["horizontal_well"].update({"well_length": 707.0, **loop})
    return cfg


def _loop(cfg: dict[str, Any]) -> Any:
    """The built horizontal well."""
    return Workflow(cfg)._orchestrator.components["horizontal_well"]  # noqa: SLF001


def test_neither_given_uses_default_resolution() -> None:
    """No num_cells or cell_length: one cell per ~250 m, rounded up to a multiple of 10."""
    loop = _loop(_config(well_length=8000.0))
    assert loop.num_cells == default_num_cells(8000.0) == 40
    assert loop.cell_length == pytest.approx(200.0)


def test_cell_length_alone_is_a_target() -> None:
    """cell_length alone: the fewest cells no longer than it, then the exact length."""
    loop = _loop(_config(well_length=8000.0, cell_length=150.0))
    assert loop.num_cells == 54
    assert loop.cell_length == pytest.approx(8000.0 / 54)


def test_num_cells_alone_sets_cell_length() -> None:
    """num_cells alone: cell_length is well_length / num_cells."""
    loop = _loop(_config(well_length=8000.0, num_cells=10))
    assert loop.cell_length == pytest.approx(800.0)


def test_inconsistent_num_cells_and_cell_length_raise() -> None:
    """Both given but not multiplying out to well_length is a ConfigError."""
    with pytest.raises(ConfigError, match="num_cells"):
        _loop(_config(well_length=8000.0, num_cells=10, cell_length=100.0))


def test_mismatched_derived_value_raises_instead_of_being_overwritten() -> None:
    """A derived value in the config that disagrees with the computed one raises."""
    with pytest.raises(ConfigError, match="T_r"):
        _loop(_config(well_length=8000.0, T_r=[1.0]))


def test_to_dict_omits_derived_values_so_edited_inputs_reload() -> None:
    """A to_dict() copy with an edited input (here rock_k) rebuilds without a stale derived value."""
    wf_cfg = Workflow(_config()).to_dict()
    assert "T_r" not in wf_cfg["components"]["horizontal_well"]
    wf_cfg["common"]["rock_k"] = 3.0
    Workflow(wf_cfg)


def test_to_dict_keeps_only_the_discretization_the_config_gave() -> None:
    """A default cell count isn't pinned, so an edited to_dict() copy gets the default for its new length."""
    wf_cfg = Workflow(_config()).to_dict()
    assert not {"num_cells", "cell_length"} & set(wf_cfg["components"]["horizontal_well"])
    expunge_linked_quantities(wf_cfg)
    wf_cfg["components"]["horizontal_well"]["well_length"] = 8000.0
    assert _loop(wf_cfg).num_cells == 40

    given = Workflow(_config(num_cells=10)).to_dict()["components"]["horizontal_well"]
    assert given["num_cells"] == 10
    assert "cell_length" not in given


def test_editing_length_with_both_given_raises() -> None:
    """A config pinning both num_cells and cell_length can't have its length changed without set_well_length."""
    cfg = _config(num_cells=10, cell_length=70.7)
    cfg["components"]["horizontal_well"]["well_length"] = 8000.0
    with pytest.raises(ConfigError, match="set_well_length"):
        _loop(cfg)


@pytest.mark.parametrize(
    ("side_effect", "num_cells", "cell_length"),
    [
        (WellLengthSideEffect.KEEP_CELL_LENGTH, 114, 8000.0 / 114),
        (WellLengthSideEffect.KEEP_NUM_CELLS, 10, 800.0),
    ],
)
def test_set_well_length_side_effects(
    side_effect: WellLengthSideEffect,
    num_cells: int,
    cell_length: float,
) -> None:
    """A 707 m loop configured with 10 cells of 70.7 m, lengthened to 8000 m."""
    cfg = _config(num_cells=10)
    set_well_length(cfg["components"]["horizontal_well"], 8000.0, side_effect)
    loop = _loop(cfg)
    assert loop.num_cells == num_cells
    assert loop.cell_length == pytest.approx(cell_length)


def test_set_well_length_on_raw_config_keeps_default_resolution() -> None:
    """A config that gives neither keeps giving neither, so the new length gets the default."""
    cfg = _config()
    set_well_length(cfg["components"]["horizontal_well"], 8000.0, WellLengthSideEffect.KEEP_CELL_LENGTH)
    assert "num_cells" not in cfg["components"]["horizontal_well"]
    assert _loop(copy.deepcopy(cfg)).num_cells == 40


@pytest.mark.parametrize("num_cells", [0, -5, 2.5, True, "10"])
def test_num_cells_must_be_a_positive_integer(num_cells: Any) -> None:
    """Zero, negative, fractional, boolean or string cell counts are config errors."""
    with pytest.raises(ConfigError, match="positive integer"):
        _loop(_config(num_cells=num_cells))


@pytest.mark.parametrize("cell_length", [0.0, -100.0])
def test_cell_length_must_be_positive(cell_length: float) -> None:
    """A zero or negative target cell length is a config error."""
    with pytest.raises(ConfigError, match="cell_length must be positive"):
        _loop(_config(cell_length=cell_length))
