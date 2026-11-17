# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""SystemDirect — single-pass orchestrator for tango.

Auto-selected when sim_config.injection_mode is absent — i.e. the input graph
declares no boundary-condition variable to solve for (e.g. a bare wellbore
test fixture). Executes each component exactly once per timestep, in
component_idx order, wiring each component's outlet into its downstream
neighbor's inlet immediately after it solves.

The run advances one sync interval at a time (see
``tango_core.core.time_stepping``). With a single subsystem, every step is
its own interval. With several, each subsystem takes its own steps through
the interval in circuit order, and a stream passing into another subsystem
is collected over the sender's steps and handed to each of the receiver's
steps through the edge's ``SyncRule`` (``sync_stream``). A stream that
wraps around the circuit, from the last subsystem back to the first,
reaches the first subsystem in the next interval, the same one-pass lag
as between two steps of a single subsystem.

This is also the base class for SystemBCIteration (see that module's
docstring). SystemDirect owns the only implementation of "one circuit pass"
and "loop over timesteps" — SystemBCIteration reuses both via inheritance
instead of re-implementing them. The choice between the two orchestrator
classes is a topology question (does this graph declare a BC-iteration
circuit at all); InjectionPolicy is the sole authority over how many passes
a single sync interval takes once that topology choice has been made.
"""

from __future__ import annotations

from tango_core.components.economic.base import EconomicComponent
from tango_core.core.component import FlowComponent
from tango_core.core.errors import ConfigError, CoolPropError
from tango_core.core.orchestrator import Orchestrator
from tango_core.core.stream import Stream
from tango_core.core.time_stepping import SyncInterval, SyncRule, TimeStep, TimeStepping, sync_stream


class SystemDirect(Orchestrator):
    """Single-pass orchestrator: one circuit pass per timestep, no BC concept.

    Also the base class for SystemBCIteration — see module docstring.
    """

    def __init__(
        self,
        components: dict[str, FlowComponent],
        time_stepping: TimeStepping,
        economic: EconomicComponent | None = None,
    ) -> None:
        """Initialize, sorting components by component_idx for circuit order.

        Args:
            components: Named physical components keyed by YAML name.
            time_stepping: The run's subsystems, grids, and sync rules
                (``SimConfig.time_stepping_for()``); every component is in
                exactly one subsystem.
            economic: Optional economic component (from the ``economic:``
                YAML block). Deliberately kept OUT of ``components``/
                ``_ordered``/``_by_idx`` — it must run exactly once, after
                every physical timestep completes (see ``finalize()``), not
                once per timestep like every other component. See
                ``DoubletEconomicComponent``'s module docstring for why it
                can't just be component_idx N+1 in the per-timestep loop.

        Raises:
            ConfigError: A subsystem is not a contiguous run of
                ``component_idx``, a ``sync`` rule names an edge the
                circuit does not have, or a component that keeps external
                state takes more than one step in a sync interval.

        """
        self._components = components
        self.intervals: list[SyncInterval] = time_stepping.intervals()
        """The run's sync intervals, in order; each pass of ``run()`` solves one."""
        self._economic = economic

        # Sort components by component_idx for deterministic solve order.
        self._ordered: list[FlowComponent] = sorted(
            components.values(),
            key=lambda c: c.component_idx,
        )
        # Build idx → component lookup for stream wiring.
        self._by_idx: dict[int, FlowComponent] = {c.component_idx: c for c in self._ordered}

        # Subsystems in circuit order, each with its components in circuit order.
        self._subsystems: list[tuple[str, list[FlowComponent]]] = sorted(
            (
                (name, sorted((components[c] for c in subsystem.components), key=lambda c: c.component_idx))
                for name, subsystem in time_stepping.subsystems.items()
            ),
            key=lambda named: named[1][0].component_idx,
        )
        _check_subsystems_contiguous(self._subsystems)
        _check_external_state_steps(self._subsystems, self.intervals)
        # The sync rule for each component fed from another subsystem, keyed by its component_idx.
        self._inlet_rules: dict[int, SyncRule] = _inlet_rules(self._subsystems, time_stepping, self._by_idx)
        # Streams sent into another subsystem this interval, with the step each was sent over,
        # keyed by the receiving component's component_idx; cleared at the start of each pass.
        self._sent: dict[int, list[tuple[TimeStep, Stream]]] = {}

        self._pending_inlets: dict[int, Stream] = {}
        """Most-recently-computed inlet ``Stream`` for each ``component_idx``,
        keyed by ``component_idx`` — this is what replaces ``inlet`` as a
        stored field (see ``FlowComponent.solve()``'s docstring
        for why ``inlet`` is a call parameter, not a field): the persisted
        "what feeds this component next" record now lives on the
        ORCHESTRATOR, which owns wiring, not on the component itself.
        Populated by ``_record_outlet()`` immediately after a component
        solves; read (via ``_next_inlet()``, falling back to an all-zero
        ``Stream`` if a component_idx was never wired — matching a
        never-wired component's implicit day-0 input under the old
        stored-field design) at the top of each pass. One dict, keyed
        generically by ``component_idx``, handles BOTH a straight-pipe edge
        (its entry is consumed later in THIS pass) and a wraparound edge —
        e.g. the surface's ``next`` pointing back to the circuit's own
        entry component_idx (consumed on the NEXT pass) — with the same
        code path; no special-casing needed for either shape.
        """

    @property
    def components(self) -> dict[str, FlowComponent]:
        """Return the named component dict."""
        return self._components

    def _next_inlet(self, component: FlowComponent) -> Stream:
        """Return the ``Stream`` to feed into ``component``'s next ``solve()`` call.

        Falls back to ``Stream.fresh()`` (all fields freshly zero) for a
        component_idx never yet wired — matching what a never-written
        ``inlet`` field defaulted to before ``inlet`` became a ``solve()``
        parameter.
        """
        return self._pending_inlets.get(component.component_idx, Stream.fresh())

    def _record_outlet(self, component: FlowComponent, outlet: Stream) -> None:
        """Copy ``outlet``, the Stream ``component.solve()`` just returned, into its downstream neighbor's next inlet.

        Stores into ``self._pending_inlets[next_idx]`` rather than writing
        directly to the downstream component (``inlet`` is no longer a
        stored field — see ``_pending_inlets``'s docstring), so this
        correctly handles a wraparound edge the same way as a straight one.

        Components without a ``next`` field in their spec (e.g. EconomicComponent)
        are silently skipped — they receive no downstream wiring.
        """
        next_idx: int | None = getattr(component, "next", None)
        if next_idx is None or next_idx not in self._by_idx:
            return
        self._pending_inlets[next_idx] = Stream.fresh(
            h=outlet.h.get_fresh(),
            P=outlet.P.get_fresh(),
            mass_rate=outlet.mass_rate.get_fresh(),
        )

    def _inlet_for(self, component: FlowComponent, step: TimeStep) -> Stream:
        """The inlet for ``component``'s solve over ``step``.

        A component fed from another subsystem that has already sent its
        streams for this interval gets them through the edge's sync rule;
        every other component gets ``_next_inlet``.
        """
        sent = self._sent.get(component.component_idx)
        if sent:
            return sync_stream(self._inlet_rules[component.component_idx], sent, step)
        return self._next_inlet(component)

    def _route_outlet(self, component: FlowComponent, outlet: Stream, step: TimeStep) -> None:
        """Wire ``outlet`` to the downstream neighbor and, if that is in another subsystem, keep it for syncing."""
        self._record_outlet(component, outlet)
        next_idx: int | None = getattr(component, "next", None)
        if next_idx in self._inlet_rules:
            self._sent.setdefault(next_idx, []).append((step, self._pending_inlets[next_idx]))

    def _after_solve(self, component: FlowComponent) -> None:
        """Hook called right after each component solves; no-op by default.

        Overridden by ``SystemBCIteration`` to hand a ``grouped_subsurface``'s
        required injection pressure to the surface plant in the same pass.
        """
        return

    def _solve_interval(self, interval: SyncInterval) -> None:
        """Solve one pass over ``interval``: each subsystem, in circuit order, through each of its steps.

        Each component's state from a step before its subsystem's last one
        in the interval is held (``hold_step_record``) for ``record()``.

        Raises:
            CoolPropError: A component's solve failed; the message names the
                component and the step.
        """
        self._sent.clear()
        for component in self._ordered:
            component.discard_held_steps()
        for name, members in self._subsystems:
            steps = interval.steps[name]
            for position, step in enumerate(steps):
                for component in members:
                    component.mark_all_stale()
                    try:
                        outlet = component.solve(self._inlet_for(component, step), step)
                    except CoolPropError as exc:
                        raise CoolPropError(
                            f"Component: {component.__class__.__name__} (component_idx "
                            f"{component.component_idx}), step from {step.t_start:.6g} s to "
                            f"{step.t_end:.6g} s\n{exc}",
                        ) from exc
                    self._route_outlet(component, outlet, step)
                    self._after_solve(component)
                if position < len(steps) - 1:
                    for component in members:
                        component.hold_step_record(step)

    def run_interval(self, i: int) -> None:
        """Execute one circuit pass over sync interval ``i``."""
        interval = self.intervals[i]
        try:
            self._solve_interval(interval)
        except CoolPropError as exc:
            raise CoolPropError(f"Sync interval: {i + 1} / {len(self.intervals)}\n{exc}") from exc

    def _after_interval(self, i: int) -> None:
        """Hook called after each sync interval in ``run()``; no-op by default.

        Overridden by SystemBCIteration to log a per-interval summary, without
        duplicating the interval loop itself.
        """
        return

    def record(self, interval: SyncInterval) -> None:
        """Record every component in the circuit for the accepted ``interval``.

        Each component records its held steps first, then its subsystem's
        last step in the interval from its live state.
        """
        for name, members in self._subsystems:
            last = interval.steps[name][-1]
            for component in members:
                component.record_held_steps()
                component.record_step(last)

    def finalize(self) -> None:
        """Run the economic component (if any) exactly once, after all timesteps.

        Called by ``run()`` after the loop over ``self.intervals``
        finishes — not once per interval like ``run_interval()``, because
        CAPEX sizing and the LCOE denominator both read the physical
        components' recorded ``history`` over the whole run (run-averaged
        turbine/pump/HX duty and net power/thermal output; see
        ``components/economic/doublet.py``), which is complete only after
        the last timestep.

        The economic component has no ``inlet``/``outlet`` (it is a plain
        ``Component``, not a ``FlowComponent``), so it gets the whole
        ``components`` dict handed to it directly (a private, non-Pydantic
        attribute — the same "live cross-reference" pattern ``GraphSurface``
        already uses for its TESPy network), rather than going through the
        ``Stream`` hand-off every flow component uses.
        """
        if self._economic is None:
            return
        self._economic._components = self._components  # noqa: SLF001
        self._economic.mark_all_stale()
        self._economic.solve()

    def run(self) -> None:
        """Execute every sync interval, then the economic finalize step (if any)."""
        for interval in self.intervals:
            self.run_interval(interval.index)
            for component in self._ordered:
                component.accept_timestep()
            self._after_interval(interval.index)
            self.record(interval)
        self.finalize()


