"""Regression tests comparing tango_next against canonical src/tango results.

Reference: ``examples/flexible_SF_manual.yml`` run via the old tango ``Runner``
produces LCOE = 0.7740618821220107.  The equivalent tango_next input is
``examples/tango_next/flexible_SF_manual.yml``.

tango_next cannot yet compute LCOE — the economic component is Phase 2 work.
``test_lcoe_parity`` is marked xfail and will auto-promote when LCOE is wired.

When LCOE doesn't match, ``compare_against_old_tango`` provides a per-timestep
state snapshot from both systems so discrepancies can be traced to specific
components.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from tango_next.core.errors import CoolPropError, TangoNextError
from tango_next.workflows.workflow import Workflow

# ---------------------------------------------------------------------------
# Paths and reference values
# ---------------------------------------------------------------------------

EXAMPLES_DIR = Path(__file__).parents[2] / "examples"
OLD_SF_MANUAL = EXAMPLES_DIR / "flexible_SF_manual.yml"
NEW_SF_MANUAL = EXAMPLES_DIR / "tango_next" / "flexible_SF_manual.yml"
NEW_AGS_DIRECT_HEAT = EXAMPLES_DIR / "tango_next" / "AGS_direct_heat.yml"

REFERENCE_LCOE = 0.7740618821220107
N_TSTEPS = 20  # sim_config.time.num_tsteps in the tango_next YAML


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_tango_next(path: Path) -> Workflow:
    wf = Workflow.from_file(path)
    wf.run()
    return wf


def _components(wf: Workflow) -> dict[str, Any]:
    return wf._orchestrator.components


# ---------------------------------------------------------------------------
# Smoke test — does it run at all?
# ---------------------------------------------------------------------------


def test_smoke() -> None:
    """tango_next runs flexible_SF_manual.yml to completion without raising."""
    wf = _run_tango_next(NEW_SF_MANUAL)
    # If we get here without exception, the circuit completed all 20 timesteps.
    assert wf._orchestrator.n_tsteps == N_TSTEPS


def test_ags_direct_heat_smoke() -> None:
    """tango_next runs the no-reservoir AGS direct-heat loop to completion.

    Covers the closed-loop topology (injection_well -> horizontal_well ->
    production_well -> surface -> back to injection_well, no reservoir) and
    the ``horizontal_well``/``numerical`` registry entry (the base
    ``NumericalWell`` used directly with ``angle_from_vert_deg: 90``).
    """
    wf = _run_tango_next(NEW_AGS_DIRECT_HEAT)
    surface = _components(wf)["surface"]

    # t=0 is a known cold-start transient (circuit seeded at surface_temperature
    # rather than the steady re-injection temperature — see SystemBCIteration's
    # _seed_circuit_inlet docstring), so check steady-state behavior from t=1 on.
    net_thermal_steady_state = surface.history.net_thermal_W[1:]
    assert all(q > 0 for q in net_thermal_steady_state), (
        "Direct-heat plant should deliver positive net thermal power once past "
        f"the t=0 cold-start transient: {net_thermal_steady_state}"
    )


# ---------------------------------------------------------------------------
# LCOE parity — xfail until Phase 2 economic component is implemented
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "tango_next has no economic component yet (Phase 2). "
        "Remove this marker once wf.lcoe (or equivalent) is wired. "
        "Reference: LCOE=0.7740618821220107 from examples/flexible_SF_manual.yml."
    ),
    strict=False,
)
def test_lcoe_parity(tmp_path: Path) -> None:
    """tango_next LCOE matches the canonical src/tango reference.

    Granular comparison helpers are in ``compare_against_old_tango()`` below.
    The reference value was obtained from the old Runner on
    ``examples/flexible_SF_manual.yml``::

        runner = Runner(OLD_SF_MANUAL, save_dir=tmp_path)
        runner.start()
        df = pd.read_csv(runner.tango.workflow.run_dir / "flexible_SF_manual.econ.csv")
        assert df["LCOE"].iloc[0] == pytest.approx(0.7740618821220107, abs=1e-6)
    """
    wf = _run_tango_next(NEW_SF_MANUAL)  # noqa: F841 — used by the commented-out assertions below
    # TODO (Phase 2): replace with real LCOE extraction once wired.
    # lcoe = wf._orchestrator.components["economic"].state.lcoe
    # assert lcoe == pytest.approx(REFERENCE_LCOE, rel=1e-3)
    raise NotImplementedError(
        "tango_next economic component not yet implemented. "
        "See GraphSurface / EconomicComponent Phase 2 TODOs.",
    )


# ---------------------------------------------------------------------------
# NumericalInjectionWell — spatial history and physics
# ---------------------------------------------------------------------------


def test_injection_well_heats_cold_fluid() -> None:
    """CoolProp-backed injection well heats the cold injected fluid as it descends."""
    wf = _run_tango_next(NEW_SF_MANUAL)
    well = _components(wf)["injection_well"]

    # Inlet: surface temperature + approach ≈ 295 K.
    # Outlet: somewhere between inlet and rock temperature at 5 km depth
    # (288 + 0.035 × 5000 = 463 K), depending on t_d and heat-loss model.
    assert well.state.T_outlet.get_fresh() > well.state.T_inlet.get_fresh(), (
        f"Injection well outlet T ({well.state.T_outlet.get_fresh():.1f} K) should exceed "
        f"inlet T ({well.state.T_inlet.get_fresh():.1f} K) — geothermal gradient heats downward flow"
    )
    assert well.state.T_outlet.get_fresh() > 295.0  # must exceed cold surface injection T


def test_injection_well_pressure_increases_downward() -> None:
    """Hydrostatic gain dominates friction loss — outlet P > inlet P for 5 km well."""
    wf = _run_tango_next(NEW_SF_MANUAL)
    well = _components(wf)["injection_well"]

    # Net hydrostatic ≈ 1000 kg/m³ × 9.81 m/s² × 5000 m ≈ 49 MPa; friction ≈ few MPa.
    assert well.state.P_outlet.get_fresh() > well.state.P_inlet.get_fresh(), (
        f"Injection well outlet P ({well.state.P_outlet.get_fresh() / 1e6:.2f} MPa) should exceed "
        f"inlet P ({well.state.P_inlet.get_fresh() / 1e6:.2f} MPa)"
    )


def test_injection_well_spatial_history_shape() -> None:
    """After N_TSTEPS solves, history lists each have exactly N_TSTEPS entries
    and each entry is a 1-D array of length num_cells (100).
    """
    wf = _run_tango_next(NEW_SF_MANUAL)
    well = _components(wf)["injection_well"]
    history = well.history
    assert history is not None, "history should be enabled by default (record_history=True)"

    num_cells = well.num_cells
    for attr in ("T_cells", "P_cells", "h_cells", "rho_cells", "mu_cells", "u_cells"):
        entries = getattr(history, attr)
        assert len(entries) == N_TSTEPS, f"history.{attr} has {len(entries)} entries, expected {N_TSTEPS}"
        for t, arr in enumerate(entries):
            assert len(arr) == num_cells, f"history.{attr}[{t}] len {len(arr)}, expected {num_cells}"


def test_injection_well_spatial_history_deepest_cell_hotter() -> None:
    """Deepest cell is hotter than the shallowest cell at every timestep.

    T_cells need not be strictly monotone: when injection T exceeds the
    shallow-rock temperature, the fluid loses heat near the surface before
    gaining it from hotter deep rock.  The invariant that must hold is that
    T[-1] > T[0] (deep end is hottest), since the reservoir at 5 km is
    well above any plausible injection temperature.
    """
    wf = _run_tango_next(NEW_SF_MANUAL)
    well = _components(wf)["injection_well"]
    history = well.history
    assert history is not None

    for t, T_vec in enumerate(history.T_cells):
        assert T_vec[-1] > T_vec[0], (
            f"T_cells at timestep {t}: deepest T ({T_vec[-1]:.2f} K) should exceed "
            f"shallowest T ({T_vec[0]:.2f} K)"
        )


def test_injection_well_spatial_history_monotone_P() -> None:
    """P_cells increases monotonically with depth: hydrostatic gain dominates friction."""
    wf = _run_tango_next(NEW_SF_MANUAL)
    well = _components(wf)["injection_well"]
    history = well.history
    assert history is not None

    for t, P_vec in enumerate(history.P_cells):
        diffs = np.diff(P_vec)
        assert np.all(diffs >= 0), (
            f"P_cells at timestep {t} is not non-decreasing with depth. "
            f"Min diff = {diffs.min():.2f} Pa at cell {diffs.argmin()}"
        )


def test_injection_well_t_d_advances() -> None:
    """Dimensionless time advances each timestep and is stored in history."""
    wf = _run_tango_next(NEW_SF_MANUAL)
    well = _components(wf)["injection_well"]
    history = well.history
    assert history is not None

    t_d_series = history.t_d
    assert len(t_d_series) == N_TSTEPS
    # t_d should be strictly increasing
    diffs = np.diff(t_d_series)
    assert np.all(diffs > 0), f"t_d is not strictly increasing: {t_d_series}"


# ---------------------------------------------------------------------------
# Reservoir
# ---------------------------------------------------------------------------


def test_reservoir_thermal_equilibration() -> None:
    """LumpedReservoir outlet T is bounded between injection inlet T and initial reservoir T.

    Thermal depletion causes T_outlet to fall below T_initial over time; it can
    never drop below the injection temperature or exceed the un-depleted geothermal T.
    """
    wf = _run_tango_next(NEW_SF_MANUAL)
    res = _components(wf)["reservoir"]

    T_initial = 288.0 + 0.035 * 5000.0  # 463 K
    T_inj = res.state.T_inlet.get_fresh()
    assert T_inj <= res.state.T_outlet.get_fresh() <= T_initial, (
        f"T_outlet={res.state.T_outlet.get_fresh():.1f} K not in [{T_inj:.1f}, {T_initial:.1f}] K"
    )


def test_reservoir_pressure_drop() -> None:
    """Darcy pressure drop: reservoir outlet P is below the overpressure target."""
    wf = _run_tango_next(NEW_SF_MANUAL)
    res = _components(wf)["reservoir"]

    # overpressure_target = hydro_static × (1 + op_pct/100) = 50e6 × 1.10 = 55 MPa
    overpressure_target = 50_000_000 * 1.10
    assert res.state.P_outlet.get_fresh() < overpressure_target
    assert res.state.P_outlet.get_fresh() > 0


# ---------------------------------------------------------------------------
# Surface
# ---------------------------------------------------------------------------


def test_surface_positive_net_power() -> None:
    """Surface plant produces positive net electrical power."""
    wf = _run_tango_next(NEW_SF_MANUAL)
    surface = _components(wf)["surface"]

    assert surface.state.net_power_W.get_fresh() > 0, (
        f"net_power_W = {surface.state.net_power_W.get_fresh():.3g} W — expected > 0"
    )


def test_surface_outlet_cooler_than_inlet() -> None:
    """Surface plant cools the brine: injection outlet T < production inlet T."""
    wf = _run_tango_next(NEW_SF_MANUAL)
    surface = _components(wf)["surface"]

    assert surface.state.T_outlet.get_fresh() < surface.state.T_inlet.get_fresh(), (
        f"Surface outlet T ({surface.state.T_outlet.get_fresh():.1f} K) should be below "
        f"inlet T ({surface.state.T_inlet.get_fresh():.1f} K)"
    )


# ---------------------------------------------------------------------------
# Error taxonomy — CoolProp failures should surface as CoolPropError
# ---------------------------------------------------------------------------


def test_coolprop_error_on_bad_state() -> None:
    """A physically invalid CoolProp query raises CoolPropError, not a bare exception."""
    from tango_next.core.fluid_state import FluidState

    with pytest.raises(CoolPropError):
        # Negative pressure is unphysical — CoolProp will raise internally
        FluidState.with_PT("H2O", P=-1.0, T=300.0)


def test_coolprop_error_is_tango_next_error() -> None:
    """CoolPropError inherits from TangoNextError — catchable at the base class."""
    from tango_next.core.fluid_state import FluidState

    with pytest.raises(TangoNextError):
        FluidState.with_PT("H2O", P=-1.0, T=300.0)


# ---------------------------------------------------------------------------
# Performance: sanity-check that the 20-timestep run finishes quickly
# ---------------------------------------------------------------------------


@pytest.mark.perf
def test_performance_20_timesteps() -> None:
    """Full 20-timestep run completes in under 60 s (NumericalInjectionWell + CoolProp).

    This is a soft upper bound — it will be tightened as Phase 2 physics
    are added so regressions are caught early.  Adjust the limit if the
    threshold proves too tight or too loose on CI hardware.
    """
    start = time.perf_counter()
    _run_tango_next(NEW_SF_MANUAL)
    elapsed = time.perf_counter() - start

    assert elapsed < 60.0, (
        f"20-timestep run took {elapsed:.1f} s — exceeds 60 s soft limit. "
        "Check for CoolProp call overhead or accidental O(n²) behaviour."
    )


# ---------------------------------------------------------------------------
# Granular comparison helper — call manually when LCOE doesn't match
# ---------------------------------------------------------------------------


def compare_against_old_tango(tmp_path: Path) -> dict[str, Any]:
    """Run both old tango and tango_next, return a side-by-side state snapshot.

    Not a pytest test — call this directly for diagnostic work when
    ``test_lcoe_parity`` fails and you need to trace the discrepancy::

        tmp = Path("/tmp/tango_compare")
        tmp.mkdir(exist_ok=True)
        result = compare_against_old_tango(tmp)
        for key, val in result.items():
            print(key, val)

    Returns a dict with keys:
      ``old_lcoe``          — LCOE from old tango ($/kWh)
      ``tango_next_power_W``   — net_power_W from tango_next surface (last timestep)
      ``tango_next_thermal_W`` — net_thermal_W from tango_next surface (last timestep;
                                 0 for an electricity-product config like this one —
                                 reported for completeness, not because this comparison
                                 pair is heat-product)
      ``inj_T_outlet``      — injection well outlet T (K) from tango_next (last timestep)
      ``res_T_outlet``      — reservoir outlet T (K) from tango_next (last timestep)
      ``prod_T_outlet``     — production well outlet T (K) from tango_next (last timestep)
      ``inj_T_cells_last``  — full axial T profile of injection well (last timestep)
    """
    import pandas as pd

    from tango.runner import Runner  # old tango

    runner = Runner(OLD_SF_MANUAL, save_dir=tmp_path / "old")
    runner.start()
    econ_file = runner.tango.workflow.run_dir / "flexible_SF_manual.econ.csv"
    old_lcoe = pd.read_csv(econ_file)["LCOE"].iloc[0]

    wf = _run_tango_next(NEW_SF_MANUAL)
    c = _components(wf)
    surface = c.get("surface")
    inj = c.get("injection_well")
    res = c.get("reservoir")
    prod = c.get("production_well_lower")

    return {
        "old_lcoe": old_lcoe,
        "reference_lcoe": REFERENCE_LCOE,
        "tango_next_power_W": surface.state.net_power_W.get_fresh() if surface else None,
        "tango_next_thermal_W": surface.state.net_thermal_W.get_fresh() if surface else None,
        "inj_T_inlet_K": inj.state.T_inlet.get_fresh() if inj else None,
        "inj_T_outlet_K": inj.state.T_outlet.get_fresh() if inj else None,
        "inj_P_outlet_Pa": inj.state.P_outlet.get_fresh() if inj else None,
        "inj_T_cells_last": inj.history.T_cells[-1] if (inj and inj.history) else None,
        "inj_P_cells_last": inj.history.P_cells[-1] if (inj and inj.history) else None,
        "res_T_outlet_K": res.state.T_outlet.get_fresh() if res else None,
        "res_P_outlet_Pa": res.state.P_outlet.get_fresh() if res else None,
        "prod_T_outlet_K": prod.state.T_outlet.get_fresh() if prod else None,
        "prod_P_outlet_Pa": prod.state.P_outlet.get_fresh() if prod else None,
    }
