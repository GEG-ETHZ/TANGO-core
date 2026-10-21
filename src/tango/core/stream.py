"""Stream — fluid connection between tango components."""

from __future__ import annotations

from dataclasses import dataclass, field

from tango.core.locked_state import LockedState
from tango.core.state_methods import StateMethods


def _ls() -> LockedState[float]:
    """Convenience: LockedState[float] starting stale with value 0.0."""
    ls: LockedState[float] = LockedState(0.0)
    ls.mark_stale()
    return ls


@dataclass(frozen=True)
class Stream(StateMethods):
    """Carries mass flow rate and the two thermodynamic properties
    (pressure, temperature) that actually cross a component boundary.

    SI units throughout: pressures in Pa, temperatures in K,
    mass flow rates in kg/s.

    Deliberately narrow: every field here is one every component's
    ``solve()`` both writes (``outlet``) and reads (``inlet``) — see the
    3-line block at the top of every concrete ``solve()``. Fields that are
    *computed* at the outlet condition but never read back by anything
    (``rho``, ``mu``) or never touched by any component at all (``H``,
    ``port``) were removed rather than carried here as dead weight — each
    component still computes its own density/viscosity locally wherever
    the physics needs them (e.g. ``state.rho``/``state.mu``, evaluated at
    whatever T/P that component's own calculation needs, not necessarily
    the outlet condition); ``Stream`` just isn't the place those live if
    nothing downstream reads them off the wire. Revisit if a future
    consumer (e.g. an external-tool adapter, a cavitation check) actually
    needs outlet-condition fluid properties propagated between components.

    Every scalar field is ``LockedState``-wrapped, structurally identical to
    a component's own ``state`` dataclass (see TANGO Commandment on
    LockedState placement in ``CONTRIBUTING.md``) — a ``Stream`` instance is
    never a bare, freely-reassignable container of raw floats. ``frozen=True``
    for the same Layer-3 reason every ``*State`` class uses it (see
    ``core/locked_state.py``'s module docstring): it blocks
    ``stream.T = LockedState(...)`` from silently replacing the wrapper and
    discarding its status, while leaving ``stream.T.update(...)`` fully
    functional.

    ``Stream()`` (the bare default constructor) leaves every field STALE —
    matching every other ``*State`` dataclass's convention: a genuinely
    usable, immediately-``get_fresh()``-able value requires an explicit
    write. Use ``Stream.fresh(...)`` instead wherever a Stream needs to carry
    real, immediately-readable data (orchestrator wiring, test fixtures).

    Deliberately does NOT carry a ``fluid_name`` (or any other fluid-identity
    field): every component that needs one already holds a reference to the
    Workflow's single shared ``Common`` instance (``core/specs.py``), which
    is where ``fluid_name`` lives. Duplicating it here as per-timestep,
    per-stream state would just be a second, unvalidated copy that could
    drift from ``Common`` — exactly the risk this design avoids (see
    docs/tango_tasks.md's fluid-identity review). If a future component
    needs to represent a genuine fluid *boundary* (e.g. a secondary/ORC loop
    physically separate from the geofluid loop), that calls for an explicit
    typed marker on the boundary component, not a field here.
    """

    mass_rate: LockedState[float] = field(default_factory=_ls)
    """Mass flow rate crossing the component boundary (kg/s). TODO(docs): drafted, review."""
    P: LockedState[float] = field(default_factory=_ls)
    """Pressure at the component boundary (Pa). TODO(docs): drafted, review."""
    T: LockedState[float] = field(default_factory=_ls)
    """Temperature at the component boundary (K). TODO(docs): drafted, review."""

    @classmethod
    def fresh(
        cls,
        *,
        T: float = 0.0,
        P: float = 0.0,
        mass_rate: float = 0.0,
    ) -> Stream:
        """Construct a Stream with every field already FRESH — immediately usable.

        ``Stream()``'s own default constructor leaves every field stale
        (see class docstring); this factory is for the common case of
        needing a Stream that already carries real data, readable right
        away via ``get_fresh()`` — the core mechanism the orchestrator's
        wiring layer (``SystemDirect``/``SystemBCIteration``) uses to build
        every ``inlet`` it constructs, not just a test-fixture convenience.
        Never used inside a component's own ``solve()``, which writes its
        own ``outlet`` fields via ``.update()`` individually, same as any
        other state field.
        """
        return cls(
            mass_rate=LockedState(mass_rate),
            P=LockedState(P),
            T=LockedState(T),
        )


@dataclass
class StreamHistory:
    """Per-timestep history of a ``Stream`` (TANGO Commandment: every
    ``*State``-shaped class — ``Stream`` included — must have a ``*History``
    analog with a matching field for each attribute). No exceptions needed
    here: every ``Stream`` field is ``LockedState``-wrapped, solve-cycle
    state (see ``Stream``'s own docstring for the fields deliberately
    excluded from the class entirely, rather than excluded from history).
    """

    mass_rate: list[float] = field(default_factory=list)
    """Per-timestep mass flow rate (kg/s). TODO(docs): drafted, review."""
    P: list[float] = field(default_factory=list)
    """Per-timestep pressure (Pa). TODO(docs): drafted, review."""
    T: list[float] = field(default_factory=list)
    """Per-timestep temperature (K). TODO(docs): drafted, review."""

    def record(self, stream: Stream) -> None:
        """Append one timestep snapshot."""
        self.mass_rate.append(stream.mass_rate.get_fresh())
        self.P.append(stream.P.get_fresh())
        self.T.append(stream.T.get_fresh())
