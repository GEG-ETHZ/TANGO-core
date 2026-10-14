"""Regression tests for ``phase_diagrams.write_phase_diagrams``.

Uses a reduced timestep count (fast) rather than any example config's own
full length -- this is about the file-writing/data-correctness mechanism,
not physics, so there's no reason to pay for a full-length run.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from CoolProp import CoolProp as CP

from tango import phase_diagrams
from tango.components.surface.graph import GraphSurface
from tango.core.errors import ConfigError
from tango.workflows.workflow import Workflow

# Frozen scenario copies of example configs; see test_lcoe_regression.py.
_EXAMPLE_CONFIGS_DIR = Path(__file__).parent / "fixtures" / "scenarios"
_N_TSTEPS_FAST = 3


def _run_fast(filename: str) -> Workflow:
    cfg = Workflow.from_file(_EXAMPLE_CONFIGS_DIR / filename).to_dict()
    cfg["sim_config"]["num_tsteps"] = _N_TSTEPS_FAST
    wf = Workflow(cfg)
    wf.run()
    return wf


def test_single_fluid_config_writes_one_file(tmp_path: Path) -> None:
    """A single-working-fluid config (Single-Flash, H2O) writes exactly one HTML file."""
    wf = _run_fast("hydro_sf_electric.yml")
    written = phase_diagrams.write_phase_diagrams(wf, tmp_path, "hydro_sf_electric")

    assert written == [tmp_path / "hydro_sf_electric.phase_H2O.html"]
    assert written[0].exists()


def test_binary_cycle_config_writes_one_file_per_fluid(tmp_path: Path) -> None:
    """A binary (ORC) config writes one HTML per fluid: the geofluid and the secondary fluid."""
    wf = _run_fast("hydro_ORC_electric.yml")
    written = phase_diagrams.write_phase_diagrams(wf, tmp_path, "hydro_ORC_electric")

    assert set(written) == {
        tmp_path / "hydro_ORC_electric.phase_H2O.html",
        tmp_path / "hydro_ORC_electric.phase_R245fa.html",
    }
    for path in written:
        assert path.exists()


def test_branching_node_records_each_outgoing_connection_separately() -> None:
    """A DropletSeparator's liquid and vapor branches get distinct, correct states.

    Regression guard: an earlier version of ``_collect_node_detail`` only
    ever recorded a node's FIRST outgoing connection (``next(c for c in
    conns if c.source is node)``), so a branching node's second (or later)
    branch silently reported the first branch's own state instead of its
    own -- found while building this module. The vapor branch (feeding the
    turbine) has a much higher specific enthalpy than the liquid branch
    (feeding the recirculation pump); if they matched, this would still be
    the bug.
    """
    wf = _run_fast("hydro_sf_electric.yml")
    surface = wf._orchestrator.components["surface"]  # noqa: SLF001
    assert isinstance(surface, GraphSurface)
    node_history = surface.history.node_history

    assert "separator:out1" in node_history
    assert "separator:out2" in node_history
    h_liquid = node_history["separator:out1"]["h"][-1]
    h_vapor = node_history["separator:out2"]["h"][-1]
    assert h_vapor > h_liquid * 2, (
        f"vapor-branch h ({h_vapor}) should be far larger than liquid-branch h "
        f"({h_liquid}) -- equal values would mean the branches are being conflated again"
    )


def test_splitting_node_with_unported_edge_connects_every_branch() -> None:
    """An edge with no ``target_port`` into a splitting node draws to EVERY branch.

    Regression guard: ``flash_valve -> separator`` has no ``target_port``
    in the YAML (``separator`` has a single inlet, so there's no
    real ambiguity in the TESPy topology). An earlier version of this
    lookup fell back to arbitrarily picking the splitting node's FIRST
    outgoing branch only, leaving the second branch (``:out2``, the vapor
    branch feeding the turbine) with no visible incoming connection at all
    -- it rendered as a disconnected terminal node (found via Chad's
    2026-09-26 screenshot).
    """
    wf = _run_fast("hydro_sf_electric.yml")
    surface = wf._orchestrator.components["surface"]  # noqa: SLF001
    assert isinstance(surface, GraphSurface)

    targets = phase_diagrams._target_history_keys(surface, "separator", None)  # noqa: SLF001

    assert set(targets) == {"separator:out1", "separator:out2"}


def test_fluid_groups_separates_geofluid_from_secondary_fluid() -> None:
    """A dual-fluid HeatExchanger's two sides are correctly attributed to different fluids."""
    wf = _run_fast("hydro_ORC_electric.yml")
    surface = wf._orchestrator.components["surface"]  # noqa: SLF001
    assert isinstance(surface, GraphSurface)

    groups = phase_diagrams._fluid_groups(surface)  # noqa: SLF001

    assert set(groups.keys()) == {"H2O", "R245fa"}
    assert "evaporator:out1" in groups["H2O"]
    assert "evaporator:out2" in groups["R245fa"]


