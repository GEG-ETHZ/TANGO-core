"""Per-year P-h phase-diagram PNGs for every working fluid in a Workflow.

``tango_cli run --save-dir DIR`` is the caller. Writes one
``<stem>.phase_<fluid>/`` folder per distinct working fluid found in a
``GraphSurface`` component's TESPy network (e.g. the primary geofluid plus,
for a binary/ORC plant, the secondary working fluid), containing one static
PNG per timestep (``0000.png``, ``0001.png``, ...): x-axis specific enthalpy
h [kJ/kg], y-axis pressure P [bar] (log scale), the fluid's saturation dome,
and the (P, h) state at every node in that fluid's loop, connected in
topology order.

Originally an interactive Plotly figure with a year slider (GitLab #56).
Pivoted to a folder of static matplotlib PNGs (2026-09-28) after Plotly.js's
log-scale-axis-plus-animation-frame rendering turned out to have an
unresolved bug (the axis periodically blows out to an absurd range, e.g.
10^100+, on some slider positions/after the page sits open a while, even
with an explicit fixed range pinned on every single frame's own layout) --
a static PNG per year has no animation/frame-transition machinery at all,
so there's nothing left for that class of bug to attach to.

For the PRIMARY geofluid (``common.fluid_name``) specifically, the loop
extends past the surface plant's own TESPy network into the outer circuit
(injection well -> reservoir/horizontal well -> production well(s) ->
surface -> back to injection well), so the diagram closes into a real loop
rather than stopping at the surface plant's own inlet/outlet -- a secondary
ORC/binary-cycle working fluid never leaves the surface plant, so it has no
subsurface leg to add.

Each line segment is colored by its SOURCE point's thermodynamic phase
(liquid/gas/supercritical/two-phase -- see ``_PHASE_COLORS``), not a single
fixed color for the whole fluid. The axis range is fixed identically across
every PNG in a fluid's folder (computed once from the full run's data), so
frames are directly comparable and there's no risk of a per-frame rescale.

Only ``GraphSurface`` surface components are covered -- other
``SurfaceComponent`` variants don't expose a TESPy network's per-node
detail at all, so there's nothing to plot for them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from CoolProp import CoolProp as CP
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from tango.components.surface.graph import GraphSurface
from tango.core.constants import J_PER_KG_TO_KJ_PER_KG, PA_TO_BAR
from tango.core.fluid_state import FluidState

if TYPE_CHECKING:
    from pathlib import Path

    from tango.core.component import Component
    from tango.workflows.workflow import Workflow

_N_DOME_POINTS = 200
"""Points per saturation-curve branch (liquid/vapor) when tracing the dome."""

_FIGSIZE = (10.0, 6.0)
_DPI = 150

_PHASE_COLORS: dict[int, str] = {
    CP.iphase_liquid: "blue",
    CP.iphase_gas: "orange",
    CP.iphase_supercritical: "green",
    CP.iphase_supercritical_gas: "green",
    CP.iphase_supercritical_liquid: "green",
    CP.iphase_critical_point: "green",
    CP.iphase_twophase: "red",
}
"""CoolProp phase index -> line color (Chad's request, 2026-09-25; the
``iphase_twophase`` entry added 2026-09-28).

