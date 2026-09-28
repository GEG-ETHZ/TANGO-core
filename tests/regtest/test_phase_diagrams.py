"""Regression tests for ``phase_diagrams.write_phase_diagrams``.

Uses a reduced timestep count (fast) rather than any example config's own
full length -- this is about the file-writing/data-correctness mechanism,
not physics, so there's no reason to pay for a full-length run.
"""

from __future__ import annotations

from pathlib import Path

from tango import phase_diagrams
from tango.components.surface.graph import GraphSurface
from tango.workflows.workflow import Workflow

_EXAMPLE_CONFIGS_DIR = Path(__file__).parents[2] / "example_configs"
_N_TSTEPS_FAST = 3


def _run_fast(filename: str) -> Workflow:
    cfg = Workflow.from_file(_EXAMPLE_CONFIGS_DIR / filename).to_dict()
    cfg["sim_config"]["num_tsteps"] = _N_TSTEPS_FAST
    wf = Workflow(cfg)
    wf.run()
    return wf


def test_single_fluid_config_writes_one_png_per_timestep(tmp_path: Path) -> None:
    """A single-working-fluid config (Single-Flash, H2O) writes one folder, one PNG per timestep."""
    wf = _run_fast("hydro_sf_electric.yml")
    written = phase_diagrams.write_phase_diagrams(wf, tmp_path, "hydro_sf_electric")

    fluid_dir = tmp_path / "hydro_sf_electric.phase_H2O"
    assert set(written) == {fluid_dir / f"{t:04d}.png" for t in range(_N_TSTEPS_FAST)}
    for path in written:
        assert path.exists()
        assert path.stat().st_size > 0


def test_binary_cycle_config_writes_one_folder_per_fluid(tmp_path: Path) -> None:
    """A binary (ORC) config writes one folder per fluid: the geofluid and the secondary fluid."""
    wf = _run_fast("hydro_orc_electric.yml")
    written = phase_diagrams.write_phase_diagrams(wf, tmp_path, "hydro_orc_electric")

    folders = {path.parent for path in written}
    assert folders == {
        tmp_path / "hydro_orc_electric.phase_H2O",
        tmp_path / "hydro_orc_electric.phase_R245fa",
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

    assert "droplet_separator:out1" in node_history
    assert "droplet_separator:out2" in node_history
    h_liquid = node_history["droplet_separator:out1"]["h"][-1]
    h_vapor = node_history["droplet_separator:out2"]["h"][-1]
    assert h_vapor > h_liquid * 2, (
        f"vapor-branch h ({h_vapor}) should be far larger than liquid-branch h "
        f"({h_liquid}) -- equal values would mean the branches are being conflated again"
    )


def test_splitting_node_with_unported_edge_connects_every_branch() -> None:
    """An edge with no ``target_port`` into a splitting node draws to EVERY branch.

    Regression guard: ``valve -> droplet_separator`` has no ``target_port``
    in the YAML (``droplet_separator`` has a single inlet, so there's no
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

    targets = phase_diagrams._target_history_keys(surface, "droplet_separator", None)  # noqa: SLF001

    assert set(targets) == {"droplet_separator:out1", "droplet_separator:out2"}


def test_fluid_groups_separates_geofluid_from_secondary_fluid() -> None:
    """A dual-fluid HeatExchanger's two sides are correctly attributed to different fluids."""
    wf = _run_fast("hydro_orc_electric.yml")
    surface = wf._orchestrator.components["surface"]  # noqa: SLF001
    assert isinstance(surface, GraphSurface)

    groups = phase_diagrams._fluid_groups(surface)  # noqa: SLF001

    assert set(groups.keys()) == {"H2O", "R245fa"}
    assert "heatexchanger:out1" in groups["H2O"]
    assert "heatexchanger:out2" in groups["R245fa"]


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


def test_axis_range_is_identical_across_every_timestep_png(tmp_path: Path) -> None:
    """Every PNG in a fluid's folder is rendered with the SAME fixed axis range.

    Ensures frames are directly comparable and there's no per-timestep
    rescale -- the whole reason for pivoting away from Plotly's animated
    slider, which had an unresolved axis-autorange bug (2026-09-28).
    """
    wf = _run_fast("hydro_sf_electric.yml")
    surface = wf._orchestrator.components["surface"]  # noqa: SLF001
    assert isinstance(surface, GraphSurface)
    groups = phase_diagrams._fluid_groups(surface)  # noqa: SLF001
    fluid_name, node_names = next(iter(groups.items()))

    seen_limits: list[tuple[tuple[float, float], tuple[float, float]]] = []

    def _fake_render_frame(*, xlim: tuple[float, float], ylim: tuple[float, float], **_: object) -> None:
        seen_limits.append((xlim, ylim))

    orig_render_frame = phase_diagrams._render_frame  # noqa: SLF001
    phase_diagrams._render_frame = _fake_render_frame  # type: ignore[assignment]  # noqa: SLF001
    try:
        phase_diagrams._write_fluid_pngs(  # noqa: SLF001
            wf,
            surface,
            fluid_name,
            node_names,
            wf._sim_config.dt_years,  # noqa: SLF001
            tmp_path / "fluid_dir",
        )
    finally:
        phase_diagrams._render_frame = orig_render_frame  # noqa: SLF001

    assert len(seen_limits) == _N_TSTEPS_FAST
    assert len(set(seen_limits)) == 1


def test_no_graph_surface_writes_nothing(tmp_path: Path) -> None:
    """A Workflow with no GraphSurface component writes nothing (nothing to error on either)."""
    wf = _run_fast("hydro_sf_electric.yml")
    surface = wf._orchestrator.components.pop("surface")  # noqa: SLF001
    try:
        written = phase_diagrams.write_phase_diagrams(wf, tmp_path, "no_surface")
        assert written == []
    finally:
        wf._orchestrator.components["surface"] = surface  # noqa: SLF001
