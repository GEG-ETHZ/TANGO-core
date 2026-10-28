# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Round-trip serialization/deserialization (serde) tests for tango
component state.

Verifies that ``LockedState[T]`` fields are transparent in the serialized
format and round-trip correctly through ``model_dump()`` →
``from_dict(dump, skip_init=True)``:

- Serialized form contains raw values (no ``LockedState`` wrapper).
- Deserialized fields are ``LockedState`` instances, not plain floats.
- Values are preserved exactly.
- Deserialized status is fresh (readable immediately, same as any
  newly-constructed ``LockedState``).
- Persistent accumulator fields (e.g. ``energy_extracted``) survive the
  round-trip too, same as any other ``LockedState`` field.
"""

from __future__ import annotations

import pytest

from tango_core.core.fluid_state import COOLPROP_BACKEND, FluidState
from tango_core.core.locked_state import LockedState
from tango_core.core.stream import Stream

# ---------------------------------------------------------------------------
# Shared config helpers
# ---------------------------------------------------------------------------

# Common is shared by reference across every component that declares a
# `common` field (see core/specs.py) — each _*_cfg() helper below passes its
# own dict() copy so tests never accidentally share (and couldn't anyway,
# since Common is frozen and Pydantic constructs its own instance from
# whatever dict content it's given, not a reference to the input dict).
_COMMON_FIELDS: dict[str, float | str] = {
    "fluid_name": "water",
    "rock_density": 2700.0,
    "rock_cp": 1000.0,
    "rock_k": 3.0,
    "thermal_gradient": 0.035,
    "surface_temperature": 288.0,
    "surface_pressure": 101325.0,
}


def _inlet_at(T: float, P: float, mass_rate: float) -> Stream:
    """An inlet ``Stream`` at a readable (T, P), converted to the stream's enthalpy with this file's fluid."""
    h = FluidState.with_PT(
        str(_COMMON_FIELDS["fluid_name"]),
        P,
        T,
        str(_COMMON_FIELDS.get("coolprop_backend", COOLPROP_BACKEND)),
    ).H
    return Stream.fresh(h=h, P=P, mass_rate=mass_rate)


_WELL_FIELDS: dict[str, float] = {
    "well_length": 5000.0,
    "diameter": 0.2,
    "pipe_roughness": 5e-5,
}

_RESERVOIR_FIELDS: dict[str, float] = {
    "dt_years": 1.0,
    "reservoir_depth": 5000.0,
    "thickness": 300.0,
    "porosity": 0.1,
    "permeability": 1e-14,
    "hydro_static_pressure": 50e6,
    "over_pressure_percentage": 10.0,
    "well_pattern": "DOUBLET",
}


def _well_cfg(idx: int) -> dict:
    return dict(component_idx=idx, prev=idx - 1, next=idx + 1, common=dict(_COMMON_FIELDS), **_WELL_FIELDS)


def _reservoir_cfg(idx: int) -> dict:
    return dict(
        component_idx=idx,
        prev=idx - 1,
        next=idx + 1,
        common=dict(_COMMON_FIELDS),
        **_RESERVOIR_FIELDS,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_locked_float(field: object, expected: float, name: str) -> None:
    """Assert ``field`` is a fresh LockedState[float] holding ``expected``."""
    assert isinstance(field, LockedState), f"{name}: expected LockedState, got {type(field).__name__}"
    assert field.is_fresh(), f"{name}: expected fresh after round-trip"
    assert field.get_fresh() == pytest.approx(expected), f"{name}: value mismatch after round-trip"


# ---------------------------------------------------------------------------
# LumpedInjectionWell
# ---------------------------------------------------------------------------


def test_lumped_injection_well_roundtrip() -> None:
    """State fields survive a model_dump / from_config round-trip as LockedState."""
    from tango_core.components.well.lumped import LumpedInjectionWell

    cfg = _well_cfg(1)
    well = LumpedInjectionWell.from_dict(cfg)
    well.solve(_inlet_at(295.0, 5e6, 50.0))

    T_out = well.state.T_outlet.get_fresh()
    P_out = well.state.P_outlet.get_fresh()

    dump = well.model_dump()

    # Serialized form: raw float, no wrapper
    assert isinstance(dump["state"]["T_outlet"], float)
    assert dump["state"]["T_outlet"] == pytest.approx(T_out)

    # Reconstruct
    well2 = LumpedInjectionWell.from_dict(dump, skip_init=True)

    _assert_locked_float(well2.state.T_outlet, T_out, "T_outlet")
    _assert_locked_float(well2.state.P_outlet, P_out, "P_outlet")
    _assert_locked_float(well2.state.T_inlet, well.state.T_inlet.get_fresh(), "T_inlet")


# ---------------------------------------------------------------------------
# LumpedProductionWell
# ---------------------------------------------------------------------------


def test_lumped_production_well_roundtrip() -> None:
    """State fields survive a model_dump / from_config round-trip as LockedState."""
    from tango_core.components.well.lumped import LumpedProductionWell

    cfg = _well_cfg(3)
    well = LumpedProductionWell.from_dict(cfg)
    # 600 bar bottom-hole: a 5000 m water column alone needs ~450 bar to lift itself
    well.solve(_inlet_at(450.0, 6e7, 50.0))

    T_out = well.state.T_outlet.get_fresh()
    P_out = well.state.P_outlet.get_fresh()

    dump = well.model_dump()
    assert isinstance(dump["state"]["T_outlet"], float)

    well2 = LumpedProductionWell.from_dict(dump, skip_init=True)
    _assert_locked_float(well2.state.T_outlet, T_out, "T_outlet")
    _assert_locked_float(well2.state.P_outlet, P_out, "P_outlet")


# ---------------------------------------------------------------------------
# LumpedReservoir
# ---------------------------------------------------------------------------


def test_lumped_reservoir_roundtrip_values() -> None:
    """State values and energy_extracted survive the round-trip."""
    from tango_core.components.reservoir.lumped import LumpedReservoir

    cfg = _reservoir_cfg(2)
    res = LumpedReservoir.from_dict(cfg)
    res.solve(_inlet_at(350.0, 5.1e7, 50.0))

    T_out = res.state.T_outlet.get_fresh()
    P_out = res.state.P_outlet.get_fresh()
    psi = res.state.psi.get_fresh()
    energy = res.state.energy_extracted.get_fresh()

    dump = res.model_dump()
    assert isinstance(dump["state"]["T_outlet"], float)
    assert dump["state"]["T_outlet"] == pytest.approx(T_out)
    assert isinstance(dump["state"]["energy_extracted"], float)

    res2 = LumpedReservoir.from_dict(dump, skip_init=True)
    _assert_locked_float(res2.state.T_outlet, T_out, "T_outlet")
    _assert_locked_float(res2.state.P_outlet, P_out, "P_outlet")
    _assert_locked_float(res2.state.psi, psi, "psi")
    _assert_locked_float(res2.state.energy_extracted, energy, "energy_extracted")


def test_lumped_reservoir_roundtrip_multi_timestep() -> None:
    """energy_extracted accumulates correctly and round-trips after multiple steps."""
    from tango_core.components.reservoir.lumped import LumpedReservoir

    cfg = _reservoir_cfg(2)
    res = LumpedReservoir.from_dict(cfg)

    for i in range(3):
        if i > 0:
            res.mark_all_stale()
        res.solve(_inlet_at(350.0, 5.1e7, 50.0))

    energy_before = res.state.energy_extracted.get_fresh()
    dump = res.model_dump()
    res2 = LumpedReservoir.from_dict(dump, skip_init=True)
    assert res2.state.energy_extracted.get_fresh() == pytest.approx(energy_before)


# ---------------------------------------------------------------------------
# LockedState generic type: list[float]
# ---------------------------------------------------------------------------


def test_numerical_well_cell_arrays_roundtrip() -> None:
    """LockedState[list[float]] fields (cell arrays) also round-trip correctly."""
    from tango_core.components.well.numerical import NumericalInjectionWell

    cfg = dict(
        component_idx=1,
        prev=0,
        next=2,
        num_cells=10,
        common=dict(_COMMON_FIELDS),
        dt_years=1.0,
        **_WELL_FIELDS,
    )
    well = NumericalInjectionWell.from_dict(cfg)
    well.solve(_inlet_at(295.0, 5e6, 50.0))

    T_cells = well.state.T_cells.get_fresh()
    P_cells = well.state.P_cells.get_fresh()

    dump = well.model_dump()

    # Serialized form: plain list, no wrapper. num_cells + 1: one value per
    # axial NODE (num_cells cells have num_cells + 1 node values), not one
    # per cell.
    assert isinstance(dump["state"]["T_cells"], list)
    assert len(dump["state"]["T_cells"]) == 11

    well2 = NumericalInjectionWell.from_dict(dump, skip_init=True)

    assert isinstance(well2.state.T_cells, LockedState)
    assert well2.state.T_cells.is_fresh()
    assert well2.state.T_cells.get_fresh() == pytest.approx(T_cells)
    assert well2.state.P_cells.get_fresh() == pytest.approx(P_cells)


# ---------------------------------------------------------------------------
# GraphSurface
# ---------------------------------------------------------------------------

_DIRECT_HEAT_POWER_PLANT: dict = {
    "nodes": {
        "inlet": {"type": "Source"},
        "dh_hx": {"type": "SimpleHeatExchanger", "role": "net_thermal", "T_out": 323.15},
        "outlet": {"type": "Sink"},
    },
    "edges": {
        1: {"source": "inlet", "target": "dh_hx"},
        2: {"source": "dh_hx", "target": "outlet"},
    },
}


def _graph_surface_cfg() -> dict:
    return {
        "component_idx": 0,
        "prev": 0,
        "next": 1,
        "common": dict(_COMMON_FIELDS),
        "injection_pressure": 7.0e6,
        "pipe_diameter": 0.3,
        "pipe_roughness": 1e-5,
        "approach_temperature": 7.0,
        "target_extraction_pressure": 7.0e6,
        "well_spacing": 707.0,
        "power_plant": _DIRECT_HEAT_POWER_PLANT,
    }


def test_graph_surface_roundtrip_state_values() -> None:
    """State/history values (including node_detail/node_history dicts) survive
    a model_dump / from_dict(skip_init=True) round-trip.

    Matches the convention used above for wells/reservoir — this only checks
    that Pydantic-declared fields serialize correctly, NOT that the restored
    object can solve() again (GraphSurface's TESPy network lives in private,
    non-serialized attributes rebuilt by init() — see the next test for that).
    """
    from tango_core.components.surface.graph import GraphSurface

    surface = GraphSurface.from_dict(_graph_surface_cfg())
    surface.solve(_inlet_at(423.15, 8.5e6, 50.0))
    surface.record(0)

    T_out = surface.state.T_outlet.get_fresh()
    net_thermal = surface.state.net_thermal_W.get_fresh()
    node_detail = dict(surface.state.node_detail.get_fresh())

    dump = surface.model_dump()

    # Serialized form: raw values, no LockedState wrapper; plain dicts for
    # node_detail/node_history (no custom serializer needed — they're just
    # dict[str, dict[str, float | list[float]]]).
    assert isinstance(dump["state"]["T_outlet"], float)
    assert dump["state"]["T_outlet"] == pytest.approx(T_out)
    assert dump["state"]["node_detail"]["dh_hx"]["Q"] == pytest.approx(node_detail["dh_hx"]["Q"])
    assert dump["history"]["node_history"]["dh_hx"]["Q"] == pytest.approx(
        surface.history.node_history["dh_hx"]["Q"],
    )

    surface2 = GraphSurface.from_dict(dump, skip_init=True)
    _assert_locked_float(surface2.state.T_outlet, T_out, "T_outlet")
    _assert_locked_float(surface2.state.net_thermal_W, net_thermal, "net_thermal_W")
    assert surface2.state.node_detail.get_fresh() == node_detail
    assert surface2.history.node_history == surface.history.node_history


def test_graph_surface_roundtrip_then_resolve() -> None:
    """After a full round-trip WITH init() (not skip_init), the restored
    component can solve() again — proves the TESPy network (private,
    non-serialized attributes) is correctly rebuilt from the serialized
    power_plant dict alone, not silently relying on stale private state.
    """
    from tango_core.components.surface.graph import GraphSurface

    surface = GraphSurface.from_dict(_graph_surface_cfg())
    surface.solve(_inlet_at(423.15, 8.5e6, 50.0))

    dump = surface.model_dump()

    # skip_init defaults to False -> init() runs -> TESPy network rebuilt.
    surface2 = GraphSurface.from_dict(dump)
    # dump captured surface's already-solved (fresh) state, so surface2's
    # restored state starts fresh too — mark it stale first, exactly like
    # the orchestrator would immediately before each solve().
    surface2.mark_all_stale()
    # would raise (no _inlet_conn etc.) if init() hadn't rebuilt the network
    surface2.solve(_inlet_at(423.15, 8.5e6, 45.0))

    assert pytest.approx(323.15, abs=1e-6) == surface2.state.T_outlet.get_fresh()  # fixed by T_out config
    assert pytest.approx(7.0e6) == surface2.outlet.P.get_fresh()  # fixed by injection_pressure BC
    assert surface2.state.net_thermal_W.get_fresh() > 0