def _check_subsystems_contiguous(subsystems: list[tuple[str, list[FlowComponent]]]) -> None:
    """Require each subsystem to be a contiguous run of ``component_idx``, so the circuit passes through it once.

    Raises:
        ConfigError: A subsystem's components skip a ``component_idx`` that
            belongs to another subsystem.
    """
    for name, members in subsystems:
        indices = [c.component_idx for c in members]
        if indices != list(range(indices[0], indices[0] + len(indices))):
            raise ConfigError(
                f"sim_config.time_stepping subsystem {name!r} has component_idx {indices}; a subsystem must "
                "be a contiguous run of the circuit, with no component of another subsystem in between.",
            )


def _check_external_state_steps(
    subsystems: list[tuple[str, list[FlowComponent]]],
    intervals: list[SyncInterval],
) -> None:
    """Require a component that keeps external state to take one step per sync interval.

    Raises:
        ConfigError: Such a component's subsystem takes several steps in an
            interval (see ``Component.keeps_external_state``).
    """
    for name, members in subsystems:
        external = [c.__class__.__name__ for c in members if c.keeps_external_state]
        if not external:
            continue
        crowded = next((interval for interval in intervals if len(interval.steps[name]) > 1), None)
        if crowded is not None:
            raise ConfigError(
                f"Subsystem {name!r} holds {external[0]}, whose simulator state lives outside tango and can "
                f"take only one step per sync interval, but it takes {len(crowded.steps[name])} steps between "
                f"{crowded.t_start:.6g} s and {crowded.t_end:.6g} s. Give the other subsystems step end times "
                "at each of its step ends, or give it the coarser grid.",
            )


def _inlet_rules(
    subsystems: list[tuple[str, list[FlowComponent]]],
    time_stepping: TimeStepping,
    by_idx: dict[int, FlowComponent],
) -> dict[int, SyncRule]:
    """The sync rule for every component whose upstream neighbor is in another subsystem.

    Raises:
        ConfigError: A ``sync`` key names two subsystems with no stream
            between them, in that direction.
    """
    subsystem_of = {c.component_idx: name for name, members in subsystems for c in members}
    rules: dict[int, SyncRule] = {}
    edges: set[tuple[str, str]] = set()
    for name, members in subsystems:
        for component in members:
            next_idx: int | None = getattr(component, "next", None)
            if next_idx is None or next_idx not in by_idx or subsystem_of[next_idx] == name:
                continue
            edge = (name, subsystem_of[next_idx])
            edges.add(edge)
            rules[next_idx] = time_stepping.sync_rule(*edge)
    for key in time_stepping.sync:
        if time_stepping.edge(key) not in edges:
            raise ConfigError(
                f"sim_config.time_stepping.sync gives a rule for {key!r}, but no stream flows that way; "
                f"the circuit's edges between subsystems are {sorted(f'{a} -> {b}' for a, b in edges)!r}.",
            )
    return rules