def test_every_frame_pins_its_own_axis_range() -> None:
    """Every animation frame's OWN layout carries the fixed axis range, not just the base figure's.

    Regression guard: setting the fixed range/``autorange: False`` only on
    the base figure's layout was NOT enough -- Plotly.js's ``redraw: true``
    frame-transition path can recompute the axis range from scratch on a
    frame switch regardless of what the base layout says, reproducing the
    original 10^112-blowout bug on some slider positions but not others
    (Chad, 2026-09-28). Every frame must carry its own explicit,
    identical axis range for the fix to actually hold across the whole
    slider.
    """
    wf = _run_fast("hydro_sf_electric.yml")
    surface = wf._orchestrator.components["surface"]  # noqa: SLF001
    assert isinstance(surface, GraphSurface)
    groups = phase_diagrams._fluid_groups(surface)  # noqa: SLF001
    fluid_name, node_names = next(iter(groups.items()))

    fig = phase_diagrams._build_figure(wf, surface, fluid_name, node_names, wf._sim_config.dt_years)  # noqa: SLF001

    assert fig.frames
    for frame in fig.frames:
        assert frame.layout.xaxis.autorange is False
        assert frame.layout.yaxis.autorange is False
        assert frame.layout.xaxis.range == fig.layout.xaxis.range
        assert frame.layout.yaxis.range == fig.layout.yaxis.range


def test_two_phase_state_gets_its_own_color_not_the_gray_fallback() -> None:
    """A genuinely two-phase (wet) state is colored distinctly, not lumped into the gray fallback.

    Regression guard: wet states (a flash valve's outlet, a wet turbine's
    exhaust, a condenser's outlet, a saturated-liquid separator branch) are
    the NORMAL case for several node types in this domain, not a rare edge
    case -- Chad's original 3-color scheme (orange/blue/green) had no
    bucket for them, so they all silently fell back to an unstyled gray
    until a 4th color was added for ``iphase_twophase`` (2026-09-28).
    """
    wf = _run_fast("hydro_sf_electric.yml")
    surface = wf._orchestrator.components["surface"]  # noqa: SLF001
    assert isinstance(surface, GraphSurface)
    hist = surface.history.node_history["turbine"]
    h_kj = hist["h"][-1] * phase_diagrams.J_PER_KG_TO_KJ_PER_KG
    p_bar = hist["p"][-1] * phase_diagrams.PA_TO_BAR

    color = phase_diagrams._phase_color("H2O", h_kj, p_bar, surface.common.coolprop_backend)  # noqa: SLF001

    assert color != phase_diagrams._PHASE_COLOR_FALLBACK  # noqa: SLF001
    assert color == "red"


def test_no_graph_surface_writes_nothing(tmp_path: Path) -> None:
    """A Workflow with no GraphSurface component writes nothing (nothing to error on either)."""
    wf = _run_fast("hydro_sf_electric.yml")
    surface = wf._orchestrator.components.pop("surface")  # noqa: SLF001
    try:
        written = phase_diagrams.write_phase_diagrams(wf, tmp_path, "no_surface")
        assert written == []
    finally:
        wf._orchestrator.components["surface"] = surface  # noqa: SLF001


def _sf_figure(config: phase_diagrams.PropertyLineConfig | None = None) -> object:
    wf = _run_fast("hydro_sf_electric.yml")
    surface = wf._orchestrator.components["surface"]  # noqa: SLF001
    assert isinstance(surface, GraphSurface)
    fluid_name, node_names = next(iter(phase_diagrams._fluid_groups(surface).items()))  # noqa: SLF001
    return phase_diagrams._build_figure(  # noqa: SLF001
        wf,
        surface,
        fluid_name,
        node_names,
        wf._sim_config.dt_years,
        config,  # noqa: SLF001
    )


