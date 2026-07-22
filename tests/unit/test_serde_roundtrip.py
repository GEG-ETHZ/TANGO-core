"""Round-trip serialization/deserialization (serde) tests for tango_next
component state.

Verifies that ``LockedState[T]`` fields are transparent in the serialized
format and round-trip correctly through ``model_dump()`` →
``from_config(dump, skip_init=True)``:

- Serialized form contains raw values (no ``LockedState`` wrapper).
- Deserialized fields are ``LockedState`` instances, not plain floats.
- Values are preserved exactly.
- Deserialized status is fresh (matching fastsim TrackedState convention).
- Persistent scalar fields (e.g. ``energy_extracted``) survive the round-trip.
"""

from __future__ import annotations

import pytest

from tango_next.core.locked_state import LockedState
from tango_next.core.stream import Stream

# ---------------------------------------------------------------------------
# Shared config helpers
# ---------------------------------------------------------------------------

_WELL_FIELDS: dict[str, float] = {
    "thermal_gradient": 0.035,
    "well_length": 5000.0,
    "diameter": 0.2,
    "pipe_roughness": 5e-5,
}

_RESERVOIR_FIELDS: dict[str, float] = {
    "thermal_gradient": 0.035,
    "surface_temperature": 288.0,
    "rock_density": 2700.0,
    "rock_cp": 1000.0,
    "rock_k": 3.0,
    "dt_years": 1.0,
    "reservoir_depth": 5000.0,
    "thickness": 300.0,
    "porosity": 0.1,
    "permeability": 1e-14,
    "hydro_static_pressure": 50e6,
    "over_pressure_percentage": 10.0,
}


def _well_cfg(idx: int) -> dict:
    return dict(component_idx=idx, prev=idx - 1, next=idx + 1, **_WELL_FIELDS)


def _reservoir_cfg(idx: int) -> dict:
    return dict(component_idx=idx, prev=idx - 1, next=idx + 1, **_RESERVOIR_FIELDS)


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
    from tango_next.components.well.lumped import LumpedInjectionWell

    cfg = _well_cfg(1)
    well = LumpedInjectionWell.from_config(cfg)
    well.inlet = Stream(T=295.0, P=5e6, mass_rate=50.0, fluid_name="water")
    well.solve()

    T_out = well.state.T_outlet.get_fresh()
    P_out = well.state.P_outlet.get_fresh()

    dump = well.model_dump()

    # Serialized form: raw float, no wrapper
    assert isinstance(dump["state"]["T_outlet"], float)
    assert dump["state"]["T_outlet"] == pytest.approx(T_out)

    # Reconstruct
    well2 = LumpedInjectionWell.from_config(dump, skip_init=True)

    _assert_locked_float(well2.state.T_outlet, T_out, "T_outlet")
    _assert_locked_float(well2.state.P_outlet, P_out, "P_outlet")
    _assert_locked_float(well2.state.T_inlet, well.state.T_inlet.get_fresh(), "T_inlet")


# ---------------------------------------------------------------------------
# LumpedProductionWell
# ---------------------------------------------------------------------------


def test_lumped_production_well_roundtrip() -> None:
    """State fields survive a model_dump / from_config round-trip as LockedState."""
    from tango_next.components.well.lumped import LumpedProductionWell

    cfg = _well_cfg(3)
    well = LumpedProductionWell.from_config(cfg)
    well.inlet = Stream(T=450.0, P=4e7, mass_rate=50.0, fluid_name="water")
    well.solve()

    T_out = well.state.T_outlet.get_fresh()
    P_out = well.state.P_outlet.get_fresh()

    dump = well.model_dump()
    assert isinstance(dump["state"]["T_outlet"], float)

    well2 = LumpedProductionWell.from_config(dump, skip_init=True)
    _assert_locked_float(well2.state.T_outlet, T_out, "T_outlet")
    _assert_locked_float(well2.state.P_outlet, P_out, "P_outlet")


# ---------------------------------------------------------------------------
# LumpedReservoir
# ---------------------------------------------------------------------------


def test_lumped_reservoir_roundtrip_values() -> None:
    """State values and energy_extracted survive the round-trip."""
    from tango_next.components.reservoir.lumped import LumpedReservoir

    cfg = _reservoir_cfg(2)
    res = LumpedReservoir.from_config(cfg)
    res.inlet = Stream(T=350.0, P=5.1e7, mass_rate=50.0, fluid_name="water")
    res.solve()

    T_out = res.state.T_outlet.get_fresh()
    P_out = res.state.P_outlet.get_fresh()
    psi = res.state.psi.get_fresh()
    energy = res.energy_extracted

    dump = res.model_dump()
    assert isinstance(dump["state"]["T_outlet"], float)
    assert dump["state"]["T_outlet"] == pytest.approx(T_out)

    res2 = LumpedReservoir.from_config(dump, skip_init=True)
    _assert_locked_float(res2.state.T_outlet, T_out, "T_outlet")
    _assert_locked_float(res2.state.P_outlet, P_out, "P_outlet")
    _assert_locked_float(res2.state.psi, psi, "psi")
    assert res2.energy_extracted == pytest.approx(energy)


