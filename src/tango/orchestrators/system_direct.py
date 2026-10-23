"""SystemDirect — single-pass orchestrator for tango.

Auto-selected when sim_config.injection_mode is absent — i.e. the input graph
declares no boundary-condition variable to solve for (e.g. a bare wellbore
test fixture). Executes each component exactly once per timestep, in
component_idx order, wiring each component's outlet into its downstream
neighbor's inlet immediately after it solves.

This is also the base class for SystemBCIteration (see that module's
docstring). SystemDirect owns the only implementation of "one circuit pass"
and "loop over timesteps" — SystemBCIteration reuses both via inheritance
instead of re-implementing them. The choice between the two orchestrator
classes is a topology question (does this graph declare a BC-iteration
circuit at all); InjectionPolicy is the sole authority over how many passes
a single timestep takes once that topology choice has been made.
"""

from __future__ import annotations

from tango.components.economic.base import EconomicComponent
from tango.core.component import Component
from tango.core.errors import CoolPropError
from tango.core.orchestrator import Orchestrator
from tango.core.stream import Stream


class SystemDirect(Orchestrator):
    """Single-pass orchestrator: one circuit pass per timestep, no BC concept.

    Also the base class for SystemBCIteration — see module docstring.
    """

    def __init__(
        self,
        components: dict[str, Component],
        n_tsteps: int = 1,
        economic: EconomicComponent | None = None,
    ) -> None:
        """Initialize, sorting components by component_idx for circuit order.

        Args:
            components: Named physical components keyed by YAML name.
            n_tsteps: Total number of simulation timesteps.
            economic: Optional economic component (from the ``economic:``
                YAML block). Deliberately kept OUT of ``components``/
                ``_ordered``/``_by_idx`` — it must run exactly once, after
                every physical timestep completes (see ``finalize()``), not
                once per timestep like every other component. See
                ``DoubletEconomicComponent``'s module docstring for why it
                can't just be component_idx N+1 in the per-timestep loop.

        """
        self._components = components
        self.n_tsteps = n_tsteps
        self._economic = economic

        # Sort components by component_idx for deterministic solve order.
        self._ordered: list[Component] = sorted(
            components.values(),
            key=lambda c: c.component_idx,
        )
        # Build idx → component lookup for stream wiring.
        self._by_idx: dict[int, Component] = {c.component_idx: c for c in self._ordered}

        self._pending_inlets: dict[int, Stream] = {}
        """Most-recently-computed inlet ``Stream`` for each ``component_idx``,
        keyed by ``component_idx`` — this is what replaces ``inlet`` as a
        stored ``Component`` field (see ``Component.solve()``'s docstring
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
    def components(self) -> dict[str, Component]:
        """Return the named component dict."""
        return self._components

    def _next_inlet(self, component: Component) -> Stream:
        """Return the ``Stream`` to feed into ``component``'s next ``solve()`` call.

        Falls back to ``Stream.fresh()`` (all fields freshly zero) for a
        component_idx never yet wired — matching what a never-written
        ``inlet`` field defaulted to before ``inlet`` became a ``solve()``
        parameter.
        """
        return self._pending_inlets.get(component.component_idx, Stream.fresh())

    def _record_outlet(self, component: Component) -> None:
        """Convert ``component.outlet`` into its downstream neighbor's next inlet.

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
        src = component.outlet
        self._pending_inlets[next_idx] = Stream.fresh(
            T=src.T.get_fresh(),
            P=src.P.get_fresh(),
            mass_rate=src.mass_rate.get_fresh(),
        )

    def run_timestep(self, t: int) -> None:
        """Execute one circuit pass: solve each component in order and wire streams."""
        for component in self._ordered:
            component.mark_all_stale()
            try:
                component.solve(self._next_inlet(component))
            except CoolPropError as exc:
                raise CoolPropError(
                    f"Timestep: {t} / {self.n_tsteps}",
                    f"Component: {component.__class__.__name__} Component index: {component.component_idx}",
                    f"{exc}",
                ) from exc
            self._record_outlet(component)

    def _after_timestep(self, t: int) -> None:
        """Hook called after each timestep in ``run()``; no-op by default.

        Overridden by SystemBCIteration to log a per-timestep summary, without
        duplicating the timestep loop itself.
        """
        return

    def record(self, t: int) -> None:
        """Cascade record to every component in the circuit."""
        for component in self._ordered:
            component.record(t)

    def finalize(self) -> None:
        """Run the economic component (if any) exactly once, after all timesteps.

        Called by ``run()`` after the ``for t in range(self.n_tsteps)`` loop
        finishes — not once per timestep like ``run_timestep()``, because
        CAPEX sizing and the LCOE denominator both read the physical
        components' recorded ``history`` over the whole run (run-averaged
        turbine/pump/HX duty and net power/thermal output; see
        ``components/economic/doublet.py``), which is complete only after
        the last timestep.

        The economic component has no ``inlet``/``outlet`` wiring to any
        other component, so it gets the whole ``components`` dict handed to
        it directly (a private, non-Pydantic attribute — the same "live
        cross-reference" pattern ``GraphSurface`` already uses for its TESPy
        network), rather than going through the ``Stream`` abstraction every
        physical component uses.
        """
        if self._economic is None:
            return
        self._economic._components = self._components  # noqa: SLF001
        self._economic.mark_all_stale()
        # Stream() (unused) — EconomicComponent.solve() ignores `inlet`
        # entirely; see EconomicComponent.solve()'s docstring for why the
        # signature still requires one (Liskov compatibility with
        # Component.solve()).
        self._economic.solve(Stream())

    def run(self) -> None:
        """Execute all timesteps, then the economic finalize step (if any)."""
        for t in range(self.n_tsteps):
            self.run_timestep(t)
            self._after_timestep(t)
            self.record(t)
        self.finalize()