def test_frames_only_touch_edge_traces() -> None:
    """Frames name their trace indices explicitly and never touch the static traces.

    Regression guard: the base figure once had one more trace than each
    frame (the dome was added twice), so the last base trace -- the final
    year's ``outlet -> injection_well`` edge -- was never overwritten and
    stayed on screen as a stale copy on every other year.
    """
    fig = _sf_figure()
    n_static = len(fig.data) - len(fig.frames[0].data)
    for frame in fig.frames:
        assert list(frame.traces) == list(range(n_static, len(fig.data)))
        assert len(frame.data) == len(fig.data) - n_static
    static_groups = {trace.legendgroup for trace in fig.data[:n_static] if trace.legendgroup}
    assert static_groups == {"Isotherms (°C)", "Isentropes (kJ/kg·K)", "Isochores (kg/m³)", "Quality (x)"}


def test_explicit_reference_line_values_draw_one_line_each() -> None:
    """Explicit values draw exactly those lines; 0 turns a family off; one legend entry per family."""
    config = phase_diagrams.PropertyLineConfig(
        isotherm_temperatures_kelvin=(350.0, 450.0, 700.0),
        isentrope_entropies_kj_per_kg_kelvin=0,
        isochore_densities_kg_per_m3=(1.0, 1000.0),
        qualities=(0.5,),
    )
    fig = _sf_figure(config)
    lines: dict[str, list[object]] = {}
    for trace in fig.data:
        if trace.legendgroup and trace.mode == "lines":
            lines.setdefault(trace.legendgroup, []).append(trace)
    assert len(lines["Isotherms (°C)"]) == 3
    assert "Isentropes (kJ/kg·K)" not in lines
    assert len(lines["Isochores (kg/m³)"]) == 2
    assert len(lines["Quality (x)"]) == 1
    for traces in lines.values():
        assert sum(bool(t.showlegend) for t in traces) == 1


def test_subcritical_isotherm_is_flat_across_the_dome() -> None:
    """Below the critical temperature an isotherm crosses the dome at constant saturation pressure."""
    pressures = np.geomspace(1e3, 1e8, 100)
    h_vals, p_vals = phase_diagrams._isotherm("Water", "HEOS", 400.0, pressures)  # noqa: SLF001
    p_sat_bar = CP.PropsSI("P", "T", 400.0, "Q", 0, "Water") * phase_diagrams.PA_TO_BAR
    flat = [h for h, p in zip(h_vals, p_vals, strict=True) if p == pytest.approx(p_sat_bar)]
    assert len(flat) == 2
    assert flat[0] < flat[1]  # saturated liquid, then saturated vapor
    assert p_vals == sorted(p_vals, reverse=True)


def test_load_config_from_inline_string_and_file(tmp_path: Path) -> None:
    """The same YAML/JSON works inline or from a file; per-fluid overrides only replace given keys."""
    text = (
        "{isotherm_temperatures_kelvin: [300, 400], qualities: 2, fluids: {Isopentane: {qualities: [0.5]}}}"
    )
    inline = phase_diagrams.load_phase_diagram_config(text)
    config_file = tmp_path / "phase.yml"
    config_file.write_text(text)
    from_file = phase_diagrams.load_phase_diagram_config(str(config_file))
    assert inline == from_file
    assert inline.default.isotherm_temperatures_kelvin == (300.0, 400.0)
    assert inline.default.qualities == 2
    isopentane = inline.for_fluid("Isopentane")
    assert isopentane.qualities == (0.5,)
    assert isopentane.isotherm_temperatures_kelvin == (300.0, 400.0)
    assert inline.for_fluid("H2O") == inline.default


@pytest.mark.parametrize(
    "text",
    [
        "{isotherms: 5}",  # unknown key
        "{qualities: [0.5, 1.5]}",  # quality outside [0, 1]
        "{isochore_densities_kg_per_m3: [-1]}",  # non-positive density
        "{isotherm_temperatures_kelvin: -2}",  # negative count
        "{isotherm_temperatures_kelvin: true}",  # bool isn't a count
        "[1, 2]",  # not a mapping
        "{fluids: {H2O: {bogus: 1}}}",  # unknown key in a per-fluid override
    ],
)
def test_load_config_rejects_invalid_input(text: str) -> None:
    """Bad keys or values raise ConfigError before any simulation runs."""
    with pytest.raises(ConfigError):
        phase_diagrams.load_phase_diagram_config(text)


