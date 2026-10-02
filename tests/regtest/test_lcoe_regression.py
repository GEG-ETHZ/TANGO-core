"""Regression tests for tango's economic-component behavior.

``hydro_sf_electric.yml``'s own golden-LCOE regression check lives in
``test_example_configs.py`` alongside every other ``example_configs/``
YAML's, not here -- this file owns the rest of its coverage instead:
detailed injection-well/reservoir/surface physics invariants
(spatial history shape, per-cell monotonicity, ``t_d`` advancement, ...)
that are specific to this config's own topology and go well beyond the
generic checks ``test_example_configs.py`` applies to every config.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from tango.core import fluid_utils
from tango.core.errors import (
    ConfigError,
    CoolPropError,
    FrackingViolationError,
    InvalidPowerStateError,
    TangoError,
)
from tango.workflows.workflow import Workflow

# ---------------------------------------------------------------------------
# Paths and reference values
# ---------------------------------------------------------------------------

EXAMPLE_CONFIGS_DIR = Path(__file__).parents[2] / "example_configs"
HYDRO_SF_ELECTRIC = EXAMPLE_CONFIGS_DIR / "hydro_sf_electric.yml"
AGS_DIRECT_HEAT = EXAMPLE_CONFIGS_DIR / "AGS_direct_heat.yml"

N_TSTEPS = 20  # sim_config.time.num_tsteps in the tango YAML

N_TSTEPS_FAST = 8
"""Timestep cap for structural/qualitative checks below (monotonicity, sign,
shape — NOT precise numeric goldens) — these don't care how many years the
run covers, so there's no reason to pay for the full N_TSTEPS run. Tests
that DO assert precise numeric values against a full-length reference are
marked @pytest.mark.slow and left at the real N_TSTEPS instead — see
pytest.ini for why perf/slow are deselected by default."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_tango(path: Path, num_tsteps: int | None = None) -> Workflow:
    """Run the given config. ``num_tsteps``, if given, overrides
    ``sim_config.num_tsteps`` (e.g. ``N_TSTEPS_FAST``) without touching the
    YAML file on disk — other callers/examples using the same file are
    unaffected.
    """
    if num_tsteps is None:
        wf = Workflow.from_file(path)
    else:
        cfg = yaml.safe_load(Path(path).read_text())
        cfg["sim_config"]["num_tsteps"] = num_tsteps
        wf = Workflow(cfg)
    wf.run()
    return wf


def _components(wf: Workflow) -> dict[str, Any]:
    return wf._orchestrator.components


# ---------------------------------------------------------------------------
# Workflow (de)serialization round-trips — from_file/from_str/to_file/to_str/to_config
# ---------------------------------------------------------------------------


def test_workflow_to_dict_reflects_source_yaml_inputs() -> None:
    """to_dict() carries through the user-authored input values.

    NOT a strict equality check against the raw source file: to_dict() is
    reconstructed from live component state (see Workflow's class
    docstring), which also includes derived/computed fields (e.g.
    NumericalWell's T_r, cell_length — computed by init(), never present
    in hand-authored YAML) that the original file never had. Checking a
    representative sample of real input values is the meaningful
    invariant here; test_workflow_from_str_to_str_roundtrip below is what
    actually proves full round-trip fidelity.
    """
    with HYDRO_SF_ELECTRIC.open() as f:
        original = yaml.safe_load(f)

    wf = Workflow.from_file(HYDRO_SF_ELECTRIC)
    dumped = wf.to_dict()

    assert dumped["common"]["rock_k"] == original["common"]["rock_k"]
    assert dumped["common"]["fluid_name"] == original["common"]["fluid_name"]
    assert dumped["sim_config"]["num_tsteps"] == original["sim_config"]["num_tsteps"]
    assert (
        dumped["components"]["injection_well"]["well_length"]
        == original["components"]["injection_well"]["well_length"]
    )


def test_workflow_to_config_is_a_fresh_copy_each_call() -> None:
    """to_dict() never returns a shared reference — mutating one call's result
    must not affect the Workflow or any other to_dict() call.
    """
    wf = Workflow.from_file(HYDRO_SF_ELECTRIC)

    cfg_a = wf.to_dict()
    cfg_a["common"]["rock_k"] = -1.0

    cfg_b = wf.to_dict()
    assert cfg_b["common"]["rock_k"] != -1.0
    assert cfg_a is not cfg_b