def test_lumped_reservoir_roundtrip_multi_timestep() -> None:
    """energy_extracted accumulates correctly and round-trips after multiple steps."""
    from tango_next.components.reservoir.lumped import LumpedReservoir

    cfg = _reservoir_cfg(2)
    res = LumpedReservoir.from_config(cfg)

    for _ in range(3):
        res.inlet = Stream(T=350.0, P=5.1e7, mass_rate=50.0, fluid_name="water")
        res.solve()

    energy_before = res.energy_extracted
    dump = res.model_dump()
    res2 = LumpedReservoir.from_config(dump, skip_init=True)
    assert res2.energy_extracted == pytest.approx(energy_before)


# ---------------------------------------------------------------------------
# LockedState generic type: list[float]
# ---------------------------------------------------------------------------


def test_numerical_well_cell_arrays_roundtrip() -> None:
    """LockedState[list[float]] fields (cell arrays) also round-trip correctly."""
    from tango_next.components.well.numerical import NumericalInjectionWell

    cfg = dict(
        component_idx=1,
        prev=0,
        next=2,
        num_cells=10,
        fluid_name="water",
        surface_temperature=288.0,
        rock_density=2700.0,
        rock_cp=1000.0,
        rock_k=3.0,
        dt_years=1.0,
        **_WELL_FIELDS,
    )
    well = NumericalInjectionWell.from_config(cfg)
    well.inlet = Stream(T=295.0, P=5e6, mass_rate=50.0, fluid_name="water")
    well.solve()

    T_cells = well.state.T_cells.get_fresh()
    P_cells = well.state.P_cells.get_fresh()

    dump = well.model_dump()

    # Serialized form: plain list, no wrapper
    assert isinstance(dump["state"]["T_cells"], list)
    assert len(dump["state"]["T_cells"]) == 10

    well2 = NumericalInjectionWell.from_config(dump, skip_init=True)

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
        "surface_temperature": 288.15,
        "surface_pressure": 101325.0,
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
    a model_dump / from_config(skip_init=True) round-trip.

    Matches the convention used above for wells/reservoir — this only checks
    that Pydantic-declared fields serialize correctly, NOT that the restored
    object can solve() again (GraphSurface's TESPy network lives in private,
    non-serialized attributes rebuilt by init() — see the next test for that).
    """
    from tango_next.components.surface.graph import GraphSurface

    surface = GraphSurface.from_config(_graph_surface_cfg())
    surface.inlet = Stream(mass_rate=50.0, P=8.5e6, T=423.15, fluid_name="water")
    surface.solve()
    surface.record(0)

    T_out = surface.state.T_outlet.get_fresh()
    net_thermal = surface.state.net_thermal_W.get_fresh()
    node_detail = dict(surface.state.node_detail)

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

    surface2 = GraphSurface.from_config(dump, skip_init=True)
    _assert_locked_float(surface2.state.T_outlet, T_out, "T_outlet")
    _assert_locked_float(surface2.state.net_thermal_W, net_thermal, "net_thermal_W")
    assert surface2.state.node_detail == node_detail
    assert surface2.history.node_history == surface.history.node_history


def test_graph_surface_roundtrip_then_resolve() -> None:
    """After a full round-trip WITH init() (not skip_init), the restored
    component can solve() again — proves the TESPy network (private,
    non-serialized attributes) is correctly rebuilt from the serialized
    power_plant dict alone, not silently relying on stale private state.
    """
    from tango_next.components.surface.graph import GraphSurface

    surface = GraphSurface.from_config(_graph_surface_cfg())
    surface.inlet = Stream(mass_rate=50.0, P=8.5e6, T=423.15, fluid_name="water")
    surface.solve()

    dump = surface.model_dump()

    # skip_init defaults to False -> init() runs -> TESPy network rebuilt.
    surface2 = GraphSurface.from_config(dump)
    surface2.inlet = Stream(mass_rate=45.0, P=8.5e6, T=423.15, fluid_name="water")
    surface2.solve()  # would raise (no _inlet_conn etc.) if init() hadn't rebuilt the network

    assert pytest.approx(323.15, abs=1e-6) == surface2.outlet.T  # fixed by T_out config
    assert pytest.approx(7.0e6) == surface2.outlet.P  # fixed by injection_pressure BC
    assert surface2.state.net_thermal_W.get_fresh() > 0
