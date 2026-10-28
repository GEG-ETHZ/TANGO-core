# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""The ``grouped_subsurface`` component: an AGS loop's three wells as one circuit component.

The ``numerical`` variant must give exactly the same results as the same
three wells configured as separate circuit components; ``_ungrouped``
builds that equivalent config from ``AGS_ORC_electric_grouped_subsurface.yml``.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from tango_core.components.well.base import WellRole
from tango_core.components.well.grouped_subsurface import (
    LOOP_SET_SEGMENT_KEYS,
    SEGMENT_NAMES,
    NumericalGroupedSubsurface,
)
from tango_core.core.errors import ConfigError
from tango_core.core.stream import Stream
from tango_core.workflows.workflow import Workflow

_CONFIGS = Path(__file__).resolve().parents[2] / "templates"
_GROUPED = "AGS_ORC_electric_grouped_subsurface.yml"


def _load(name: str, num_tsteps: int | None = None) -> dict[str, Any]:
    cfg: dict[str, Any] = yaml.safe_load((_CONFIGS / name).read_text())
    if num_tsteps is not None:
        cfg["sim_config"]["num_tsteps"] = num_tsteps
    return cfg


def _ungrouped(cfg: dict[str, Any]) -> dict[str, Any]:
    """The same system with the grouped subsurface's three segments as separate circuit components (indices 0-2)."""
    cfg = copy.deepcopy(cfg)
    components = cfg["components"]
    group = components.pop("grouped_subsurface")
    surface = components.pop("surface")
    for idx, name in enumerate(SEGMENT_NAMES):
        components[name] = {
            "type": "horizontal_well" if name == "horizontal_well" else name,
            "variant": "numerical",
            "component_idx": idx,
            "prev": (idx - 1) % 4,
            "next": idx + 1,
            **group[name],
        }
        if name == "horizontal_well":
            components[name]["angle_from_vert_deg"] = 90.0
    components["surface"] = {**surface, "component_idx": 3, "prev": 2, "next": 0}
    cfg["sim_config"]["bc_checkpoint_idx"] = 3
    return cfg


def _loop(wf: Workflow) -> NumericalGroupedSubsurface:
    loop = wf._orchestrator.components["grouped_subsurface"]  # noqa: SLF001
    assert isinstance(loop, NumericalGroupedSubsurface)
    return loop


def test_grouped_subsurface_reproduces_three_separate_wells_exactly() -> None:
    """Every year's production wellhead state, surface power and the LCOE are bit-identical."""
    three = Workflow(_ungrouped(_load(_GROUPED)))
    three.run()
    loop_wf = Workflow(_load(_GROUPED))
    loop_wf.run()

    three_comps = three._orchestrator.components  # noqa: SLF001
    loop = _loop(loop_wf)
    for name in SEGMENT_NAMES:
        assert getattr(loop, name).history.h_cells == three_comps[name].history.h_cells, name
        assert getattr(loop, name).history.P_cells == three_comps[name].history.P_cells, name
    production = three_comps["production_well"].history
    assert loop.history.h_outlet == production.h_outlet
    assert loop.history.P_outlet == production.P_outlet
    assert loop.history.T_outlet == production.T_outlet
    loop_surface = loop_wf._orchestrator.components["surface"].history  # noqa: SLF001
    assert loop_surface.net_power_W == three_comps["surface"].history.net_power_W
    assert loop_wf._economic is not None and three._economic is not None  # noqa: SLF001
    assert loop_wf._economic.state.LCOE.get_fresh() == three._economic.state.LCOE.get_fresh()  # noqa: SLF001