@pytest.mark.parametrize("backend", ["HEOS", "BICUBIC&HEOS"])
def test_isotherm_never_enters_the_dome_off_saturation(backend: str) -> None:
    """Off the saturation pressure an isotherm is liquid above it and vapor below it, never in between.

    Regression guard: with the tabular ``BICUBIC&HEOS`` backend, a 150 °C
    isotherm queried just below its saturation pressure came back at
    h = 2138 kJ/kg, inside the dome, drawing a spurious notch.
    """
    pressures = np.geomspace(1e4, 1e7, 150)
    h_vals, p_vals = phase_diagrams._isotherm("Water", backend, 423.15, pressures)  # noqa: SLF001
    h_liquid = CP.PropsSI("H", "T", 423.15, "Q", 0, "Water") / 1000
    h_vapor = CP.PropsSI("H", "T", 423.15, "Q", 1, "Water") / 1000
    p_sat_bar = CP.PropsSI("P", "T", 423.15, "Q", 0, "Water") * phase_diagrams.PA_TO_BAR
    margin = 0.01 * (h_vapor - h_liquid)
    for h, p in zip(h_vals, p_vals, strict=True):
        if p != pytest.approx(p_sat_bar):
            assert not h_liquid + margin < h < h_vapor - margin, (
                f"h={h:.1f} kJ/kg at P={p:.3f} bar is inside the dome"
            )


def test_round_numbered_line_values() -> None:
    """Count specs give round values; ties between round steps pick the step with more lines."""
    assert phase_diagrams._resolve_line_values(5, [-5.0, 4.0]) == [-4.0, -2.0, 0.0, 2.0, 4.0]  # noqa: SLF001
    assert phase_diagrams._resolve_line_values(5, [0.05, 1000.0], log=True) == [0.05, 0.6, 7.0, 80.0, 1000.0]  # noqa: SLF001
    assert phase_diagrams._resolve_line_values((1.5, 2.5), [0.0, 100.0]) == [1.5, 2.5]  # noqa: SLF001
    assert phase_diagrams._resolve_line_values(0, [0.0, 100.0]) == []  # noqa: SLF001


def test_surface_exit_point_is_the_recorded_state_into_outlet() -> None:
    """The loop's surface-exit point is the recorded state flowing into the ``outlet`` Sink.

    Regression guard: re-deriving it from the plant's outlet (T, P) with
    a tabular backend drifted 16 kJ/kg from the node feeding ``outlet``
    for near-critical CO2 (75 bar, ~31.7 degC).
    """
    wf = _run_fast("CO2_EGS_ORC_electric.yml")
    surface = wf._orchestrator.components["surface"]  # noqa: SLF001
    assert isinstance(surface, GraphSurface)
    h_kj: dict[str, list[float]] = {"circulation_control": [1.0, 2.0, 3.0]}
    p_bar: dict[str, list[float]] = {"circulation_control": [4.0, 5.0, 6.0]}
    phase_diagrams._add_subsurface_points(  # noqa: SLF001
        wf,
        surface,
        surface.common.coolprop_backend,
        _N_TSTEPS_FAST,
        h_kj,
        p_bar,
        {},
        {},
    )
    assert h_kj["outlet"] == h_kj["circulation_control"]
    assert p_bar["outlet"] == p_bar["circulation_control"]


def test_wells_are_drawn_as_their_marched_profiles() -> None:
    """A numerical well's edge follows its recorded per-node (h, P) profile, every year.

    It starts at the well's own first node, not the upstream point, so a
    state lost across the boundary shows as a gap rather than being bridged.
    """
    wf = _run_fast("CO2_EGS_ORC_electric.yml")
    surface = wf._orchestrator.components["surface"]  # noqa: SLF001
    assert isinstance(surface, GraphSurface)
    well = wf._orchestrator.components["injection_well"]  # noqa: SLF001
    fluid_name, node_names = next(iter(phase_diagrams._fluid_groups(surface).items()))  # noqa: SLF001
    fig = phase_diagrams._build_figure(wf, surface, fluid_name, node_names, wf._sim_config.dt_years)  # noqa: SLF001
    for t, frame in enumerate(fig.frames):
        trace = next(tr for tr in frame.data if tr.name == "outlet -> injection_well")
        assert list(trace.x) == pytest.approx([h / 1000 for h in well.history.h_cells[t]])
        assert list(trace.y) == pytest.approx([p * phase_diagrams.PA_TO_BAR for p in well.history.P_cells[t]])