def test_workflow_from_str_to_str_roundtrip() -> None:
    """to_str() -> from_str() reproduces byte-identical YAML output.

    Compares the two YAML STRINGS, not the parsed dicts: pre-solve state
    fields default to LockedState's "not yet computed" sentinel
    (float('nan')), and NaN != NaN under plain ==, which would make a
    dict-equality comparison spuriously fail even when both sides hold the
    identical (still-unsolved) sentinel. YAML's `.nan` tag serializes
    identically either way, so a string comparison sidesteps the issue at
    the root — no need to run() first just to dodge NaN semantics.
    """
    wf = Workflow.from_file(HYDRO_SF_ELECTRIC)
    wf2 = Workflow.from_str(wf.to_str())
    assert wf2.to_str() == wf.to_str()


def test_workflow_to_file_from_file_roundtrip(tmp_path: Path) -> None:
    """to_file() -> from_file() on a temp path reproduces byte-identical YAML output.

    See test_workflow_from_str_to_str_roundtrip's docstring for why this
    compares serialized strings rather than parsed dicts (NaN != NaN).
    """
    wf = Workflow.from_file(HYDRO_SF_ELECTRIC)

    out = tmp_path / "roundtrip.yml"
    wf.to_file(out)
    wf2 = Workflow.from_file(out)

    assert wf2.to_str() == wf.to_str()


def test_workflow_to_dict_roundtrips_ags_power_plant_graph_structure() -> None:
    """``power_plant.nodes``/``edges`` survive a to_dict() -> Workflow() round-trip.

    Specifically exercises ``AGS_direct_heat.yml``'s ``circulation_control``
    (``PumpOrValve``, no ``p_out`` of its own, giving the AGS closed loop
    its real circulation device -- see
    ``docs/bugs-fixed-in-tango.md``'s "AGS closed loop has no pump
    anywhere" entry) and ``dh_hx``'s ``pressure_ratio``. Not just a smoke
    check that the values are present: rebuilds a second ``Workflow``
    from the dumped dict and confirms its own re-dump is byte-for-byte
    identical, proving the structure is genuinely reconstructible, not
    merely echoed back once.
    """
    wf = Workflow.from_file(AGS_DIRECT_HEAT)
    wf.run()
    dumped = wf.to_dict()

    nodes = dumped["components"]["surface"]["power_plant"]["nodes"]
    assert nodes["circulation_control"] == {
        "type": "PumpOrValve",
        "role": "net_electric",
        "efficiency": 1.0,
    }
    assert nodes["dh_hx"]["pressure_ratio"] == 0.99
    assert "p_out_megapascals" not in nodes["circulation_control"], (
        "circulation_control must have no pressure target of its own -- injection_pressure "
        "already pins the network's outlet connection; a second target would over-determine "
        "it (see AGS_direct_heat.yml's circulation_control comment)."
    )

    wf2 = Workflow(dumped)
    assert wf2.to_dict() == dumped


def test_workflow_json_roundtrip() -> None:
    """A ``Workflow``'s config survives a REAL ``json.dumps``/``json.loads``
    round-trip, not just a plain-Python-dict copy.

    Uses ``AGS_direct_heat.yml`` specifically: its ``power_plant.edges``
    previously used bare integer YAML keys (``1:``, ``2:``, ...), which
    JSON cannot represent at all (JSON object keys are always strings) --
    ``json.dumps``/``json.loads`` silently coerced them to string keys,
    breaking exact round-trip fidelity even though nothing in
    ``GraphSurface`` ever reads those keys semantically (confirmed by
    inspection: every consumer iterates ``edge_cfgs.values()`` only, never
    the keys). Fixed at the source (2026-08-18) by quoting the edge keys
    in every example YAML, matching what ``GraphSurface``'s own
    ``edge_cfgs: dict[str, dict[str, Any]]`` type hint already claimed.
    This test is the regression guard for that fix actually holding.
    """
    wf = Workflow.from_file(AGS_DIRECT_HEAT)
    wf.run()
    dumped = wf.to_dict()

    json_str = json.dumps(dumped)
    reloaded = json.loads(json_str)

    wf2 = Workflow(reloaded)
    assert wf2.to_dict() == dumped


def test_workflow_sweep_pattern_does_not_mutate_base() -> None:
    """The documented sweep pattern (to_dict() per iteration) never mutates
    the base Workflow, and each derived Workflow actually gets its own value.
    """
    base_wf = Workflow.from_file(HYDRO_SF_ELECTRIC)
    original_rock_k = base_wf.to_dict()["common"]["rock_k"]

    built_values = []
    for rock_k in (original_rock_k + 1.0, original_rock_k + 2.0):
        cfg = base_wf.to_dict()
        cfg["common"]["rock_k"] = rock_k
        wf = Workflow(cfg)
        built_values.append(wf._orchestrator.components["reservoir"].common.rock_k)

    assert built_values == [original_rock_k + 1.0, original_rock_k + 2.0]
    assert base_wf.to_dict()["common"]["rock_k"] == original_rock_k


