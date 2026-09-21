"""Component base class for tango.

Components are Pydantic models — the instantiated object is 1:1 with the YAML
input file.  All fields, including runtime state, history, and derived quantities,
are public Pydantic fields so that solved models can be serialized and restored.

Fields that are absent from YAML (state, history, outlet, derived quantities)
use ``default_factory`` and are populated when ``init()`` runs or, in the case of
state/history/outlet, when ``solve()``/``record()`` run. ``inlet`` is NOT a
field — see ``solve()``'s docstring for why.

Serialization design
--------------------
``model_dump()`` returns all fields, including state, history, and outlet.
This allows a solved model to be saved and later restored via ``from_dict()``.

Round-trip test pattern (config-only, skip_init=True)::

    comp1 = MyComponent.from_dict(d, skip_init=True)
    json1 = comp1.model_dump()
    comp2 = MyComponent.model_validate(json1)
    json2 = comp2.model_dump()
    assert json1 == json2

``skip_init=True`` leaves derived fields at their defaults (zero / empty list)
and is used for serde round-trip tests and for restoring a previously-solved
model (where derived fields are already embedded in the serialized data).

History / save_interval
-----------------------
``save_interval: int | None = 1``

- ``None``  — never record history
- ``1``     — record every timestep (default)
- ``n > 1`` — record every n-th timestep

Each component's ``record(timestep)`` (inherited from ``StateMethods`` — see
``core/state_methods.py``) is called by the orchestrator after every
``solve()``; it checks ``save_interval`` and, if due, pushes every
``(state, history)`` pair returned by ``_state_history_pairs()`` (``state``/
``history`` plus ``outlet``/``outlet_history``). Orchestrator.record()
cascades downward so callers can call it at the top level and know it
propagates.

Frozen config fields
---------------------
Every field that is genuinely YAML config — set once at construction and
never reassigned by ``init()``/``solve()``/the orchestrator afterward — is
declared ``Field(frozen=True)`` in each concrete ``Component`` subclass
(``component_idx``/``save_interval`` here on the base class; geometry,
physics-model selections, etc. in each subclass). This mirrors ``Common``
(``core/specs.py``): the only supported way to change one of these values
is the dict-modify-then-reinstantiate pattern (``Workflow.to_dict()`` →
mutate the copy → ``Workflow(cfg)``), never live attribute assignment —
see ``applications/sweep_demo_AGS_direct_heat/sweep_demo_AGS_direct_heat.py`` for a worked
example.

This is deliberately NOT applied to every field. Some fields are plain
Pydantic fields (not ``LockedState``-wrapped) that are legitimately
reassigned during the simulation itself, not by a user tweaking config —
freezing these would break ``init()``/``solve()``, not protect anything:

- ``outlet`` — reassigned by ``solve()`` every timestep.
- ``state``/``history`` — the object itself is never reassigned (its
  fields mutate internally instead), so freezing the container field would
  add nothing.
- ``SurfaceComponent.injection_pressure`` — the BC-iteration guess,
  explicitly updated in place by ``SystemBCIteration`` every convergence
  pass (see its docstring).
- A handful of subclass-specific "derived, computed once by ``init()``"
  fields that happen to be plain floats rather than ``LockedState``, e.g.
  ``NumericalWell.cell_length``/``relative_roughness``/``T_r`` and
  ``LumpedReservoir.T_initial``/``rock_volume``/``rock_C_v`` — these are
  pure functions of frozen config fields, computed exactly once in
  ``init()`` and never reassigned by ``solve()``, so there is nothing for
  write-once enforcement to protect and no reason for them to live in
  ``state`` (next paragraph) either. See each class's own comments for why.

Every field that IS reassigned by ``solve()`` — every call, or only some
calls, doesn't matter — belongs in ``state``, not as a bare ``Component``
field, no matter whether it also happens to be a pure function of already-
restored inputs (e.g. ``LumpedReservoir``'s ``p1``/``p2``/``p3``) or a
genuine cross-timestep accumulator that depends on its own prior value
(e.g. ``LumpedReservoir.energy_extracted``/``ever_solved``,
``NumericalWell.state.t_d``). ``state`` is restored in full before every
re-solve (next paragraph) precisely so this one rule has no exceptions to
track per-field: anything ``solve()`` writes is protected the same way,
accumulator or not.
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tango.core.state_methods import StateMethods
from tango.core.stream import Stream, StreamHistory


class Component(BaseModel, ABC, StateMethods):
    """Abstract base for all tango physical components.

    Subclass this and declare YAML-configuration fields as normal Pydantic
    fields.  Override ``init()`` to compute derived quantities.
    ``record(timestep)`` (inherited from ``StateMethods``) already appends
    to history generically — override ``_state_history_pairs()`` instead if
    a subclass has more ``(state, history)``-shaped pairs to push than the
    base class's ``state``/``history`` and ``outlet``/``outlet_history``.

    The orchestrator passes ``inlet`` directly into ``solve(inlet)`` — it is
    NOT a stored ``Component`` field (see ``solve()``'s docstring for why);
    ``solve()`` writes ``outlet``, which IS a stored field.

    The orchestrator also calls ``mark_all_stale()`` immediately before every
    ``solve()`` call — ``solve()`` itself does not do this. A component fresh
    from construction already starts with a stale ``state`` (each field's
    ``default_factory`` marks it stale), so the very first ``solve()`` call
    needs no explicit ``mark_all_stale()`` first; every subsequent call does.
    Callers invoking ``solve()`` directly (bypassing an orchestrator — tests,
    scratch scripts) must call ``mark_all_stale()`` themselves before any
    call after the first.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        populate_by_name=True,
    )

    component_idx: int = Field(frozen=True)
    """Circuit index.  0 is the circuit entry (injection well, solved first).
    The BC checkpoint (surface) is identified separately via ``bc_checkpoint_idx``
    in ``sim_config``."""

    save_interval: int | None = Field(default=1, frozen=True)
    """Timestep interval at which ``record()`` appends state to history.
    ``None`` disables history recording entirely.  Default ``1`` records
    every timestep (matches the original ``record_history=True`` behaviour).
    """

    # ------------------------------------------------------------------
    # Runtime stream — written by solve()
    # ------------------------------------------------------------------
    outlet: Stream = Field(default_factory=Stream)
    """Downstream stream — written by solve(), once per call, same
    write-once-per-solve pattern as ``state`` (``outlet``'s fields are
    ``LockedState``-wrapped — see ``core/stream.py``). There is no
    corresponding ``inlet`` field: see ``solve()``'s docstring."""
    outlet_history: StreamHistory = Field(default_factory=StreamHistory)
    """Per-timestep history of ``outlet`` — pushed alongside ``state``'s own
    history every ``record()`` call (see ``_state_history_pairs()``).
    TANGO Commandment: every ``*State``-shaped attribute (``outlet``
    included) needs a ``*History`` analog."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, config: dict[str, Any], skip_init: bool = False) -> Component:
        """Instantiate from a merged YAML config dict.

        Args:
            config: Merged dict of common + layout + component-specific fields.
            skip_init: If ``True``, skip ``init()`` — use this when restoring a
                previously-solved model (derived fields are already in ``config``)
                or for serde round-trip tests.

        """
        obj = cls.model_validate(config)
        if not skip_init:
            obj.init()
        return obj

    def init(self) -> None:
        """Compute derived quantities from validated input fields.

        Called by ``from_dict()`` unless ``skip_init=True``.  Override in
        subclasses to pre-compute geometry constants, look-up tables, etc.
        """

    @abstractmethod
    def solve(self, inlet: Stream) -> None:
        """Compute outlet stream state from the given inlet stream state.

        ``inlet`` is passed as an explicit call parameter — never a stored
        ``Component`` field — so that what feeds a component is always
        traceable to one place: the orchestrator's wiring code
        (``SystemDirect._next_inlet()``/``_record_outlet()``, tracked in
        ``_pending_inlets``), which computes each ``inlet`` from a named
        upstream component's ``outlet`` and hands it directly to this call.
        Reading ``solve()``'s signature plus that one wiring site tells you
        exactly which upstream component a given component's output causally
        depends on, for a given pass — there is no separate, independently-
        timed write to chase through a mutable field to answer that
        question. Every concrete ``solve()`` immediately records ``inlet``
        into its own ``state.T_inlet``/``P_inlet``/``mass_rate`` — already
        ``LockedState``-protected, already correctly restored by
        ``restore_convergence_state()`` — which is the durable, inspectable
        record of "what this component's inlet was, this solve," e.g. for
        history/debugging; the parameter itself is transient, never touched
        again after that.

        ``EconomicComponent.solve()`` overrides this with the same
        signature for Liskov compatibility but never reads ``inlet`` — it
        has no concept of a fluid inlet (see its own class docstring).
        """

    def _state_history_pairs(self) -> list[tuple[Any, Any]]:
        """Add ``(outlet, outlet_history)`` to ``StateMethods``'s default ``(state, history)`` pair.

        Every concrete ``Component`` gets this for free from the base
        class — no per-subclass override needed, since ``outlet``/
        ``outlet_history`` are declared here, not per-subclass.
        """
        pairs = super()._state_history_pairs()
        pairs.append((self.outlet, self.outlet_history))
        return pairs

    def snapshot_convergence_state(self) -> Any:
        """Deep-copy ``state`` — the only thing that must not leak across a within-timestep re-solve.

        Used by orchestrators that re-solve a component more than once for
        the same calendar timestep (e.g. an injection-temperature
        convergence loop): restore this snapshot before every re-solve so
        each attempt starts from "state as committed at the end of the
        previous timestep," not from whatever the last attempt left behind
        (whether that's an unconverged re-solve's own output, or a stale
        read of a cross-timestep accumulator via last attempt's leftovers).

        Scope: ``self.state`` only. Every field a component's ``solve()``
        writes — whether recomputed from scratch each call or a genuine
        cross-timestep accumulator that depends on its own prior value —
        lives in ``state`` by convention (see the class docstring's "Frozen
        config fields" section); nothing outside ``state`` is ever mutated
        by ``solve()``. ``inlet``/``outlet`` are excluded implicitly (they
        aren't part of ``state``) because they must evolve iteration-to-
        iteration during a convergence loop — restoring them would prevent
        any loop from moving. ``history`` is excluded the same way — only
        ``record()`` touches it, once per timestep after any convergence
        loop finishes, never during it.
        """
        return copy.deepcopy(self.state)

    def restore_convergence_state(self, snapshot: Any) -> None:
        """Write a fresh deep copy of a ``snapshot_convergence_state()`` snapshot back onto ``self.state``.

        Deep-copies again at restore time, not just at snapshot time — the
        snapshot must stay pristine across repeated restores within the
        same timestep, so a ``solve()`` call's in-place mutation of what
        was handed out on one attempt must not corrupt what the next
        attempt reads back.
        """
        self.state = copy.deepcopy(snapshot)
