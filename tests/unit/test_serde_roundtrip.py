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