def test_workflow_to_dict_reflects_live_mutation_not_a_stale_cache() -> None:
    """to_dict() reconstructs from CURRENT live state every call — no cached
    "original config" that could silently drift from the real object.

    This is the exact bug an earlier version of Workflow had: to_dict()
    returned a deepcopy of self._config, the dict this Workflow happened to
    be constructed from, which never noticed later mutations to genuinely
    mutable fields (e.g. surface.injection_pressure, reassigned every
    SystemBCIteration pass). Mutating it directly here and confirming
    to_dict() picks it up immediately is the regression test for that.
    """
    wf = Workflow.from_file(HYDRO_SF_ELECTRIC)
    surface = wf._orchestrator.components["surface"]

    surface.injection_pressure = 9_999_999.0

    assert wf.to_dict()["components"]["surface"]["injection_pressure"] == 9_999_999.0


# ---------------------------------------------------------------------------
# Smoke test — does it run at all?
# ---------------------------------------------------------------------------


def test_smoke() -> None:
    """Tango runs hydro_sf_electric.yml to completion without raising."""
    wf = _run_tango(HYDRO_SF_ELECTRIC, num_tsteps=N_TSTEPS_FAST)
    # If we get here without exception, the circuit completed all N_TSTEPS_FAST timesteps.
    assert wf._orchestrator.n_tsteps == N_TSTEPS_FAST


def test_ags_direct_heat_smoke() -> None:
    """Tango runs the no-reservoir AGS direct-heat loop to completion.

    Covers the closed-loop topology (injection_well -> horizontal_well ->
    production_well -> surface -> back to injection_well, no reservoir) and
    the ``horizontal_well``/``numerical`` registry entry (the base
    ``NumericalWell`` used directly with ``angle_from_vert_deg: 90``).
    """
    wf = _run_tango(AGS_DIRECT_HEAT, num_tsteps=N_TSTEPS_FAST)
    surface = _components(wf)["surface"]

    # t=0 is a known cold-start transient (circuit seeded at surface_temperature
    # rather than the steady re-injection temperature — see SystemBCIteration's
    # _seed_circuit_inlet docstring), so check steady-state behavior from t=1 on.
    net_thermal_steady_state = surface.history.net_thermal_W[1:]
    assert all(q > 0 for q in net_thermal_steady_state), (
        "Direct-heat plant should deliver positive net thermal power once past "
        f"the t=0 cold-start transient: {net_thermal_steady_state}"
    )


def test_bare_valve_circulation_control_rejected_at_construction(
    ags_direct_heat_config: dict[str, Any],
) -> None:
    """A bare ``type: Valve`` circulation node (no ``PumpOrValve`` fallback) is rejected up front.

    ``workflows/workflow.py::_check_loop_has_pressure_source`` exists
    specifically to reject a closed loop with no mechanical
    pressure-adding device AND no active per-solve() check backing it up
    -- exactly this pattern: a passive Valve with nothing to fall back on
    if the loop's thermosiphon margin runs out (see
    ``docs/bugs-fixed-in-tango.md``'s "AGS closed loop has no pump
    anywhere" entry for the physical risk this prevents). ``type:
    PumpOrValve`` (this file's actual default -- see the auto-resolving
    tests below) is the sanctioned way to use a Valve here at all,
    precisely because it comes with that active check built in.
    """
    nodes = ags_direct_heat_config["components"]["surface"]["power_plant"]["nodes"]
    nodes["circulation_control"] = {"type": "Valve", "role": "net_electric"}

    with pytest.raises(ConfigError, match="no pressure-adding device"):
        Workflow(ags_direct_heat_config)


def test_compressor_circulation_control_rejects_design_that_only_needs_a_valve(
    ags_direct_heat_config: dict[str, Any],
) -> None:
    """A ``type: Compressor`` circulation node raises when it solves to negative power.

    Mirror image of the test above: at valve-sufficient parameters, a
    ``Compressor`` explicitly pinned at this node (opting OUT of the
    default ``PumpOrValve`` auto-fallback) has more driving pressure
    available than it needs to hit ``injection_pressure``, so TESPy's
    fixed-``p_out`` compressor equation solves to a negative ``P.val`` —
    "generating" power, which a real passive pump never does (see
    ``docs/bugs-fixed-in-tango.md``'s "AGS closed loop has no pump
    anywhere" entry for why this matters).
    """
    nodes = ags_direct_heat_config["components"]["surface"]["power_plant"]["nodes"]
    nodes["circulation_control"] = {"type": "Compressor", "role": "net_electric", "efficiency": 1.0}
    ags_direct_heat_config["sim_config"]["mass_rate"] = 10.0  # valve-sufficient -- see YAML comment
    ags_direct_heat_config["sim_config"]["num_tsteps"] = N_TSTEPS_FAST

    with pytest.raises(InvalidPowerStateError, match="negative.*Valve"):
        Workflow(ags_direct_heat_config).run()