def test_linked_lengths_are_derived_from_the_injection_well() -> None:
    """Production length and horizontal wellhead depth follow the injection length; well_spacing the loop length."""
    cfg = _load(_GROUPED, num_tsteps=1)
    cfg["components"]["grouped_subsurface"]["injection_well"]["well_length"] = 5000.0
    cfg["components"]["grouped_subsurface"]["horizontal_well"]["well_length"] = 2000.0
    wf = Workflow(cfg)
    loop = _loop(wf)
    assert loop.production_well.well_length == 5000.0
    assert loop.horizontal_well.wellhead_depth == 5000.0
    assert wf._layout.well_spacing == 2000.0  # noqa: SLF001


def test_disagreeing_linked_length_is_rejected() -> None:
    """A production well length that differs from the injection well's is a ConfigError, not silently replaced."""
    cfg = _load(_GROUPED, num_tsteps=1)
    cfg["components"]["grouped_subsurface"]["production_well"]["well_length"] = 7000.0
    with pytest.raises(ConfigError, match=r"production_well\.well_length"):
        Workflow(cfg)


@pytest.mark.parametrize("key", LOOP_SET_SEGMENT_KEYS)
def test_segment_block_may_not_set_loop_set_fields(key: str) -> None:
    """A segment block giving a field the loop sets for it is a ConfigError."""
    cfg = _load(_GROUPED, num_tsteps=1)
    cfg["components"]["grouped_subsurface"]["horizontal_well"][key] = 90.0
    with pytest.raises(ConfigError):
        Workflow(cfg)


def test_config_round_trips_and_segment_blocks_stay_clean() -> None:
    """``to_dict()`` loads back, and its segment blocks hold none of the fields the loop sets."""
    wf = Workflow(_load(_GROUPED, num_tsteps=1))
    dumped = wf.to_dict()
    for name in SEGMENT_NAMES:
        assert not set(LOOP_SET_SEGMENT_KEYS) & dumped["components"]["grouped_subsurface"][name].keys()
    reloaded = Workflow(copy.deepcopy(dumped))
    assert reloaded.to_dict() == dumped


def test_well_sections_cost_the_three_segments_by_role() -> None:
    """The economic model sees an injection, a horizontal and a production section with the loop's geometry."""
    loop = _loop(Workflow(_load(_GROUPED, num_tsteps=1)))
    sections = loop.well_sections()
    assert [s.role for s in sections] == [WellRole.INJECTION, WellRole.HORIZONTAL, WellRole.PRODUCTION]
    assert [s.well_length for s in sections] == [8000.0, 3000.0, 8000.0]
    assert {s.diameter for s in sections} == {0.311}


def test_convergence_snapshot_covers_every_segment() -> None:
    """Restoring a snapshot rolls back each segment's dimensionless time, not just the loop's own state."""
    loop = _loop(Workflow(_load(_GROUPED, num_tsteps=1)))
    inlet = Stream.fresh(h=100_000.0, P=1_500_000.0, mass_rate=30.0)
    snapshot = loop.snapshot_convergence_state()
    loop.solve(inlet)
    t_d_after_one_solve = [segment.state.t_d.get_fresh() for segment in loop.segments()]

    loop.restore_convergence_state(snapshot)
    loop.mark_all_stale()
    loop.solve(inlet)
    assert [segment.state.t_d.get_fresh() for segment in loop.segments()] == t_d_after_one_solve


def test_mass_rate_lost_in_the_circuit_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A component returning less mass than it received fails loudly instead of lowering the injected rate."""
    original_solve = NumericalGroupedSubsurface.solve

    def leaky_solve(self: NumericalGroupedSubsurface, inlet: Stream) -> Stream:
        outlet = original_solve(self, inlet)
        return Stream.fresh(
            h=outlet.h.get_fresh(),
            P=outlet.P.get_fresh(),
            mass_rate=0.95 * outlet.mass_rate.get_fresh(),
        )

    monkeypatch.setattr(NumericalGroupedSubsurface, "solve", leaky_solve)
    wf = Workflow(_load(_GROUPED, num_tsteps=1))
    with pytest.raises(ConfigError, match="does not conserve mass"):
        wf.run()
