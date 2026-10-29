# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Interactive P-h phase diagrams for every working fluid in a Workflow.

``tango_core run --save-dir DIR`` is the caller. Writes one
``<stem>.phase_<fluid>.html`` file per distinct working fluid found in a
``GraphSurface`` component's TESPy network (e.g. the primary geofluid plus,
for a binary/ORC plant, the secondary working fluid) -- an interactive
Plotly figure with a year slider (see module docstring's own "Inspiration"
section in GitLab issue #56), loosely modeled on the tango web app's own
Phase Diagram tab: x-axis specific enthalpy h [kJ/kg], y-axis pressure P
[bar] (log scale), the fluid's saturation dome, and the (P, h) state at
every node in that fluid's loop, connected in topology order and faded by
elapsed time.

For the PRIMARY geofluid (``common.fluid_name``) specifically, the loop
extends past the surface plant's own TESPy network into the outer
circuit (injection well -> reservoir/horizontal well -> production
well(s) -> surface -> back to injection well), so the diagram closes into
a real loop rather than stopping at the surface plant's own inlet/outlet
(Chad's request, 2026-09-25) -- a secondary ORC/binary-cycle working fluid
never leaves the surface plant, so it has no subsurface leg to add.

Each line segment is colored by its SOURCE point's thermodynamic phase
(liquid/gas/supercritical -- see ``_PHASE_COLORS``), not a single fixed
color for the whole fluid.

Behind the cycle, each diagram draws reference lines of constant density
(isochores), entropy (isentropes), temperature (isotherms), and vapor
quality, configurable via ``PhaseDiagramConfig`` (``tango_core run
--phase-diagram-config``). They're static across years; only the node
states move with the slider.

Only ``GraphSurface`` surface components are covered -- other
``SurfaceComponent`` variants don't expose a TESPy network's per-node
detail at all, so there's nothing to plot for them.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt
import plotly.graph_objects as go
import yaml
from CoolProp import CoolProp as CP

from tango_core.components.surface.graph import GraphSurface
from tango_core.components.well.grouped_subsurface import (
    SEGMENT_NAMES,
    NumericalGroupedSubsurface,
    RaftGroupedSubsurface,
)
from tango_core.core.constants import J_PER_KG_TO_KJ_PER_KG, PA_TO_BAR
from tango_core.core.errors import ConfigError
from tango_core.core.fluid_state import FluidState

if TYPE_CHECKING:
    from tango_core.core.component import FlowComponent
    from tango_core.workflows.workflow import Workflow

_N_DOME_POINTS = 200
"""Points per saturation-curve branch (liquid/vapor) when tracing the dome."""

_LABEL_MERGE_FRACTION = 0.01
"""State points closer than this fraction of the plot's width and height share one number label."""

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
"""Line color -> human-readable label, in display order (Chad, 2026-09-28:
"nothing showing what the colors mean" -- the rendered figure had no
legend at all for the per-edge phase coloring, only for the dome trace)."""

_N_PROPERTY_LINE_POINTS = 150
"""Points per isotherm/isentrope/isochore (swept in pressure) or quality line (swept in temperature)."""

_PROPERTY_LINE_STYLES: dict[str, tuple[str, str, str]] = {
    "isotherm_temperatures_kelvin": ("Isotherms (°C)", "dash", "217, 96, 76"),
    "isentrope_entropies_kj_per_kg_kelvin": ("Isentropes (kJ/kg·K)", "dashdot", "91, 107, 214"),
    "isochore_densities_kg_per_m3": ("Isochores (kg/m³)", "dot", "111, 154, 58"),
    "qualities": ("Quality (x)", "longdashdot", "192, 79, 201"),
}
"""Config field -> (legend group label, line dash, RGB). Thin, dashed, and
semi-transparent so they read as background behind the solid, phase-colored
cycle; each line's label is drawn in the same color, fully opaque."""

_PROPERTY_LINE_OPACITY = 0.55

_LABEL_POSITIONS = {"qualities": "top center"}

_TOP_EDGE_FRACTION = 0.95
"""Label anchors above this fraction of the (log) pressure axis count as on the top edge."""
"""Text position relative to a line's label anchor, per family; default ``middle left``
(anchors at the right edge, so the text stays inside the plot)."""

_REFERENCE_LINE_BACKEND = "HEOS"
"""CoolProp backend for reference lines, regardless of the simulation's own
``coolprop_backend``. Tabular backends (e.g. ``BICUBIC&HEOS``) interpolate
across the phase boundary just off saturation -- a 150 °C isotherm queried
just below its saturation pressure came back at h = 2138 kJ/kg, inside the
dome, drawing a spurious notch. The full equation of state is exact there,
and reference lines are cheap enough that its cost doesn't matter."""
_DOME_FILL_COLOR = "rgba(250, 225, 190, 0.45)"

LineSpec = int | tuple[float, ...]
"""Either a count of lines, spread across the range the plotted states span, or explicit values."""


@dataclass(frozen=True)
class PropertyLineConfig:
    """Which reference lines to draw behind one fluid's cycle.

    Each field is either a count (``int``) or explicit values. A count
    spreads that many lines across the range spanned by the plotted node
    states -- linearly for temperature and entropy, logarithmically for
    density, evenly inside ``(0, 1)`` for quality. ``0`` or ``[]`` turns
    a family off.
    """

    isotherm_temperatures_kelvin: LineSpec = 5
    isentrope_entropies_kj_per_kg_kelvin: LineSpec = 5
    isochore_densities_kg_per_m3: LineSpec = 5
    qualities: LineSpec = (0.2, 0.4, 0.6, 0.8)

    @classmethod
    def from_mapping(cls, data: dict[str, Any], *, where: str) -> PropertyLineConfig:
        """Validate and build from a parsed YAML/JSON mapping; ``where`` names it in errors."""
        allowed = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ConfigError(f"{where}: unknown key(s) {unknown}; allowed: {sorted(allowed)}")
        values: dict[str, LineSpec] = {}
        for key, raw in data.items():
            if isinstance(raw, bool) or not isinstance(raw, (int, list, tuple)):
                raise ConfigError(f"{where}.{key}: expected a count or a list of numbers, got {raw!r}")
            if isinstance(raw, int):
                if raw < 0:
                    raise ConfigError(f"{where}.{key}: count must be >= 0, got {raw}")
                values[key] = raw
                continue
            try:
                numbers = tuple(float(v) for v in raw)
            except (TypeError, ValueError):
                raise ConfigError(f"{where}.{key}: expected a list of numbers, got {raw!r}") from None
            if key == "qualities" and any(not 0.0 <= q <= 1.0 for q in numbers):
                raise ConfigError(f"{where}.{key}: qualities must be within [0, 1], got {list(numbers)}")
            if key != "qualities" and any(v <= 0 for v in numbers):
                raise ConfigError(f"{where}.{key}: values must be > 0, got {list(numbers)}")
            values[key] = numbers
        return cls(**values)


@dataclass(frozen=True)
class PhaseDiagramConfig:
    """Reference-line settings for every phase diagram, with optional per-fluid overrides.

    Parsed by ``load_phase_diagram_config`` from YAML or JSON (e.g.
    ``tango_core run --phase-diagram-config``)::

        isotherm_temperatures_kelvin: [350, 400, 450, 500, 550]
        isentrope_entropies_kj_per_kg_kelvin: 4
        isochore_densities_kg_per_m3: [1, 10, 100, 1000]
        qualities: [0.2, 0.4, 0.6, 0.8]
        fluids:
          Isopentane:
            isochore_densities_kg_per_m3: 3

    Top-level keys apply to every fluid; a ``fluids.<name>`` entry
    overrides individual keys for that fluid only (explicit densities
    that suit water mean little for an ORC working fluid). Omitted keys
    keep ``PropertyLineConfig``'s defaults.
    """

    default: PropertyLineConfig = field(default_factory=PropertyLineConfig)
    per_fluid: dict[str, dict[str, Any]] = field(default_factory=dict)

    def for_fluid(self, fluid_name: str) -> PropertyLineConfig:
        """Settings for one fluid: the defaults with that fluid's overrides applied."""
        overrides = self.per_fluid.get(fluid_name)
        if not overrides:
            return self.default
        given = PropertyLineConfig.from_mapping(overrides, where=f"fluids.{fluid_name}")
        # take only the keys this fluid actually overrides; the rest come from the defaults
        merged = {
            f.name: getattr(given, f.name) if f.name in overrides else getattr(self.default, f.name)
            for f in fields(PropertyLineConfig)
        }
        return PropertyLineConfig(**merged)


def load_phase_diagram_config(source: str) -> PhaseDiagramConfig:
    """Parse a ``PhaseDiagramConfig`` from a YAML/JSON file path or an inline YAML/JSON string.

    Raises:
        ConfigError: the text isn't a mapping, or any key/value is invalid.
    """
    path = Path(source)
    text = path.read_text(encoding="utf-8") if path.is_file() else source
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"phase diagram config: not valid YAML/JSON ({exc})") from exc
    if data is None:
        return PhaseDiagramConfig()
    if not isinstance(data, dict):
        raise ConfigError(f"phase diagram config: expected a mapping, got {type(data).__name__}")
    data = dict(data)
    per_fluid = data.pop("fluids", None) or {}
    if not isinstance(per_fluid, dict) or not all(isinstance(v, dict) for v in per_fluid.values()):
        raise ConfigError("phase diagram config: 'fluids' must map fluid names to mappings")
    config = PhaseDiagramConfig(
        default=PropertyLineConfig.from_mapping(data, where="phase diagram config"),
        per_fluid={str(name): dict(overrides) for name, overrides in per_fluid.items()},
    )
    for name in config.per_fluid:
        config.for_fluid(name)  # validate overrides up front, not mid-run
    return config


def write_phase_diagrams(
    wf: Workflow,
    save_dir: Path,
    stem: str,
    config: PhaseDiagramConfig | None = None,
) -> list[Path]:
    """Write one ``<stem>.phase_<fluid>.html`` per working fluid found in ``wf``.

    Args:
        wf: A Workflow whose ``run()`` has already completed.
        save_dir: Directory to write into; created if it doesn't exist.
        stem: Base filename (no extension) -- typically the input YAML's
            own stem.
        config: Reference-line settings; ``None`` uses the defaults.

    Returns:
        Paths actually written, one per distinct working fluid across
        every ``GraphSurface`` component in ``wf``. Empty if ``wf`` has no
        ``GraphSurface`` component (nothing to plot).
    """
    config = config or PhaseDiagramConfig()
    save_dir.mkdir(parents=True, exist_ok=True)
    dt_years = wf._sim_config.dt_years  # noqa: SLF001
    written: list[Path] = []

    for component in wf._orchestrator.components.values():  # noqa: SLF001
        if not isinstance(component, GraphSurface):
            continue
        for fluid_name, node_names in _fluid_groups(component).items():
            path = save_dir / f"{stem}.phase_{fluid_name}.html"
            fig = _build_figure(
                wf,
                component,
                fluid_name,
                node_names,
                dt_years,
                config.for_fluid(fluid_name),
                config_name=stem,
            )
            # auto_play=False: open on the final year, static, and let the
            # reader drag the slider instead of animating every year on load.
            fig.write_html(path, auto_play=False)
            written.append(path)

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
    for -- e.g. ``hydro_ORC_electric.yml``'s dual-fluid ``HeatExchanger``
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

    This fixes a real bug (Chad, 2026-09-26): ``flash_valve -> separator``
    has no ``target_port`` in the YAML (``separator`` has a single
    inlet, so there's no real ambiguity in the TESPy topology), but the
    single-key version of this lookup used to fall back to
    ``outgoing[0].source_id``, drawing the incoming edge to only
    ``separator:out1`` and leaving ``separator:out2`` (the
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


def _outer_circuit_order(wf: Workflow) -> list[tuple[str, FlowComponent]]:
    """Every component in ``wf``, in physical loop order (following ``.next`` from idx 0).

    Mirrors the outer-circuit convention used throughout ``tango_core``
    (``component_idx``/``prev``/``next``, a single cycle across every
    component including the surface plant) -- see ``Workflow``'s own class
    docstring. A ``grouped_subsurface`` component is listed as its three well
    segments, under their own names (``"injection_well"`` etc., as in a
    config with three separate well components), so each gets its own
    profile and label. For the ``raft`` variant, whose segments have no
    state of their own, each entry is the component itself;
    ``_raft_segment_profiles`` splits RAFT's profile along the loop into
    the three.
    """
    components = wf._orchestrator.components  # noqa: SLF001
    by_idx = {c.component_idx: (name, c) for name, c in components.items()}
    order: list[tuple[str, FlowComponent]] = []
    idx = 0
    seen: set[int] = set()
    while idx not in seen:
        seen.add(idx)
        name, comp = by_idx[idx]
        if isinstance(comp, NumericalGroupedSubsurface):
            order += [
                (segment_name, segment)
                for segment_name, segment in zip(SEGMENT_NAMES, comp.segments(), strict=True)
            ]
        elif isinstance(comp, RaftGroupedSubsurface):
            order += [(segment_name, comp) for segment_name in SEGMENT_NAMES]
        else:
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
    profiles: dict[str, list[tuple[list[float], list[float]]]],
    pumped: dict[str, list[bool]],
) -> list[tuple[str, str]]:
    """Extend ``h_kj``/``p_bar`` with every non-surface component's own outlet state.

    A component that records a marched axial profile (a numerical well's
    per-node ``h_cells``/``P_cells``) also gets ``profiles[name][t]`` =
    that year's ``(h [kJ/kg], P [bar])`` along the flow path, and its
    outlet point is the profile's last node -- the state the march actually
    produced, not one rebuilt from (T, P). A profiled component whose own
    pump ran that year (``pump_power_watts > 0``; the pump sits at its
    inlet, so the march starts at the pump discharge) gets its upstream
    neighbor's outlet -- the pump suction -- prepended, so the pump's
    pressure and enthalpy rise is drawn as part of the component's line
    instead of a gap; ``pumped[name][t]`` records which years that applies to.

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
    # The surface plant's exit state is the recorded state of the connection
    # INTO its "outlet" Sink (GraphSurface requires exactly one). Re-deriving
    # h from the plant's outlet (T, P) instead is unreliable near the critical
    # point: CO2 at 75 bar and ~31.7 degC moves 19 kJ/kg per 0.17 K, and a
    # tabular backend put the re-derived point 16 kJ/kg away from the node
    # feeding it, drawing a visible gap in the loop.
    exit_key = next(
        (
            _node_history_key(component, edge["source"], edge.get("source_port"))
            for edge in component.power_plant.get("edges", {}).values()
            if edge["target"] == "outlet"
        ),
        None,
    )
    if exit_key in h_kj:
        h_kj["outlet"] = list(h_kj[exit_key])
        p_bar["outlet"] = list(p_bar[exit_key])
    else:
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
        if isinstance(comp, RaftGroupedSubsurface):
            profiles[name] = [
                _raft_segment_profiles(comp, t)[SEGMENT_NAMES.index(name)] for t in range(n_tsteps)
            ]
            h_kj[name] = [profile_h[-1] for profile_h, _ in profiles[name]]
            p_bar[name] = [profile_p[-1] for _, profile_p in profiles[name]]
            continue
        history = comp.history  # type: ignore[attr-defined]  # every outer-circuit component has this field, just not declared on the shared base
        h_cells = getattr(history, "h_cells", None)
        p_cells = getattr(history, "P_cells", None)
        if h_cells and p_cells and len(h_cells) >= n_tsteps:
            profiles[name] = [
                (
                    [h * J_PER_KG_TO_KJ_PER_KG for h in h_cells[t]],
                    [p * PA_TO_BAR for p in p_cells[t]],
                )
                for t in range(n_tsteps)
            ]
            h_kj[name] = [profile_h[-1] for profile_h, _ in profiles[name]]
            p_bar[name] = [profile_p[-1] for _, profile_p in profiles[name]]
            continue
        recorded_h = getattr(history, "h_outlet", None)
        if recorded_h:
            # the enthalpy the component actually handed downstream
            h_kj[name] = [h * J_PER_KG_TO_KJ_PER_KG for h in recorded_h[:n_tsteps]]
        else:
            h_kj[name] = [
                FluidState.with_PT(fluid_name, p, t, backend).H * J_PER_KG_TO_KJ_PER_KG
                for t, p in zip(history.T_outlet[:n_tsteps], history.P_outlet[:n_tsteps], strict=False)
            ]
        p_bar[name] = [p * PA_TO_BAR for p in history.P_outlet[:n_tsteps]]

    # Second pass: every component's outlet is known now, including the
    # upstream neighbor of the loop's first component.
    for i, (name, comp) in enumerate(outer_order):
        pump_power = getattr(comp.history, "pump_power_watts", None)  # type: ignore[attr-defined]  # see above
        if name not in profiles or not pump_power:
            continue
        upstream_name, upstream = outer_order[i - 1]
        upstream_key = "outlet" if upstream is component else upstream_name
        pumped[name] = [pump_power[t] > 0 for t in range(n_tsteps)]
        for t in range(n_tsteps):
            if pumped[name][t]:
                profile_h, profile_p = profiles[name][t]
                profiles[name][t] = (
                    [h_kj[upstream_key][t], *profile_h],
                    [p_bar[upstream_key][t], *profile_p],
                )

    # Consecutive pairs around the full outer loop, entering/exiting the
    # surface plant via its own "inlet"/"outlet" keys instead of its bare
    # component name (which has no state of its own -- it's a whole
    # sub-network, not a single point).
    keyed_order = [("inlet", "outlet") if comp is component else (name, name) for name, comp in outer_order]
    return [(keyed_order[i][1], keyed_order[(i + 1) % len(keyed_order)][0]) for i in range(len(keyed_order))]


def _raft_segment_profiles(
    loop: RaftGroupedSubsurface,
    t: int,
) -> list[tuple[list[float], list[float]]]:
    """RAFT's recorded ``(h [kJ/kg], P [bar])`` profile in year ``t``, split into the loop's three segments.

    RAFT's well runs from the injection wellhead to the production wellhead;
    it is split at the nodes nearest the segment boundaries (the alignment
    corners, which the mesh has nodes at), and each boundary node ends one
    segment and starts the next, so the three lines join.
    """
    history = loop.raft.history
    s_nodes = history.s_nodes[t]
    h = [value * J_PER_KG_TO_KJ_PER_KG for value in history.h_nodes[t]]
    p = [value * PA_TO_BAR for value in history.P_nodes[t]]
    lengths = [segment.well_length for segment in loop.segments()]
    boundaries = [0.0, lengths[0], lengths[0] + lengths[1], sum(lengths)]
    indices = [_nearest_index(s_nodes, boundary) for boundary in boundaries]
    return [
        (h[start : end + 1], p[start : end + 1]) for start, end in zip(indices, indices[1:], strict=False)
    ]


def _nearest_index(values: list[float], target: float) -> int:
    """Index of the entry of ``values`` closest to ``target``."""
    return min(range(len(values)), key=lambda i: abs(values[i] - target))


def _build_figure(
    wf: Workflow,
    component: GraphSurface,
    fluid_name: str,
    node_names: list[str],
    dt_years: float,
    property_lines: PropertyLineConfig | None = None,
    config_name: str | None = None,
) -> go.Figure:
    """Build one fluid's P-h figure: saturation dome, reference lines, and a year slider over node states.

    The plot title names the config (``config_name``, typically the input
    file's stem) and the fluid, with the config's own ``title`` field
    underneath when it has one, so a saved diagram identifies its source.

    The dome, reference lines, and legend entries are static: they're the
    base figure's first traces and no animation frame touches them. Each
    frame carries only the per-edge traces plus the state-number labels and
    names their indices explicitly (``go.Frame(traces=...)``), so a frame
    can never shift onto -- or leave stale -- a trace it doesn't own.

    Every state point is numbered in flow order (``_state_point_order``),
    and a "State points" key under the plot maps each number to its node.
    The figure opens on the final year.
    """
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

    profiles: dict[str, list[tuple[list[float], list[float]]]] = {}
    pumped: dict[str, list[bool]] = {}
    if fluid_name == component.common.fluid_name:
        edges += _add_subsurface_points(wf, component, backend, n_tsteps, h_kj, p_bar, profiles, pumped)

    h_dome, p_dome = _dome_xy(fluid_name, backend)

    # Explicit axis ranges rather than relying on autorange: Plotly.js's
    # log-scale autorange combined with animation frames has a real
    # rendering bug (confirmed empirically -- the real data here spans
    # 0.006-500 bar, but autorange alone produced a y-axis up to 10^112,
    # crushing every real point into an unreadable sliver). Padding is a
    # fixed multiplicative/additive margin, not tied to any specific
    # config's own numbers. Computed BEFORE the frames loop and set on
    # EVERY frame's own layout (not just the base figure's) -- a
    # ``redraw: true`` frame transition can recompute the axis range from
    # scratch even when the base layout says ``autorange: false``, which
    # is why the blowup could reappear on some slider positions but not
    # others (Chad, 2026-09-28).
    #
    # The ranges frame the CYCLE, not the whole saturation dome: the dome
    # runs down to the triple point (~1e-4 bar for R245fa), and fitting it
    # squeezed a 1-5 bar ORC cycle into a sliver. Pressure spans the cycle's
    # nodes and the critical point (so the top of the dome shows), with a
    # factor-of-2 margin below and 1.5 above; enthalpy spans the cycle plus
    # whatever part of the dome falls inside that pressure range and within
    # half the cycle's own enthalpy span of it. Without that last limit an
    # all-liquid water loop (~200-600 kJ/kg) was stretched to the dome's
    # ~2800 kJ/kg vapor side and drawn as a sliver.
    cycle_h = [v for series in h_kj.values() for v in series]
    cycle_p = [v for series in p_bar.values() for v in series]
    for yearly in profiles.values():
        for profile_h, profile_p in yearly:
            cycle_h += profile_h
            cycle_p += profile_p
    p_crit_bar = CP.AbstractState(backend, fluid_name).trivial_keyed_output(CP.iP_critical) * PA_TO_BAR
    p_low = min(cycle_p) / 2.0
    p_high = max(max(cycle_p), p_crit_bar) * 1.5
    dome_margin = 0.5 * (max(cycle_h) - min(cycle_h))
    framed_h = cycle_h + [
        h
        for h, p in zip(h_dome, p_dome, strict=True)
        if p_low <= p <= p_high and min(cycle_h) - dome_margin <= h <= max(cycle_h) + dome_margin
    ]
    h_min, h_max = min(framed_h), max(framed_h)
    xaxis_range = [h_min - 0.05 * (h_max - h_min), h_max + 0.05 * (h_max - h_min)]
    yaxis_range = [np.log10(p_low), np.log10(p_high)]

    static_traces = [
        *_phase_legend_traces(xaxis_range[0], float(10 ** yaxis_range[0])),
        _dome_trace(fluid_name, h_dome, p_dome),
        *_property_line_traces(
            fluid_name,
            backend,
            property_lines or PropertyLineConfig(),
            h_kj,
            p_bar,
            (10 ** yaxis_range[0], 10 ** yaxis_range[1]),
            (xaxis_range[0], xaxis_range[1]),
        ),
    ]
    numbered = _state_point_order(edges, list(h_kj))
    static_traces += _state_key_traces(numbered, xaxis_range[0], float(10 ** yaxis_range[0]))
    # One trace per straight edge, 1 + len(_PROFILE_LINE_COLORS) per profiled
    # edge (see _profile_traces), then the numbered-label trace last; the
    # count is the same every year, as the slider's frames require.
    n_frame_traces = (
        sum(1 + len(_PROFILE_LINE_COLORS) if target in profiles else 1 for _, target in edges) + 1
    )
    frame_trace_indices = list(range(len(static_traces), len(static_traces) + n_frame_traces))

    frames = []
    for t in range(n_tsteps):
        frame_traces = []
        for source, target in edges:
            if target in profiles:
                profile_h, profile_p = profiles[target][t]
                frame_traces += _profile_traces(
                    source,
                    target,
                    profile_h,
                    profile_p,
                    _segment_colors(fluid_name, backend, profile_h, profile_p),
                    pumped=pumped.get(target, [False] * n_tsteps)[t],
                )
                continue
            h_s, h_t = h_kj[source][t], h_kj[target][t]
            p_s, p_t = p_bar[source][t], p_bar[target][t]
            # Colored by the phase at the line's midpoint (P midpointed in
            # log space, as the axis is drawn): an endpoint sitting exactly
            # on the saturation curve -- a pump's saturated-liquid suction,
            # a turbine's saturated-vapor inlet -- would otherwise color the
            # whole process two-phase.
            mid_p = float(np.sqrt(p_s * p_t)) if p_s > 0 and p_t > 0 else (p_s + p_t) / 2
            color = _phase_color(fluid_name, (h_s + h_t) / 2, mid_p, backend)
            frame_traces.append(
                go.Scatter(
                    x=[h_s, h_t],
                    y=[p_s, p_t],
                    mode="lines+markers",
                    line={"color": color},
                    marker={"color": color, "size": 6},
                    showlegend=False,
                    name=f"{source} -> {target}",
                    # Explicit hover text: the default hover only showed raw
                    # (h, P) coordinates with no indication of which node or
                    # edge they belonged to -- impossible to trace a line
                    # back to its endpoints once zoomed in (Chad, 2026-09-25).
                    # hovertext is per-POINT (which specific node this end
                    # is), <extra> is the edge as a whole.
                    hovertext=[source, target],
                    hovertemplate="<b>%{hovertext}</b><br>h=%{x:.1f} kJ/kg<br>P=%{y:.4g} bar<extra>%{fullData.name}</extra>",
                ),
            )
        frame_traces.append(_state_number_trace(numbered, h_kj, p_bar, t, xaxis_range, yaxis_range))
        frame_layout = {
            "xaxis": {"range": xaxis_range, "autorange": False},
            "yaxis": {"range": yaxis_range, "autorange": False, "type": "log"},
        }
        frames.append(
            go.Frame(data=frame_traces, traces=frame_trace_indices, layout=frame_layout, name=str(t)),
        )

    fig = go.Figure(data=[*static_traces, *(frames[-1].data if frames else [])], frames=frames)

    fig.update_layout(
        title=_figure_title(wf, fluid_name, config_name),
        xaxis_title="Specific enthalpy h [kJ/kg]",
        xaxis_range=xaxis_range,
        xaxis_autorange=False,
        yaxis_title="Pressure P [bar]",
        yaxis_type="log",
        yaxis_range=yaxis_range,
        yaxis_autorange=False,
        # The State points key sits under the plot, below the slider.
        legend2={
            "title": {"text": "State points"},
            "orientation": "h",
            "x": 0,
            "xanchor": "left",
            "y": -0.27,
            "yanchor": "top",
            "itemclick": False,
            "itemdoubleclick": False,
        },
        margin={"b": 160},
        sliders=[
            {
                # Start on the last year, which is what the base figure
                # shows before the slider is touched.
                "active": max(n_tsteps - 1, 0),
                "steps": [
                    {
                        "args": [
                            [str(t)],
                            {"frame": {"duration": 0, "redraw": True}, "mode": "immediate"},
                        ],
                        "label": f"{t * dt_years:.0f}",
                        "method": "animate",
                    }
                    for t in range(n_tsteps)
                ],
                "currentvalue": {"prefix": "Elapsed time (years): "},
            },
        ],
    )
    return fig


def _figure_title(wf: Workflow, fluid_name: str, config_name: str | None) -> str:
    """``<config> — <fluid> P–h phase diagram``, with the config's own ``title`` as a smaller second line."""
    heading = (
        f"{config_name} — {fluid_name} P–h phase diagram"
        if config_name
        else f"{fluid_name} — P–h phase diagram"
    )
    config_title = wf.to_dict().get("title")
    return f"{heading}<br><sup>{config_title}</sup>" if config_title else heading


def _segment_colors(
    fluid_name: str,
    backend: str,
    profile_h: list[float],
    profile_p: list[float],
) -> list[str]:
    """Phase color of each stretch between consecutive profile nodes, at its midpoint.

    Same rule as a straight edge (P midpointed in log space, as the axis is
    drawn), so a well that crosses the critical pressure or the saturation
    curve changes color where it crosses, not at one color for the whole
    well.
    """
    colors = []
    for h_a, h_b, p_a, p_b in zip(profile_h, profile_h[1:], profile_p, profile_p[1:], strict=False):
        mid_p = float(np.sqrt(p_a * p_b)) if p_a > 0 and p_b > 0 else (p_a + p_b) / 2
        try:
            colors.append(_phase_color(fluid_name, (h_a + h_b) / 2, mid_p, backend))
        except ValueError:
            colors.append(_PHASE_COLOR_FALLBACK)
    return colors


_PROFILE_LINE_COLORS: tuple[str, ...] = tuple(_PHASE_LEGEND)
"""Every phase color, in legend order: a profiled edge gets one line trace per color (see ``_profile_traces``)."""


def _profile_traces(
    source: str,
    target: str,
    profile_h: list[float],
    profile_p: list[float],
    segment_colors: list[str],
    *,
    pumped: bool = False,
) -> list[go.Scatter]:
    """One edge drawn as a component's marched (h, P) profile, each stretch in its own phase's color.

    A Plotly line has one color, so the profile is the hoverable point trace
    from ``_profile_trace`` (line hidden, markers colored by phase) plus one
    line trace per color in ``_PROFILE_LINE_COLORS``, holding only that
    color's stretches. Consecutive stretches of a color share their node;
    separate runs of one color are split by a gap, so no line is drawn
    across a stretch of another phase. A color the profile never has gets an
    empty trace, keeping the trace count the same every year.
    """
    line_traces = []
    for color in _PROFILE_LINE_COLORS:
        xs: list[float | None] = []
        ys: list[float | None] = []
        for k, segment_color in enumerate(segment_colors):
            if segment_color != color:
                continue
            if k == 0 or segment_colors[k - 1] != color:
                if xs:
                    xs.append(None)
                    ys.append(None)
                xs.append(profile_h[k])
                ys.append(profile_p[k])
            xs.append(profile_h[k + 1])
            ys.append(profile_p[k + 1])
        line_traces.append(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                line={"color": color},
                connectgaps=False,
                hoverinfo="skip",
                showlegend=False,
                name=f"{source} -> {target} ({_PHASE_LEGEND[color]})",
            ),
        )
    point_colors = (
        [*segment_colors, segment_colors[-1]] if segment_colors else [_PHASE_COLOR_FALLBACK] * len(profile_h)
    )
    return [_profile_trace(source, target, profile_h, profile_p, point_colors, pumped=pumped), *line_traces]


def _profile_trace(
    source: str,
    target: str,
    profile_h: list[float],
    profile_p: list[float],
    point_colors: list[str],
    *,
    pumped: bool = False,
) -> go.Scatter:
    """One edge drawn as a component's marched (h, P) profile: its points, for hover; the lines are drawn by ``_profile_traces``.

    Starts at the component's OWN first node, not at the upstream point:
    if the two disagree (a state lost across the component boundary), the
    gap stays visible instead of being bridged by a line that looks like a
    process. The one exception is ``pumped``: the profile's first point is
    then the pump suction (see ``_add_subsurface_points``) and its second
    the pump discharge, where the march begins.
    """
    n = len(profile_h)
    sizes = [0] * n
    sizes[0] = sizes[-1] = 6
    first_node = 1 if pumped else 0
    hovertext = [f"{target} node {i - first_node}/{n - 1 - first_node}" for i in range(n)]
    hovertext[0] = f"{target} inlet (pump suction)" if pumped else f"{target} inlet"
    if pumped:
        sizes[1] = 6
        hovertext[1] = f"{target} pump discharge"
    hovertext[-1] = target
    return go.Scatter(
        x=profile_h,
        y=profile_p,
        mode="lines+markers",
        line={"color": "rgba(0, 0, 0, 0)"},
        marker={"color": point_colors, "size": sizes},
        showlegend=False,
        name=f"{source} -> {target}",
        hovertext=hovertext,
        hovertemplate="<b>%{hovertext}</b><br>h=%{x:.1f} kJ/kg<br>P=%{y:.4g} bar<extra>%{fullData.name}</extra>",
    )


def _state_point_order(edges: list[tuple[str, str]], keys: list[str]) -> list[str]:
    """State-point keys in flow order, for numbering them 1, 2, 3, ...

    Walks the edges downstream from ``inlet`` (the geofluid entering the
    surface plant) or, for a fluid with no ``inlet`` (an ORC's working
    fluid), from the first edge's source. Points the walk never reaches are
    appended in their original order, so every point gets a number.
    """
    downstream: dict[str, list[str]] = {}
    for source, target in edges:
        downstream.setdefault(source, []).append(target)
    if "inlet" in keys:
        start = "inlet"
    elif edges:
        start = edges[0][0]
    else:
        return list(keys)
    order: list[str] = []
    stack = [start]
    while stack:
        key = stack.pop()
        if key in order or key not in keys:
            continue
        order.append(key)
        stack.extend(reversed(downstream.get(key, [])))
    return order + [key for key in keys if key not in order]


def _state_number_trace(
    numbered: list[str],
    h_kj: dict[str, list[float]],
    p_bar: dict[str, list[float]],
    t: int,
    xaxis_range: list[float],
    yaxis_range: list[float],
) -> go.Scatter:
    """Each state point's number, drawn next to its marker for year ``t``.

    Points within ``_LABEL_MERGE_FRACTION`` of the plot's width and height
    of each other share one label (e.g. ``"9, 1"``), so a component that
    passes a state straight through, or a short surface pipe, doesn't print
    two numbers on top of each other. ``yaxis_range`` is in log10(bar), as
    the axis is drawn.
    """
    h_tol = _LABEL_MERGE_FRACTION * (xaxis_range[1] - xaxis_range[0])
    logp_tol = _LABEL_MERGE_FRACTION * (yaxis_range[1] - yaxis_range[0])
    groups: list[tuple[float, float, list[str]]] = []
    for i, key in enumerate(numbered, start=1):
        h, p = h_kj[key][t], p_bar[key][t]
        log_p = float(np.log10(p)) if p > 0 else yaxis_range[0]
        for group_h, group_log_p, numbers in groups:
            if abs(h - group_h) <= h_tol and abs(log_p - group_log_p) <= logp_tol:
                numbers.append(str(i))
                break
        else:
            groups.append((h, log_p, [str(i)]))
    return go.Scatter(
        x=[h for h, _, _ in groups],
        y=[10**log_p for _, log_p, _ in groups],
        text=[", ".join(numbers) for _, _, numbers in groups],
        mode="text",
        textposition="top right",
        textfont={"size": 12, "color": "black"},
        showlegend=False,
        name="State numbers",
        hoverinfo="skip",
    )


def _state_key_traces(numbered: list[str], h_anchor: float, p_anchor: float) -> list[go.Scatter]:
    """One legend entry per state point, ``"<number>  <node>"``, in the separate ``legend2`` key.

    Same invisible single-point trick as ``_phase_legend_traces``, with a
    transparent line so the entry shows only its text.
    """
    return [
        go.Scatter(
            x=[h_anchor],
            y=[p_anchor],
            mode="lines",
            line={"color": "rgba(0, 0, 0, 0)", "width": 0},
            name=f"{i}  {key}",
            legend="legend2",
            hoverinfo="skip",
        )
        for i, key in enumerate(numbered, start=1)
    ]


def _phase_color(fluid_name: str, h_kj_val: float, p_bar_val: float, backend: str) -> str:
    """Line/marker color for the thermodynamic phase at one (h, P) point (Chad's request, 2026-09-25)."""
    state = CP.AbstractState(backend, fluid_name)
    state.update(CP.HmassP_INPUTS, h_kj_val / J_PER_KG_TO_KJ_PER_KG, p_bar_val / PA_TO_BAR)
    return _PHASE_COLORS.get(state.phase(), _PHASE_COLOR_FALLBACK)


def _dome_xy(fluid_name: str, backend: str) -> tuple[list[float], list[float]]:
    """Sweep the saturation dome (liquid + vapor branches, triple point to critical point).

    The expensive part of tracing the dome (a real CoolProp property
    lookup per point) -- called ONCE per figure and cached by
    ``_dome_trace``'s caller, not once per timestep frame (a figure with
    ``n_tsteps`` frames doesn't need ``n_tsteps`` identical dome sweeps).
    """
    T_crit = CP.AbstractState(backend, fluid_name).trivial_keyed_output(CP.iT_critical)
    h_liquid, p_liquid = _saturation_branch(fluid_name, backend, 0.0, _N_DOME_POINTS)
    h_vapor, p_vapor = _saturation_branch(fluid_name, backend, 1.0, _N_DOME_POINTS)
    crit = CP.AbstractState(backend, fluid_name)
    crit.update(CP.QT_INPUTS, 0.5, T_crit * (1 - 1e-6))
    h_c = crit.hmass() * J_PER_KG_TO_KJ_PER_KG
    p_c = crit.p() * PA_TO_BAR

    h_dome = [*h_liquid, h_c, *reversed(h_vapor)]
    p_dome = [*p_liquid, p_c, *reversed(p_vapor)]
    return h_dome, p_dome


def _saturation_branch(
    fluid_name: str,
    backend: str,
    quality: float,
    n_points: int,
) -> tuple[list[float], list[float]]:
    """(h [kJ/kg], P [bar]) along constant vapor ``quality``, triple point up to (not including) the critical point."""
    state = CP.AbstractState(backend, fluid_name)
    T_triple = state.trivial_keyed_output(CP.iT_triple)
    T_crit = state.trivial_keyed_output(CP.iT_critical)
    h_vals: list[float] = []
    p_vals: list[float] = []
    for T in np.linspace(T_triple, T_crit, n_points)[:-1]:
        try:
            state.update(CP.QT_INPUTS, quality, T)
        except ValueError:
            continue
        h_vals.append(state.hmass() * J_PER_KG_TO_KJ_PER_KG)
        p_vals.append(state.p() * PA_TO_BAR)
    return h_vals, p_vals


def _round_multiples(low: float, high: float, step: float) -> list[float]:
    start = np.ceil(low / step) * step
    return [round(float(v), 10) for v in np.arange(start, high + step * 1e-9, step)]


def _round_significant(value: float, digits: int = 1) -> float:
    return float(round(value, digits - 1 - int(np.floor(np.log10(abs(value))))))


def _resolve_line_values(spec: LineSpec, observed: list[float], *, log: bool = False) -> list[float]:
    """Explicit values as given, or about ``spec`` round-numbered values across the ``observed`` range.

    Linear families get multiples of a round step (1, 2, 2.5, or 5 times a
    power of ten); logarithmic ones get log-spaced values rounded to one
    significant figure. Rounding means the count can differ from ``spec``
    by one or two -- readable labels matter more than an exact count.
    """
    if not isinstance(spec, int):
        return list(spec)
    finite = [v for v in observed if np.isfinite(v) and (v > 0 or not log)]
    if spec == 0 or not finite:
        return []
    low, high = min(finite), max(finite)
    if low == high:
        return [_round_significant(low, 2) if low else 0.0]
    if log:
        return sorted({_round_significant(float(v)) for v in np.geomspace(low, high, spec)})
    # every 1/2/2.5/5 x 10^k step near the even spacing; keep the one whose count is closest to spec
    magnitude = 10 ** np.floor(np.log10((high - low) / max(spec, 1)))
    candidates = [_round_multiples(low, high, m * magnitude) for m in (0.5, 1, 2, 2.5, 5, 10)]
    return min(candidates, key=lambda values: (abs(len(values) - spec), -len(values)))


def _isobaric_sweep(
    fluid_name: str,
    backend: str,
    input_pair: int,
    value: float,
    pressures_pa: npt.NDArray[np.float64],
    *,
    value_first: bool,
) -> tuple[list[float], list[float]]:
    """(h [kJ/kg], P [bar]) holding one property fixed while sweeping pressure; failed points are skipped."""
    state = CP.AbstractState(backend, fluid_name)
    h_vals: list[float] = []
    p_vals: list[float] = []
    for pressure in pressures_pa:
        try:
            state.update(input_pair, *((value, pressure) if value_first else (pressure, value)))
        except ValueError:
            continue
        h_vals.append(state.hmass() * J_PER_KG_TO_KJ_PER_KG)
        p_vals.append(pressure * PA_TO_BAR)
    return h_vals, p_vals


def _isotherm(
    fluid_name: str,
    backend: str,
    temperature_K: float,
    pressures_pa: npt.NDArray[np.float64],
) -> tuple[list[float], list[float]]:
    """(h, P) along one isotherm, highest pressure first.

    Below the critical temperature the isotherm is flat across the dome
    (constant saturation pressure from saturated liquid to saturated
    vapor), where (T, P) can't fix the state -- so the pressure sweep
    skips that pressure and the two saturation end points are inserted
    explicitly.
    """
    state = CP.AbstractState(backend, fluid_name)
    T_crit = state.trivial_keyed_output(CP.iT_critical)
    T_triple = state.trivial_keyed_output(CP.iT_triple)
    descending = np.sort(pressures_pa)[::-1]
    if not T_triple < temperature_K < T_crit:
        return _isobaric_sweep(
            fluid_name,
            backend,
            CP.PT_INPUTS,
            temperature_K,
            descending,
            value_first=False,
        )
    state.update(CP.QT_INPUTS, 0.0, temperature_K)
    p_sat, h_liquid = state.p(), state.hmass()
    state.update(CP.QT_INPUTS, 1.0, temperature_K)
    h_vapor = state.hmass()
    above = descending[descending > p_sat * (1 + 1e-6)]
    below = descending[descending < p_sat * (1 - 1e-6)]
    h_hi, p_hi = _isobaric_sweep(fluid_name, backend, CP.PT_INPUTS, temperature_K, above, value_first=False)
    h_lo, p_lo = _isobaric_sweep(fluid_name, backend, CP.PT_INPUTS, temperature_K, below, value_first=False)
    sat_h = [h_liquid * J_PER_KG_TO_KJ_PER_KG, h_vapor * J_PER_KG_TO_KJ_PER_KG]
    # Physical guard: above saturation pressure the state is compressed liquid,
    # below it superheated vapor. A point well inside the dome is an
    # interpolation artifact (tabular backends, just off saturation), not
    # physics. Compressed liquid sits slightly ABOVE saturated-liquid enthalpy
    # at high pressure, so the liquid bound allows a quarter of the dome width.
    latent = sat_h[1] - sat_h[0]
    liquid = [(h, p) for h, p in zip(h_hi, p_hi, strict=True) if h <= sat_h[0] + 0.25 * latent]
    vapor = [(h, p) for h, p in zip(h_lo, p_lo, strict=True) if h >= sat_h[1] - 1e-3 * latent]
    h_hi, p_hi = [h for h, _ in liquid], [p for _, p in liquid]
    h_lo, p_lo = [h for h, _ in vapor], [p for _, p in vapor]
    sat_p = [p_sat * PA_TO_BAR] * 2
    return [*h_hi, *sat_h, *h_lo], [*p_hi, *sat_p, *p_lo]


def _property_line_traces(
    fluid_name: str,
    backend: str,
    config: PropertyLineConfig,
    h_kj: dict[str, list[float]],
    p_bar: dict[str, list[float]],
    pressure_range_bar: tuple[float, float],
    enthalpy_range_kj: tuple[float, float],
) -> list[go.Scatter]:
    """Static reference-line traces (isotherms, isentropes, isochores, quality lines) for one fluid.

    Count-based specs are spread across the temperatures/entropies/
    densities of the plotted node states (every node, every year), so the
    lines land where the cycle actually is. Each family is one legend
    group: clicking its legend entry toggles all of its lines and labels.
    Lines are computed with ``_REFERENCE_LINE_BACKEND``; ``backend`` (the
    simulation's own) is only used to read the plotted node states.

    Labels are a text-only trace per family (not ``layout.annotations``):
    a subcritical isotherm is labeled at its saturated-vapor corner (where
    its flat run across the dome meets the vapor branch -- these sit at
    different pressures, so labels don't pile up the way they do at the
    bottom edge, where low-pressure vapor isotherms all end); other lines
    at their right-most visible point, quality lines at their lowest.
    """
    state = CP.AbstractState(backend, fluid_name)
    temperatures, entropies, densities = [], [], []
    for name in h_kj:
        for h, p in zip(h_kj[name], p_bar[name], strict=False):
            try:
                state.update(CP.HmassP_INPUTS, h / J_PER_KG_TO_KJ_PER_KG, p / PA_TO_BAR)
            except ValueError:
                continue
            temperatures.append(state.T())
            entropies.append(state.smass() / 1000.0)
            densities.append(state.rhomass())

    # Below the triple-point pressure there's no liquid or two-phase state,
    # and CoolProp's answers there are meaningless, so the sweep stops at it.
    line_backend = _REFERENCE_LINE_BACKEND
    p_triple_bar = CP.AbstractState(line_backend, fluid_name).trivial_keyed_output(CP.iP_triple) * PA_TO_BAR
    low_bar = max(pressure_range_bar[0], p_triple_bar)
    pressures_pa = np.geomspace(low_bar, pressure_range_bar[1], _N_PROPERTY_LINE_POINTS) / PA_TO_BAR

    if isinstance(config.isotherm_temperatures_kelvin, int):
        # pick round values in °C, the unit the labels are read in
        celsius = _resolve_line_values(
            config.isotherm_temperatures_kelvin,
            [T - 273.15 for T in temperatures],
        )
        isotherm_values = [c + 273.15 for c in celsius]
    else:
        isotherm_values = list(config.isotherm_temperatures_kelvin)

    # (hover label, on-plot label, (h, P))
    families: dict[str, list[tuple[str, str, tuple[list[float], list[float]]]]] = {
        "isotherm_temperatures_kelvin": [
            (
                f"T = {T:.2f} K ({T - 273.15:.1f} °C)",
                f"{T - 273.15:g}°C",
                _isotherm(fluid_name, line_backend, T, pressures_pa),
            )
            for T in isotherm_values
        ],
        "isentrope_entropies_kj_per_kg_kelvin": [
            (
                f"s = {s_val:.4g} kJ/(kg·K)",
                f"s={s_val:g}",
                _isobaric_sweep(
                    fluid_name,
                    line_backend,
                    CP.PSmass_INPUTS,
                    s_val * 1000.0,
                    pressures_pa,
                    value_first=False,
                ),
            )
            for s_val in _resolve_line_values(config.isentrope_entropies_kj_per_kg_kelvin, entropies)
        ],
        "isochore_densities_kg_per_m3": [
            (
                f"ρ = {rho:.4g} kg/m³",
                f"ρ={rho:g}",
                _isobaric_sweep(
                    fluid_name,
                    line_backend,
                    CP.DmassP_INPUTS,
                    rho,
                    pressures_pa,
                    value_first=True,
                ),
            )
            for rho in _resolve_line_values(config.isochore_densities_kg_per_m3, densities, log=True)
        ],
        "qualities": [
            (
                f"x = {q:.2f}",
                f"x={q:g}",
                _saturation_branch(fluid_name, line_backend, q, _N_PROPERTY_LINE_POINTS),
            )
            for q in (
                [float(v) for v in np.linspace(0, 1, config.qualities + 2)[1:-1]]
                if isinstance(config.qualities, int)
                else config.qualities
            )
        ],
    }

    h_low, h_high = enthalpy_range_kj
    p_low, p_high = pressure_range_bar
    traces = []
    for key, lines in families.items():
        group_label, dash, rgb = _PROPERTY_LINE_STYLES[key]
        label_h: list[float] = []
        label_p: list[float] = []
        label_text: list[str] = []
        label_positions: list[str] = []
        shown_in_legend = False
        for hover_label, plot_label, (h_vals, p_vals) in lines:
            if len(h_vals) < 2:
                continue
            traces.append(
                go.Scatter(
                    x=h_vals,
                    y=p_vals,
                    mode="lines",
                    line={"color": f"rgba({rgb}, {_PROPERTY_LINE_OPACITY})", "dash": dash, "width": 1.2},
                    name=group_label,
                    legendgroup=group_label,
                    showlegend=not shown_in_legend,
                    hovertemplate=(
                        f"<b>{hover_label}</b><br>h=%{{x:.1f}} kJ/kg<br>P=%{{y:.4g}} bar<extra>{group_label}</extra>"
                    ),
                ),
            )
            shown_in_legend = True
            visible = [
                (h, p)
                for h, p in zip(h_vals, p_vals, strict=True)
                if h_low <= h <= h_high and p_low <= p <= p_high
            ]
            corners = [
                (h_vals[i + 1], p_vals[i + 1])
                for i in range(len(p_vals) - 1)
                if key == "isotherm_temperatures_kelvin" and p_vals[i] == p_vals[i + 1]
            ]
            visible_corners = [c for c in corners if c in visible]
            if visible_corners:
                anchor = visible_corners[0]
            elif visible:
                anchor = min(visible, key=lambda point: point[1]) if key == "qualities" else max(visible)
            else:
                continue
            label_h.append(anchor[0])
            label_p.append(anchor[1])
            label_text.append(plot_label)
            label_positions.append(
                _label_position(key, anchor[1], pressure_range_bar, at_dome_corner=bool(visible_corners)),
            )
        if label_text:
            traces.append(
                go.Scatter(
                    x=label_h,
                    y=label_p,
                    mode="text",
                    text=label_text,
                    textposition=label_positions,
                    textfont={"color": f"rgb({rgb})", "size": 11},
                    legendgroup=group_label,
                    showlegend=False,
                    hoverinfo="skip",
                    name=f"{group_label} labels",
                    # a label right at the plot edge may overhang it slightly; don't cut it off
                    cliponaxis=False,
                ),
            )
    return traces


def _label_position(
    key: str,
    anchor_p_bar: float,
    pressure_range_bar: tuple[float, float],
    *,
    at_dome_corner: bool,
) -> str:
    """Plotly ``textposition`` for one reference-line label, keeping the text inside the plot.

    A label anchored where its line leaves the TOP of the plot (steep lines:
    isentropes, liquid-density isochores) goes below its anchor -- centered
    on it, the upper half of the text would sit outside the plot area.
    """
    if at_dome_corner:
        return "middle right"
    low, high = np.log10(pressure_range_bar[0]), np.log10(pressure_range_bar[1])
    if (np.log10(anchor_p_bar) - low) / (high - low) > _TOP_EDGE_FRACTION:
        return "bottom left"
    return _LABEL_POSITIONS.get(key, "middle left")


def _dome_trace(fluid_name: str, h_dome: list[float], p_dome: list[float]) -> go.Scatter:
    """Build a fresh Scatter trace from an already-computed dome sweep (cheap -- no CoolProp calls)."""
    return go.Scatter(
        x=h_dome,
        y=p_dome,
        mode="lines",
        line={"color": "black", "width": 1},
        fill="toself",
        fillcolor=_DOME_FILL_COLOR,
        name=f"{fluid_name} saturation dome",
        hoverinfo="skip",
    )


def _phase_legend_traces(h_anchor: float, p_anchor: float) -> list[go.Scatter]:
    """One invisible single-point line trace per phase color, purely to populate the legend.

    Per-edge traces themselves set ``showlegend=False`` (there'd otherwise
    be one legend entry per edge, not per phase) -- these standalone
    traces are what actually tells the reader what each color means.
    They're static traces that no frame touches, so the legend stays put
    when the year slider swaps frames.

    Each trace holds one real, in-range point (``h_anchor``, ``p_anchor``,
    the axes' lower corner) in ``lines`` mode, so nothing is drawn on the
    plot (a line needs two points) while the legend shows a line sample in
    the phase color, matching the edges themselves. Plotly leaves a trace
    with no data out of the legend entirely, and a ``None`` point on a
    log-scale axis can upset the axis range.
    """
    return [
        go.Scatter(
            x=[h_anchor],
            y=[p_anchor],
            mode="lines",
            line={"color": color, "width": 3},
            name=label,
            hoverinfo="skip",
        )
        for color, label in _PHASE_LEGEND.items()
    ]