def test_pump_or_valve_auto_resolves_to_valve_when_sufficient(
    ags_direct_heat_config: dict[str, Any],
) -> None:
    """A ``type: PumpOrValve`` node resolves to a passive Valve when one suffices.

    Default AGS_direct_heat.yml behavior (no explicit component choice
    needed) for the common (majority of the declared decision space)
    regime: GraphSurface builds both a Valve- and a Compressor-resolved
    network for this node and picks the Valve one since it's physically
    valid here -- no InvalidPowerStateError, and the resolved TESPy
    component is actually a Valve (has no ``P`` attribute), confirming
    the fallback never even engaged.
    """
    ags_direct_heat_config["sim_config"]["mass_rate"] = 10.0  # valve-sufficient -- see YAML comment
    ags_direct_heat_config["sim_config"]["num_tsteps"] = N_TSTEPS_FAST

    wf = Workflow(ags_direct_heat_config)
    wf.run()

    surface = _components(wf)["surface"]
    assert type(surface._nodes["circulation_control"]).__name__ == "Valve"  # noqa: SLF001


def test_pump_or_valve_auto_resolves_to_compressor_when_needed(
    ags_direct_heat_config: dict[str, Any],
) -> None:
    """A ``type: PumpOrValve`` node falls back to a real Compressor when the valve can't do it.

    Mirror image of the test above, for the ~22% regime that genuinely
    needs a real pump: GraphSurface tries the Valve-resolved network
    first, that leg raises ``InvalidPowerStateError`` internally (an
    unphysical required pressure rise), and ``solve()`` catches that and
    retries with the Compressor-resolved network -- transparently, with
    no exception escaping to the caller and no config change needed by
    the user. This is exactly the case
    ``docs/bugs-fixed-in-tango.md``'s AGS_direct_heat.yml default
    (``mass_rate: 30``) is deliberately left exercising.
    """
    ags_direct_heat_config["sim_config"]["mass_rate"] = 30.0  # needs a real pump -- see YAML comment
    ags_direct_heat_config["sim_config"]["num_tsteps"] = N_TSTEPS_FAST

    wf = Workflow(ags_direct_heat_config)
    wf.run()

    surface = _components(wf)["surface"]
    assert type(surface._nodes["circulation_control"]).__name__ == "Compressor"  # noqa: SLF001
    # net_power_W = sum(-P.val) over net_electric nodes (see module docstring's sign
    # convention), so a real pump genuinely consuming power gives a NEGATIVE net_power_W --
    # that's the correct, expected state here (a pure-consumer plant, no generator).
    assert all(p < 0 for p in surface.history.net_power_W), (
        "A real pump should be a genuine, consistent net consumer here, not the impossible "
        f"apparent-generation state this whole check exists to reject: {surface.history.net_power_W}"
    )


# ---------------------------------------------------------------------------
# NumericalInjectionWell — spatial history and physics
# ---------------------------------------------------------------------------


def test_injection_well_heats_cold_fluid() -> None:
    """CoolProp-backed injection well heats the cold injected fluid as it descends."""
    wf = _run_tango(HYDRO_SF_ELECTRIC)
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
    wf = _run_tango(HYDRO_SF_ELECTRIC)
    well = _components(wf)["injection_well"]

    # Net hydrostatic ≈ 1000 kg/m³ × 9.81 m/s² × 5000 m ≈ 49 MPa; friction ≈ few MPa.
    assert well.state.P_outlet.get_fresh() > well.state.P_inlet.get_fresh(), (
        f"Injection well outlet P ({well.state.P_outlet.get_fresh() / 1e6:.2f} MPa) should exceed "
        f"inlet P ({well.state.P_inlet.get_fresh() / 1e6:.2f} MPa)"
    )


def test_injection_well_spatial_history_shape() -> None:
    """After N_TSTEPS solves, history lists each have exactly N_TSTEPS entries
    and each entry is a 1-D array of length num_cells + 1 (101) — one value
    per axial NODE (node 0 = inlet, node num_cells = outlet), not one per
    cell (there are num_cells cells, but num_cells + 1 node values along
    the well's axis).
    """
    wf = _run_tango(HYDRO_SF_ELECTRIC)
    well = _components(wf)["injection_well"]
    history = well.history
    assert history is not None, "history should be enabled by default (record_history=True)"

    num_nodes = well.num_cells + 1
    for attr in ("T_cells", "P_cells", "h_cells", "rho_cells", "mu_cells", "u_cells"):
        entries = getattr(history, attr)
        assert len(entries) == N_TSTEPS, f"history.{attr} has {len(entries)} entries, expected {N_TSTEPS}"
        for t, arr in enumerate(entries):
            assert len(arr) == num_nodes, f"history.{attr}[{t}] len {len(arr)}, expected {num_nodes}"