def test_pumped_well_line_starts_at_the_pump_suction() -> None:
    """A well with a pump at its inlet is drawn from the upstream outlet (suction), through the discharge, onward.

    The march starts at the pump discharge, so without the suction point the
    pump's pressure and enthalpy rise would be a gap between the two wells.
    """
    wf = _run_fast("hydro_sf_electric.yml")
    surface = wf._orchestrator.components["surface"]  # noqa: SLF001
    assert isinstance(surface, GraphSurface)
    lower = wf._orchestrator.components["production_well_lower"]  # noqa: SLF001
    upper = wf._orchestrator.components["production_well_upper"]  # noqa: SLF001
    fluid_name, node_names = next(iter(phase_diagrams._fluid_groups(surface).items()))  # noqa: SLF001
    fig = phase_diagrams._build_figure(wf, surface, fluid_name, node_names, wf._sim_config.dt_years)  # noqa: SLF001
    for t, frame in enumerate(fig.frames):
        assert upper.history.pump_power_watts[t] > 0
        trace = next(tr for tr in frame.data if tr.name == "production_well_lower -> production_well_upper")
        assert list(trace.x) == pytest.approx(
            [lower.history.h_cells[t][-1] / 1000, *(h / 1000 for h in upper.history.h_cells[t])],
        )
        assert trace.y[1] > trace.y[0]  # the pump raises pressure


def test_written_diagram_title_names_the_config(tmp_path: Path) -> None:
    """A saved diagram's title carries the config file's stem and the config's own ``title``."""
    wf = _run_fast("hydro_sf_electric.yml")
    (path,) = phase_diagrams.write_phase_diagrams(wf, tmp_path, "hydro_sf_electric")
    html = path.read_text()
    assert "hydro_sf_electric — H2O P–h phase diagram" in html
    assert str(wf.to_dict()["title"]) in html


def test_phase_legend_has_one_entry_per_color() -> None:
    """Every phase color has a legend entry backed by a real data point (an empty trace gets no legend entry)."""
    fig = _sf_figure()
    legend_traces = [tr for tr in fig.data if tr.name in phase_diagrams._PHASE_LEGEND.values()]  # noqa: SLF001
    assert sorted(tr.name for tr in legend_traces) == sorted(phase_diagrams._PHASE_LEGEND.values())  # noqa: SLF001
    assert all(len(tr.x) == 1 and len(tr.y) == 1 for tr in legend_traces)


def test_pump_from_saturated_liquid_is_colored_liquid() -> None:
    """A condensate pump starts on the saturation curve but pumps liquid, so its line is liquid-colored, not two-phase."""
    fig = _sf_figure()
    for frame in fig.frames:
        trace = next(tr for tr in frame.data if tr.name == "condenser -> condensate_pump")
        assert trace.line.color == "blue"


def test_written_diagram_opens_static_on_the_final_year(tmp_path: Path) -> None:
    """The HTML doesn't animate on load, and its slider starts on the final year the plot shows."""
    wf = _run_fast("hydro_sf_electric.yml")
    (path,) = phase_diagrams.write_phase_diagrams(wf, tmp_path, "hydro_sf_electric")
    assert "Plotly.animate(" not in path.read_text()

    fig = _sf_figure()
    assert fig.layout.sliders[0].active == len(fig.frames) - 1


def test_state_points_are_numbered_in_flow_order() -> None:
    """Geofluid points are numbered from the surface inlet downstream; the key lists every point once."""
    wf = _run_fast("hydro_ORC_electric.yml")
    surface = wf._orchestrator.components["surface"]  # noqa: SLF001
    assert isinstance(surface, GraphSurface)
    groups = phase_diagrams._fluid_groups(surface)  # noqa: SLF001
    for fluid_name, node_names in groups.items():
        fig = phase_diagrams._build_figure(wf, surface, fluid_name, node_names, 1.0)  # noqa: SLF001
        key = [tr.name for tr in fig.data if tr.legend == "legend2"]
        names = [entry.split("  ", 1)[1] for entry in key]
        assert [entry.split("  ", 1)[0] for entry in key] == [str(i) for i in range(1, len(key) + 1)]
        assert len(set(names)) == len(names)
        if fluid_name == surface.common.fluid_name:
            assert names[:3] == ["inlet", "evaporator:out1", "preheater:out1"]
            assert names[-1] == "production_well_upper"
        labels = fig.frames[-1].data[-1]
        assert labels.mode == "text"
        numbers = sorted(int(n) for text in labels.text for n in text.split(", "))
        assert numbers == list(range(1, len(key) + 1))