Two-phase (wet) states turned out to be the NORMAL case for several node
types in this domain, not a rare edge case as originally assumed: a flash
valve's outlet, a ``DropletSeparator``'s saturated-liquid branch, a wet
turbine's exhaust, and a condenser's outlet are all routinely two-phase
mixtures. Chad's original 3-color request had no bucket for this, so
those points silently fell back to an unstyled gray -- fixed by giving
two-phase its own explicit color instead."""

_PHASE_COLOR_FALLBACK = "gray"
"""Line color for a phase CoolProp reports but ``_PHASE_COLORS`` has no
entry for (``iphase_unknown``/``iphase_not_imposed``) -- genuinely rare,
unlike ``iphase_twophase`` (see that dict's own docstring)."""

_PHASE_LEGEND: dict[str, str] = {
    "blue": "Liquid",
    "orange": "Gas",
    "green": "Supercritical",
    "red": "Two-phase (wet)",
    _PHASE_COLOR_FALLBACK: "Unknown/other",
}
"""Line color -> human-readable label, in display order."""


def write_phase_diagrams(wf: Workflow, save_dir: Path, stem: str) -> list[Path]:
    """Write one ``<stem>.phase_<fluid>/`` folder (one PNG per timestep) per working fluid in ``wf``.

    Args:
        wf: A Workflow whose ``run()`` has already completed.
        save_dir: Directory to write into; created if it doesn't exist.
        stem: Base filename (no extension) -- typically the input YAML's
            own stem.

    Returns:
        Every PNG path actually written, across every fluid. Empty if
        ``wf`` has no ``GraphSurface`` component (nothing to plot).
    """
    save_dir.mkdir(parents=True, exist_ok=True)
    dt_years = wf._sim_config.dt_years  # noqa: SLF001
    written: list[Path] = []

    for component in wf._orchestrator.components.values():  # noqa: SLF001
        if not isinstance(component, GraphSurface):
            continue
        for fluid_name, node_names in _fluid_groups(component).items():
            fluid_dir = save_dir / f"{stem}.phase_{fluid_name}"
            written += _write_fluid_pngs(wf, component, fluid_name, node_names, dt_years, fluid_dir)

    return written


def _fluid_groups(component: GraphSurface) -> dict[str, list[str]]:
    """Map fluid name -> the ``node_history`` keys whose connection carries it.

    Mirrors ``GraphSurface._collect_node_detail``'s own key-qualification
    scheme exactly (bare node name for a single-output node, else
    ``"{name}:{source_id}"`` per outgoing connection) so these keys line up
    with what's actually recorded in ``node_history`` -- see that method's
    docstring for why a node can have more than one outgoing connection
    (a ``DropletSeparator``'s liquid/vapor split, a dual-fluid
    ``HeatExchanger``'s two sides) and why picking only the first one used
    to silently produce wrong data.

    Fluid identity is read directly off the live TESPy connection
    (``Connection.fluid.val``, authoritative) -- not inferred from YAML
    (``fluid_out{N}`` only appears on the ONE node that introduces a
    secondary loop, not on every node carrying it).
    """
    groups: dict[str, list[str]] = {}
    for name, node in component._nodes.items():  # noqa: SLF001
        outgoing = [c for c in component._conns if c.source is node]  # noqa: SLF001
        for conn in outgoing:
            key = name if len(outgoing) == 1 else f"{name}:{conn.source_id}"
            (fluid_name,) = conn.fluid.val.keys()
            groups.setdefault(fluid_name, []).append(key)
    return groups


def _node_history_key(component: GraphSurface, node_name: str, port: str | None) -> str:
    """The ``node_history`` key for ``node_name``'s outgoing state on the given port.

    ``port`` is an edge's own ``source_port``/``target_port`` (already
    present in the YAML for exactly the multi-port cases this matters
    for -- e.g. ``hydro_orc_electric.yml``'s dual-fluid ``HeatExchanger``
    edges). A ``target_port`` (``"in1"``/``"in2"``) is translated to the
    matching outgoing port (``"out1"``/``"out2"``) -- TESPy's own
    dual-fluid ``HeatExchanger`` convention pairs side 1 in with side 1
    out, side 2 in with side 2 out (confirmed: the only component type in
    this matrix with more than one INCOMING port also has exactly that
    many outgoing ports, matched 1:1 by index).
    """
    node = component._nodes[node_name]  # noqa: SLF001
    outgoing = [c for c in component._conns if c.source is node]  # noqa: SLF001
    if len(outgoing) <= 1:
        return node_name
    out_port = port.replace("in", "out") if port else outgoing[0].source_id
    return f"{node_name}:{out_port}"


def _target_history_keys(component: GraphSurface, node_name: str, port: str | None) -> list[str]:
    """Every ``node_history`` key that receives this edge as an incoming connection.

    Usually a single key, same as ``_node_history_key``. But when the edge
    specifies no ``target_port`` AND the target node has multiple outgoing
    branches (a splitting node, e.g. ``DropletSeparator``'s liquid/vapor
    split), the incoming stream physically arrives at ALL of those
    branches at once -- the split happens exactly at that point -- so every
    branch key is returned instead of arbitrarily picking one.

    This fixes a real bug (Chad, 2026-09-26): ``valve -> droplet_separator``
    has no ``target_port`` in the YAML (``droplet_separator`` has a single
    inlet, so there's no real ambiguity in the TESPy topology), but the
    single-key version of this lookup used to fall back to
    ``outgoing[0].source_id``, drawing the incoming edge to only
    ``droplet_separator:out1`` and leaving ``droplet_separator:out2`` (the
    vapor branch feeding the turbine) with no visible incoming connection
    at all -- it rendered as a disconnected terminal node.
    """
    node = component._nodes[node_name]  # noqa: SLF001
    outgoing = [c for c in component._conns if c.source is node]  # noqa: SLF001
    if len(outgoing) <= 1:
        return [node_name]
    if port is not None:
        return [f"{node_name}:{port.replace('in', 'out')}"]
    return [f"{node_name}:{conn.source_id}" for conn in outgoing]


def _outer_circuit_order(wf: Workflow) -> list[tuple[str, Component]]:
    """Every component in ``wf``, in physical loop order (following ``.next`` from idx 0).

    Mirrors the outer-circuit convention used throughout ``tango``
    (``component_idx``/``prev``/``next``, a single cycle across every
    component including the surface plant) -- see ``Workflow``'s own class
    docstring.
    """
    components = wf._orchestrator.components  # noqa: SLF001
    by_idx = {c.component_idx: (name, c) for name, c in components.items()}
    order: list[tuple[str, Component]] = []
    idx = 0
    seen: set[int] = set()
    while idx not in seen:
        seen.add(idx)
        name, comp = by_idx[idx]
        order.append((name, comp))
        idx = comp.next  # type: ignore[attr-defined]  # every outer-circuit component has this field, just not declared on the shared base
    return order


def _add_subsurface_points(
    wf: Workflow,
    component: GraphSurface,
    backend: str,
    n_tsteps: int,
    h_kj: dict[str, list[float]],
    p_bar: dict[str, list[float]],
) -> list[tuple[str, str]]:
    """Extend ``h_kj``/``p_bar`` with every non-surface component's own outlet state.

    Closes the loop visually (Chad's request, 2026-09-25): without this,
    the diagram stops at the surface plant's own ``inlet``/``outlet``
    TESPy nodes, even though the real physical loop continues through the
    wells/reservoir back to ``inlet``. Only called for the PRIMARY
    geofluid -- an ORC/binary secondary fluid never leaves the surface
    plant, so it has no subsurface leg.

    Returns:
        The extra edges connecting the outer circuit to the surface
        plant's own ``inlet``/``outlet`` (the surface plant's own INTERNAL
        edges are already handled by the caller).
    """
    fluid_name = component.common.fluid_name
    surface_history = component.history
    h_kj["outlet"] = [
        FluidState.with_PT(fluid_name, p, t, backend).H * J_PER_KG_TO_KJ_PER_KG
        for t, p in zip(
            surface_history.T_outlet[:n_tsteps],
            surface_history.P_outlet[:n_tsteps],
            strict=False,
        )
    ]
    p_bar["outlet"] = [p * PA_TO_BAR for p in surface_history.P_outlet[:n_tsteps]]

    outer_order = _outer_circuit_order(wf)
    for name, comp in outer_order:
        if comp is component:
            continue
        history = comp.history  # type: ignore[attr-defined]  # every outer-circuit component has this field, just not declared on the shared base
        h_kj[name] = [
            FluidState.with_PT(fluid_name, p, t, backend).H * J_PER_KG_TO_KJ_PER_KG
            for t, p in zip(history.T_outlet[:n_tsteps], history.P_outlet[:n_tsteps], strict=False)
        ]
        p_bar[name] = [p * PA_TO_BAR for p in history.P_outlet[:n_tsteps]]

    # Consecutive pairs around the full outer loop, entering/exiting the
    # surface plant via its own "inlet"/"outlet" keys instead of its bare
    # component name (which has no state of its own -- it's a whole
    # sub-network, not a single point).
    keyed_order = [("inlet", "outlet") if comp is component else (name, name) for name, comp in outer_order]
    return [(keyed_order[i][1], keyed_order[(i + 1) % len(keyed_order)][0]) for i in range(len(keyed_order))]


def _write_fluid_pngs(
    wf: Workflow,
    component: GraphSurface,
    fluid_name: str,
    node_names: list[str],
    dt_years: float,
    fluid_dir: Path,
) -> list[Path]:
    """Write one PNG per timestep for ``fluid_name`` into ``fluid_dir``; return the paths written."""
    backend = component.common.coolprop_backend
    node_history = component.history.node_history
    n_tsteps = min(len(node_history[name].get("h", [])) for name in node_names if name in node_history)

    h_kj: dict[str, list[float]] = {}
    p_bar: dict[str, list[float]] = {}
    for name in node_names:
        hist = node_history.get(name, {})
        # Read h/p directly off the recorded connection state (see
        # components/surface/graph.py's _collect_node_detail) rather than
        # re-deriving h from (T, p) via CoolProp: a state sitting exactly on
        # the saturation curve (e.g. a condenser outlet) makes (T, p) an
        # ill-posed input pair for a tabular backend.
        h_kj[name] = [h * J_PER_KG_TO_KJ_PER_KG for h in hist.get("h", [])][:n_tsteps]
        p_bar[name] = [p * PA_TO_BAR for p in hist.get("p", [])][:n_tsteps]

    edges = [
        (source_key, target_key)
        for edge in component.power_plant.get("edges", {}).values()
        if (source_key := _node_history_key(component, edge["source"], edge.get("source_port"))) in h_kj
        for target_key in _target_history_keys(component, edge["target"], edge.get("target_port"))
        if target_key in h_kj
    ]

    if fluid_name == component.common.fluid_name:
        edges += _add_subsurface_points(wf, component, backend, n_tsteps, h_kj, p_bar)
        node_names = [*node_names, *[n for n in h_kj if n not in node_names]]

    h_dome, p_dome = _dome_xy(fluid_name, backend)

    # Fixed axis range, identical across every PNG in this folder (computed
    # once from the FULL run's data, not per timestep) -- makes frames
    # directly comparable and, since there's no animation/frame-transition
    # machinery at all with static PNGs, sidesteps the whole class of
    # Plotly.js axis-range bug this module used to fight (see module
    # docstring).
    all_h = [v for series in h_kj.values() for v in series] + h_dome
    all_p = [v for series in p_bar.values() for v in series] + p_dome
    h_min, h_max = min(all_h), max(all_h)
    p_min, p_max = min(all_p), max(all_p)
    xlim = (h_min - 0.05 * (h_max - h_min), h_max + 0.05 * (h_max - h_min))
    ylim = (10 ** (np.log10(p_min) - 0.2), 10 ** (np.log10(p_max) + 0.2))

    fluid_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for t in range(n_tsteps):
        path = fluid_dir / f"{t:04d}.png"
        _render_frame(
            path=path,
            fluid_name=fluid_name,
            backend=backend,
            h_dome=h_dome,
            p_dome=p_dome,
            edges=edges,
            h_kj=h_kj,
            p_bar=p_bar,
            t=t,
            elapsed_years=t * dt_years,
            xlim=xlim,
            ylim=ylim,
        )
        written.append(path)
    return written


def _render_frame(
    *,
    path: Path,
    fluid_name: str,
    backend: str,
    h_dome: list[float],
    p_dome: list[float],
    edges: list[tuple[str, str]],
    h_kj: dict[str, list[float]],
    p_bar: dict[str, list[float]],
    t: int,
    elapsed_years: float,
    xlim: tuple[float, float],
    ylim: tuple[float, float],
) -> None:
    """Render and save a single year's P-h diagram to ``path``.

    No per-node labels (Chad, 2026-09-28: "the labels are a mess") --
    dropped rather than fixed for now; hover-free static PNGs have no good
    substitute for Plotly's hover text, so tracing a specific node needs
    the caller's own knowledge of the topology for the time being.
    """
    fig = Figure(figsize=_FIGSIZE)
    FigureCanvasAgg(fig)
    ax = fig.subplots()

    ax.plot(h_dome, p_dome, color="black", linestyle=":", linewidth=1.0)

    for source, target in edges:
        h_s, h_t = h_kj[source][t], h_kj[target][t]
        p_s, p_t = p_bar[source][t], p_bar[target][t]
        color = _phase_color(fluid_name, h_s, p_s, backend)
        ax.plot([h_s, h_t], [p_s, p_t], color=color, marker="o", markersize=3, linewidth=1.5)
        _add_direction_arrow(ax, h_s, p_s, h_t, p_t, color)

    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_yscale("log")
    ax.set_xlabel("Specific enthalpy h [kJ/kg]")
    ax.set_ylabel("Pressure P [bar]")
    ax.set_title(f"{fluid_name} — P-h phase diagram (year {elapsed_years:.0f})")
    ax.grid(True, which="major", linestyle="-", linewidth=0.5, alpha=0.6)
    ax.grid(True, which="minor", linestyle="-", linewidth=0.3, alpha=0.3)

    legend_handles = [
        Line2D([0], [0], marker="o", linestyle="", color=color, label=label)
        for color, label in _PHASE_LEGEND.items()
    ]
    legend_handles.append(
        Line2D([0], [0], color="black", linestyle=":", label=f"{fluid_name} saturation dome"),
    )
    ax.legend(handles=legend_handles, loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0.0)

    fig.tight_layout()
    fig.savefig(path, dpi=_DPI)


def _add_direction_arrow(ax: Axes, h_s: float, p_s: float, h_t: float, p_t: float, color: str) -> None:
    """Draw a short arrowhead at an edge's midpoint, showing flow direction source -> target.

    Midpointed in LOG space for P (matches the log-scale y-axis) so the
    arrow actually sits on the rendered line, not off to one side -- linear
    midpointing would put it right against one end whenever the two
    pressures differ by orders of magnitude, as they often do here.
    """
    frac = 0.05
    t0, t1 = 0.5 - frac, 0.5 + frac
    h0 = h_s + t0 * (h_t - h_s)
    h1 = h_s + t1 * (h_t - h_s)
    if p_s > 0 and p_t > 0:
        log_p_s, log_p_t = np.log10(p_s), np.log10(p_t)
        p0 = float(10 ** (log_p_s + t0 * (log_p_t - log_p_s)))
        p1 = float(10 ** (log_p_s + t1 * (log_p_t - log_p_s)))
    else:
        p0 = p_s + t0 * (p_t - p_s)
        p1 = p_s + t1 * (p_t - p_s)
    ax.annotate(
        "",
        xy=(h1, p1),
        xytext=(h0, p0),
        arrowprops={"arrowstyle": "-|>", "color": color, "lw": 1.5},
    )


def _phase_color(fluid_name: str, h_kj_val: float, p_bar_val: float, backend: str) -> str:
    """Line/marker color for the thermodynamic phase at one (h, P) point (Chad's request, 2026-09-25)."""
    state = CP.AbstractState(backend, fluid_name)
    state.update(CP.HmassP_INPUTS, h_kj_val / J_PER_KG_TO_KJ_PER_KG, p_bar_val / PA_TO_BAR)
    return _PHASE_COLORS.get(state.phase(), _PHASE_COLOR_FALLBACK)


def _dome_xy(fluid_name: str, backend: str) -> tuple[list[float], list[float]]:
    """Sweep the saturation dome (liquid + vapor branches, triple point to critical point).

    The expensive part of tracing the dome (a real CoolProp property
    lookup per point) -- called ONCE per fluid, not once per timestep PNG.
    """
    state = CP.AbstractState(backend, fluid_name)
    T_triple = state.trivial_keyed_output(CP.iT_triple)
    T_crit = state.trivial_keyed_output(CP.iT_critical)
    T_values = np.linspace(T_triple, T_crit, _N_DOME_POINTS)[:-1]  # critical point added once, below

    def _branch(quality: float) -> tuple[list[float], list[float]]:
        h_vals: list[float] = []
        p_vals: list[float] = []
        for T in T_values:
            st = CP.AbstractState(backend, fluid_name)
            try:
                st.update(CP.QT_INPUTS, quality, T)
            except ValueError:
                continue
            h_vals.append(st.hmass() * J_PER_KG_TO_KJ_PER_KG)
            p_vals.append(st.p() * PA_TO_BAR)
        return h_vals, p_vals

    h_liquid, p_liquid = _branch(0.0)
    h_vapor, p_vapor = _branch(1.0)
    crit = CP.AbstractState(backend, fluid_name)
    crit.update(CP.QT_INPUTS, 0.5, T_crit * (1 - 1e-6))
    h_c = crit.hmass() * J_PER_KG_TO_KJ_PER_KG
    p_c = crit.p() * PA_TO_BAR

    h_dome = [*h_liquid, h_c, *reversed(h_vapor)]
    p_dome = [*p_liquid, p_c, *reversed(p_vapor)]
    return h_dome, p_dome