def test_injection_well_spatial_history_deepest_cell_hotter() -> None:
    """Deepest cell is hotter than the shallowest cell at every timestep.

    T_cells need not be strictly monotone: when injection T exceeds the
    shallow-rock temperature, the fluid loses heat near the surface before
    gaining it from hotter deep rock.  The invariant that must hold is that
    T[-1] > T[0] (deep end is hottest), since the reservoir at 5 km is
    well above any plausible injection temperature.
    """
    wf = _run_tango(HYDRO_SF_ELECTRIC)
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
    wf = _run_tango(HYDRO_SF_ELECTRIC)
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
    wf = _run_tango(HYDRO_SF_ELECTRIC)
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
    wf = _run_tango(HYDRO_SF_ELECTRIC)
    res = _components(wf)["reservoir"]

    T_initial = 288.0 + 0.035 * 5000.0  # 463 K
    T_inj = res.state.T_inlet.get_fresh()
    assert T_inj <= res.state.T_outlet.get_fresh() <= T_initial, (
        f"T_outlet={res.state.T_outlet.get_fresh():.1f} K not in [{T_inj:.1f}, {T_initial:.1f}] K"
    )


def test_reservoir_pressure_drop() -> None:
    """Darcy pressure drop: reservoir outlet P is below the overpressure target."""
    wf = _run_tango(HYDRO_SF_ELECTRIC)
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
    wf = _run_tango(HYDRO_SF_ELECTRIC)
    surface = _components(wf)["surface"]

    assert surface.state.net_power_W.get_fresh() > 0, (
        f"net_power_W = {surface.state.net_power_W.get_fresh():.3g} W — expected > 0"
    )


def test_surface_outlet_cooler_than_inlet() -> None:
    """Surface plant cools the brine: injection outlet T < production inlet T."""
    wf = _run_tango(HYDRO_SF_ELECTRIC)
    surface = _components(wf)["surface"]

    assert surface.state.T_outlet.get_fresh() < surface.state.T_inlet.get_fresh(), (
        f"Surface outlet T ({surface.state.T_outlet.get_fresh():.1f} K) should be below "
        f"inlet T ({surface.state.T_inlet.get_fresh():.1f} K)"
    )


# ---------------------------------------------------------------------------
# GraphSurface pressure-monotonicity validation
# ---------------------------------------------------------------------------


@pytest.fixture
def sf_manual_config() -> dict[str, Any]:
    """Fresh parsed dict of hydro_sf_electric.yml — safe for a test to mutate.

    Not specific to the pressure-monotonicity tests below — any test that
    wants a valid tango config to tweak before constructing a Workflow
    (without touching the file on disk) can depend on this fixture too.
    """
    with HYDRO_SF_ELECTRIC.open() as f:
        return yaml.safe_load(f)


@pytest.fixture
def ags_direct_heat_config() -> dict[str, Any]:
    """Fresh parsed dict of AGS_direct_heat.yml — safe for a test to mutate.

    A reservoir-less (closed-loop) topology — useful for tests that need to
    confirm behavior when there's no ``ReservoirComponent`` to find.
    """
    with AGS_DIRECT_HEAT.open() as f:
        return yaml.safe_load(f)


def test_pressure_monotonicity_passes_on_valid_config(sf_manual_config: dict[str, Any]) -> None:
    """hydro_sf_electric.yml's plant (valve 0.05 MPa -> turbine/condenser 0.005 MPa,
    monotonically decreasing) builds without GraphSurface's validation raising.
    """
    wf = Workflow(sf_manual_config)
    assert "surface" in _components(wf)


def test_pressure_monotonicity_rejects_rising_pressure(sf_manual_config: dict[str, Any]) -> None:
    """Bumping the turbine's p_out above the upstream valve's raises ConfigError.

    Mutates an already-parsed config dict (not the file on disk) to create a
    non-physical plant — pressure rising across a passive expansion device —
    then constructs a live Workflow from it and confirms GraphSurface's
    _validate_pressure_monotonicity catches it during init(), before any
    TESPy solve is attempted.
    """
    nodes = sf_manual_config["components"]["surface"]["power_plant"]["nodes"]
    valve_p_out = nodes["valve"]["p_out_megapascals"]
    nodes["turbine"]["p_out_megapascals"] = valve_p_out * 10  # now above upstream valve's p_out

    with pytest.raises(ConfigError, match="not monotonically decreasing"):
        Workflow(sf_manual_config)


