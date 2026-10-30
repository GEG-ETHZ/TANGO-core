# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""The ``grouped_subsurface`` component: an AGS loop's three wells as one circuit component.

The loop fixes its production wellhead pressure and solves for the
injection pressure, while the same three wells configured as separate
circuit components fix the injection pressure and march to whatever
production pressure results. The ``numerical`` variant must be the same
physics solved the other way round: given each year's production pressure
from the separate-well run, it must find that run's injection pressure and
reproduce its results to 1e-6 relative. ``_ungrouped`` builds the
separate-well config from ``AGS_ORC_electric_grouped_subsurface.yml``.
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
    cfg: dict[str, Any] = yaml.safe_load((_CONFIGS / name).read_text(encoding="utf-8"))
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


_EQUIVALENCE_REL_TOL = 1e-6
"""How closely the outlet-pressure solve must reproduce the inlet-pressure-driven march."""


def test_outlet_pressure_solve_reproduces_the_inlet_pressure_driven_march() -> None:
    """Given each year's production pressure, the loop finds the old injection pressure and the old results.

    The separate-well run fixes the injection pressure (the surface plant's
    ``injection_pressure``) and marches downstream. Driving the grouped loop
    year by year with that run's injection enthalpy and mass rate, and its
    production pressure as the outlet condition, must recover the injection
    pressure and every segment's cell profiles, the production wellhead state
    and the heat extracted, to 1e-6 relative, over all 25 years (the rock's
    thermal history included). Each year's shooting solve starts from a guess
    far from the answer.
    """
    three = Workflow(_ungrouped(_load(_GROUPED)))
    three.run()
    wells = {name: three._orchestrator.components[name].history for name in SEGMENT_NAMES}  # noqa: SLF001
    injection, production = wells["injection_well"], wells["production_well"]

    loop = _loop(Workflow(_load(_GROUPED)))
    n_tsteps = len(production.P_outlet)
    for t in range(n_tsteps):
        loop.mark_all_stale()
        guess = 0.5 * injection.P_inlet[t]
        inlet = Stream.fresh(h=injection.h_inlet[t], P=guess, mass_rate=injection.mass_rate[t])
        loop.solve_for_outlet_pressure(inlet, production.P_outlet[t])
        loop.accept_timestep()
        loop.record(t)

    rel = _EQUIVALENCE_REL_TOL
    assert loop.history.P_inlet == pytest.approx(injection.P_inlet, rel=rel)
    assert loop.history.P_outlet == pytest.approx(production.P_outlet, rel=rel)
    assert loop.history.h_outlet == pytest.approx(production.h_outlet, rel=rel)
    assert loop.history.T_outlet == pytest.approx(production.T_outlet, rel=rel)
    heat_old = [
        m * (h_out - h_in)
        for m, h_in, h_out in zip(injection.mass_rate, injection.h_inlet, production.h_outlet, strict=True)
    ]
    assert loop.history.heat_extracted_watts == pytest.approx(heat_old, rel=rel)
    for name in SEGMENT_NAMES:
        new, old = getattr(loop, name).history, wells[name]
        for cells in ("P_cells", "h_cells", "T_cells"):
            for t in range(n_tsteps):
                assert getattr(new, cells)[t] == pytest.approx(getattr(old, cells)[t], rel=rel), (
                    name,
                    cells,
                    t,
                )


def test_outlet_pressure_solve_converges_from_any_reasonable_guess() -> None:
    """The shooting solve lands on the same injection pressure from a low, an exact and a high guess."""
    found = []
    for guess in (5e5, 4.844e6, 2e7):
        loop = _loop(Workflow(_load(_GROUPED, num_tsteps=1)))
        loop.mark_all_stale()
        loop.solve_for_outlet_pressure(Stream.fresh(h=100_000.0, P=guess, mass_rate=30.0), 7e6)
        assert loop.state.P_outlet.get_fresh() == pytest.approx(7e6, rel=1e-9)
        found.append(loop.state.P_inlet.get_fresh())
    assert found == pytest.approx([found[0]] * 3, rel=1e-9)


def test_grouped_template_delivers_target_extraction_pressure() -> None:
    """In a full run the production wellhead sits at target_extraction_pressure and the plant delivers the solved injection pressure."""
    cfg = _load(_GROUPED, num_tsteps=2)
    wf = Workflow(cfg)
    wf.run()
    loop = _loop(wf)
    surface = wf._orchestrator.components["surface"].history  # noqa: SLF001
    target = cfg["sim_config"]["target_extraction_pressure"]
    assert loop.history.P_outlet == pytest.approx([target, target], rel=1e-9)
    assert surface.P_outlet == pytest.approx(loop.history.P_inlet, abs=1_000.0)


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