# ---------------------------------------------------------------------------
# Shared-parameter provenance: structural (config-time) + frozen Common (runtime)
#
# rock_density/rock_cp/rock_k/thermal_gradient/surface_temperature/
# surface_pressure/fluid_name all live on ONE Common instance, shared BY
# REFERENCE (not copied) across every well, the reservoir, and the surface
# (see core/specs.py). Two things make divergence impossible rather than
# merely guarded against:
#   1. A component no longer declares these as its own fields at all (only
#      `common`) — its own YAML block setting e.g. `rock_k` is rejected as
#      an ordinary unknown-key error, the same as any other typo, not a
#      special-cased guard list.
#   2. Common itself is frozen (whole model) — even after a Workflow is
#      built, `well.common.rock_k = x` raises. Config-time validation alone
#      wouldn't catch code (e.g. a parameter-sweep script reusing live
#      objects across runs) that mutates a component's attribute directly
#      after construction — this closes that gap.
# ---------------------------------------------------------------------------


def test_component_own_block_rejects_shared_rock_param(sf_manual_config: dict[str, Any]) -> None:
    """A well's own YAML block setting rock_k raises ConfigError — it's not a
    field the well declares anymore (only `common` is), so it's rejected as
    an unknown key like any other typo.
    """
    common_rock_k = sf_manual_config["common"]["rock_k"]
    sf_manual_config["components"]["injection_well"]["rock_k"] = common_rock_k + 1.0

    with pytest.raises(ConfigError, match="rock_k"):
        Workflow(sf_manual_config)


def test_component_own_block_rejects_common_object(sf_manual_config: dict[str, Any]) -> None:
    """A component's own YAML block cannot set `common` directly either —
    it's always the single shared Workflow-level instance.
    """
    sf_manual_config["components"]["injection_well"]["common"] = {"rock_k": 1.0}

    with pytest.raises(ConfigError, match="common"):
        Workflow(sf_manual_config)


def test_components_share_one_common_instance_by_reference(sf_manual_config: dict[str, Any]) -> None:
    """Every component holding a `common` field gets the exact same object —
    not independent copies. Pydantic does not copy nested model fields on
    construction; this proves the built Workflow actually relies on that.
    """
    wf = Workflow(sf_manual_config)
    components = _components(wf)

    holders = [c for c in components.values() if hasattr(c, "common")]
    assert len(holders) >= 2, "expected at least 2 components (a well + the reservoir) to hold `common`"
    assert len({id(c.common) for c in holders}) == 1, "every component's `common` should be the SAME object"


def test_frozen_common_rejects_runtime_mutation(sf_manual_config: dict[str, Any]) -> None:
    """Mutating a live, already-built Workflow's shared Common instance raises
    — not just at config time.

    Construction-time validation alone wouldn't catch code (e.g. a
    parameter-sweep script reusing live objects across runs) that mutates
    the shared Common object directly after the Workflow is built. Because
    it's ONE shared instance, this single check protects every component
    that references it — not just the one you happened to touch. A
    genuinely-mutable field (surface.injection_pressure, which
    SystemBCIteration reassigns every BC-iteration pass) is untouched by it.
    """
    from pydantic import ValidationError

    wf = Workflow(sf_manual_config)
    components = _components(wf)

    with pytest.raises(ValidationError, match="frozen"):
        components["injection_well"].common.rock_k = 999.0
    with pytest.raises(ValidationError, match="frozen"):
        components["reservoir"].common.thermal_gradient = 0.5

    # A genuinely mutable field on the same component is unaffected.
    components["surface"].injection_pressure = 1.5e6
    assert components["surface"].injection_pressure == 1.5e6


def test_frozen_component_config_rejects_runtime_mutation(sf_manual_config: dict[str, Any]) -> None:
    """Component-local YAML config fields (not just `common`) reject live
    mutation too, mirroring the `Common` treatment above.

    Every field that is genuinely YAML config (set once at construction,
    never reassigned by init()/solve()/the orchestrator) is now
    `Field(frozen=True)` on each Component subclass. The only supported way
    to change one is the dict-modify-then-reinstantiate pattern
    (`Workflow.to_dict()` -> mutate the copy -> `Workflow(cfg)`), matching
    `applications/sweep_demo_AGS_direct_heat/sweep_demo_AGS_direct_heat.py`. Fields that are
    legitimately reassigned during simulation (`inlet`/`outlet`,
    `surface.injection_pressure`) must remain mutable — checked here too.
    """
    from pydantic import ValidationError

    wf = Workflow(sf_manual_config)
    components = _components(wf)

    with pytest.raises(ValidationError, match="frozen"):
        components["injection_well"].well_length = 9999.0
    with pytest.raises(ValidationError, match="frozen"):
        components["reservoir"].permeability = 1e-13
    with pytest.raises(ValidationError, match="frozen"):
        components["surface"].pipe_diameter = 1.0

    # Fields that are legitimately reassigned during simulation stay mutable.
    # `outlet` is LockedState-wrapped (like any `state` field) — write via
    # update(), not direct assignment (there's no `inlet` field at all
    # anymore; it's a solve() call parameter — see Component.solve()'s
    # docstring).
    components["injection_well"].outlet.h.update(1.2e5)
    assert components["injection_well"].outlet.h.get_fresh() == 1.2e5
    components["surface"].injection_pressure = 2.5e6
    assert components["surface"].injection_pressure == 2.5e6


# ---------------------------------------------------------------------------
# InjectionPolicy.MANUAL_FRACKING_CHECK — both violation pathways
# ---------------------------------------------------------------------------


def test_manual_fracking_check_raises_on_pressure_induced_violation(
    sf_manual_config: dict[str, Any],
) -> None:
    """Pushing the injection wellhead pressure high enough that the reservoir
    inlet lands above ``fluid_utils.target_reservoir_pressure()`` raises
    ``FrackingViolationError`` — full circuit run, no post-hoc mutation
    needed (unlike the flow-induced case below, a modest pressure bump
    doesn't push CoolProp/TESPy into an unrelated failure elsewhere).
    """
    sf_manual_config["sim_config"]["num_tsteps"] = 1
    sf_manual_config["sim_config"]["injection_mode"] = "manual-fracking-check"
    sf_manual_config["components"]["surface"]["injection_pressure"] = 8_000_000  # baseline: 2_000_000

    with pytest.raises(FrackingViolationError, match="Pressure-induced fracking"):
        Workflow(sf_manual_config).run()


def test_manual_fracking_check_raises_on_flow_induced_violation(
    sf_manual_config: dict[str, Any],
) -> None:
    """Exceeding ``fluid_utils.fracking_flow()``'s threshold mass rate raises
    ``FrackingViolationError``.

    Not exercised via a boosted ``sim_config.mass_rate`` + full ``run()``
    the way the pressure-induced case above is: at or even slightly below
    this config's own fracking threshold (~166 kg/s), the production side
    of the circuit is already numerically unstable (a downstream node's
    CoolProp state solve goes negative-pressure — confirmed across 18
    mass-rate/injection-pressure combinations, unrelated to fracking and
    not rescuable by raising injection pressure). See
    ``docs/tango_tasks.md``'s "Open items" entry "Production-side
    circuit numerically unstable near/above ~166 kg/s for
    `hydro_sf_electric.yml`" for the full investigation. Instead, this
    solves the circuit once at the nominal (safe) mass rate,
    then calls ``_check_fracking`` directly against a boosted
    ``orch.mass_rate`` — exercising the exact same comparison
    ``run_timestep`` makes, without going through a second, physically
    extreme TESPy/CoolProp solve.
    """
    sf_manual_config["sim_config"]["num_tsteps"] = 1
    sf_manual_config["sim_config"]["injection_mode"] = "manual-fracking-check"
    wf = Workflow(sf_manual_config)
    wf.run()

    orch = wf._orchestrator
    reservoir = orch._find_reservoir()
    inj_well = orch._by_idx[0]
    orch.mass_rate = 200.0  # baseline: 50 kg/s; threshold at this solved state is ~166 kg/s

    with pytest.raises(FrackingViolationError, match="Flow-induced fracking"):
        orch._check_fracking(reservoir, inj_well)


# ---------------------------------------------------------------------------
# InjectionPolicy.AUTO_PRESSURE — outer Newton loop on injection pressure
# ---------------------------------------------------------------------------


def test_auto_pressure_converges_to_fracking_threshold(sf_manual_config: dict[str, Any]) -> None:
    """AUTO_PRESSURE's outer Newton loop drives the reservoir inlet pressure to
    (approximately) ``fluid_utils.target_reservoir_pressure()`` — the whole
    point of the policy — within a few outer iterations, without raising.
    """
    sf_manual_config["sim_config"]["num_tsteps"] = 3
    sf_manual_config["sim_config"]["injection_mode"] = "auto-pressure"
    wf = Workflow(sf_manual_config)
    wf.run()

    orch = wf._orchestrator
    reservoir = orch._find_reservoir()
    inj_well = orch._by_idx[0]
    target_reservoir_P = fluid_utils.target_reservoir_pressure(
        reservoir.hydro_static_pressure,
        reservoir.over_pressure_percentage,
    )

    inj_outlet_P = inj_well.outlet.P.get_fresh()
    rel_error = abs(inj_outlet_P - target_reservoir_P) / target_reservoir_P
    assert rel_error < 1e-3, (
        f"inj_well.outlet.P ({inj_outlet_P:.6g} Pa) should have converged near "
        f"target_reservoir_P ({target_reservoir_P:.6g} Pa), rel_error={rel_error:.2e}"
    )


def test_auto_pressure_requires_reservoir(ags_direct_heat_config: dict[str, Any]) -> None:
    """AUTO_PRESSURE has no fracking-safety target to converge toward on a
    reservoir-less topology (e.g. AGS's closed loop) — raises ConfigError
    rather than silently doing nothing or crashing on a missing attribute.
    """
    ags_direct_heat_config["sim_config"]["injection_mode"] = "auto-pressure"

    with pytest.raises(ConfigError, match="requires a reservoir component"):
        Workflow(ags_direct_heat_config).run()


# ---------------------------------------------------------------------------
# InjectionPolicy.AUTO_FLOW — outer Picard loop on mass rate
# ---------------------------------------------------------------------------


def test_auto_flow_converges_to_capped_mass_rate(sf_manual_config: dict[str, Any]) -> None:
    """AUTO_FLOW's outer Picard loop converges mass_rate to ``max_mass_rate``
    when the cap sits below the reservoir's natural (uncapped)
    ``fracking_flow()`` threshold.

    Capped rather than left uncapped: this config's natural, uncapped
    fracking-flow threshold (~165 kg/s) sits right at the edge of a known,
    separately-documented production-side numerical instability that a cold
    solve can hit near/above ~166 kg/s (``docs/tango_tasks.md``). A
    generous cap well clear of that boundary keeps this test robust without
    depending on it.
    """
    sf_manual_config["sim_config"]["num_tsteps"] = 3
    sf_manual_config["sim_config"]["injection_mode"] = "auto-flow"
    sf_manual_config["sim_config"]["max_mass_rate"] = 100.0
    wf = Workflow(sf_manual_config)
    wf.run()

    orch = wf._orchestrator
    assert orch.mass_rate == pytest.approx(100.0)


def test_auto_flow_requires_reservoir(ags_direct_heat_config: dict[str, Any]) -> None:
    """AUTO_FLOW has no fracking-flow threshold to converge toward on a
    reservoir-less topology (e.g. AGS's closed loop) — raises ConfigError
    rather than silently doing nothing or crashing on a missing attribute.
    """
    ags_direct_heat_config["sim_config"]["injection_mode"] = "auto-flow"

    with pytest.raises(ConfigError, match="requires a reservoir component"):
        Workflow(ags_direct_heat_config).run()


def test_auto_flow_rejects_max_mass_rate_on_other_policies(sf_manual_config: dict[str, Any]) -> None:
    """``max_mass_rate`` is meaningless outside AUTO_FLOW/AUTO_BOTH — set
    alongside any other injection_mode, it raises ConfigError rather than
    being silently ignored.
    """
    sf_manual_config["sim_config"]["max_mass_rate"] = 100.0  # injection_mode stays manual-fracking-check

    with pytest.raises(ConfigError, match="only meaningful for AUTO_FLOW/AUTO_BOTH"):
        Workflow(sf_manual_config)


# ---------------------------------------------------------------------------
# Error taxonomy — CoolProp failures should surface as CoolPropError
# ---------------------------------------------------------------------------


def test_coolprop_error_on_bad_state() -> None:
    """A physically invalid CoolProp query raises CoolPropError, not a bare exception."""
    from tango.core.fluid_state import FluidState

    with pytest.raises(CoolPropError):
        # Negative pressure is unphysical — CoolProp will raise internally
        FluidState.with_PT("H2O", P=-1.0, T=300.0)


def test_coolprop_error_is_tango_error() -> None:
    """CoolPropError inherits from TangoError — catchable at the base class."""
    from tango.core.fluid_state import FluidState

    with pytest.raises(TangoError):
        FluidState.with_PT("H2O", P=-1.0, T=300.0)


# ---------------------------------------------------------------------------
# Performance: sanity-check that the 20-timestep run finishes quickly
# ---------------------------------------------------------------------------


@pytest.mark.perf
def test_performance_20_timesteps() -> None:
    """Full 20-timestep run completes in under 60 s (NumericalInjectionWell + CoolProp).

    This is a soft upper bound — it will be tightened as production-well
    physics gets more detailed (e.g. a spatially-resolved model replacing
    the current lumped one) so regressions are caught early.  Adjust the limit if the
    threshold proves too tight or too loose on CI hardware.
    """
    start = time.perf_counter()
    _run_tango(HYDRO_SF_ELECTRIC)
    elapsed = time.perf_counter() - start

    assert elapsed < 60.0, (
        f"20-timestep run took {elapsed:.1f} s — exceeds 60 s soft limit. "
        "Check for CoolProp call overhead or accidental O(n²) behaviour."
    )
