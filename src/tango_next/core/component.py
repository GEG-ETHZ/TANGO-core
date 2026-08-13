"""Component base class for tango_next.

Components are Pydantic models — the instantiated object is 1:1 with the YAML
input file.  All fields, including runtime state, history, and derived quantities,
are public Pydantic fields so that solved models can be serialized and restored.

Fields that are absent from YAML (state, history, inlet, outlet, derived quantities)
use ``default_factory`` and are populated when ``init()`` runs or, in the case of
state/history, when ``solve()``/``record()`` run.

Serialization design
--------------------
``model_dump()`` returns all fields, including state, history, inlet, and outlet.
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

Each component's ``record(timestep)`` is called by the orchestrator after
every ``solve()``; the component decides whether to append to history based
on ``save_interval``.  Orchestrator.record() cascades downward so callers
can call it at the top level and know it propagates.

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
see ``applications/tango_next/sweep_demo_AGS_direct_heat/sweep_demo_AGS_direct_heat.py`` for a worked
example.

This is deliberately NOT applied to every field. Some fields are plain
Pydantic fields (not ``LockedState``-wrapped) that are legitimately
reassigned during the simulation itself, not by a user tweaking config —
freezing these would break ``init()``/``solve()``, not protect anything:

- ``inlet``/``outlet`` — reassigned by the orchestrator/``solve()`` every
  timestep.
- ``state``/``history`` — the object itself is never reassigned (its
  fields mutate internally instead), so freezing the container field would
  add nothing.
- ``SurfaceComponent.injection_pressure`` — the BC-iteration guess,
  explicitly updated in place by ``SystemBCIteration`` every convergence
  pass (see its docstring).
- A handful of subclass-specific "derived, recomputed every timestep"
  fields that happen to be plain floats rather than ``LockedState``, e.g.
  ``NumericalWell.cell_length``/``relative_roughness``/``T_r`` and
  ``LumpedReservoir.T_initial``/``rock_volume``/``rock_C_v``/``p1``/``p2``/
  ``p3`` — these are pure functions of already-restored inputs, recomputed
  identically however many times ``solve()`` runs in a timestep, so there
  is nothing for write-once enforcement to protect. See each class's own
  comments for why.

``NumericalWell.t_d_old``, ``LumpedReservoir.energy_extracted``, and
``LumpedReservoir.ever_solved`` are genuine cross-timestep accumulator/
sticky-flag state, so unlike the fields above they ARE ``LockedState``-
wrapped (``t_d_old``/``energy_extracted`` via ``LockedState.increment()``,
``ever_solved`` via the normal ``get_stale()``/``update()`` cycle) — but
deliberately kept as plain ``Component`` fields rather than moved into
``state``, specifically so they stay in scope for
``snapshot_convergence_state()``/``restore_convergence_state()``'s
categorical restore. ``state`` itself is excluded from that restore
(next paragraph) because every one of *its* fields is unconditionally
recomputed from scratch each ``solve()`` call; these three are not — they
depend on their own prior value — so they need the restore that ``state``
is exempt from, in order to avoid double-accumulating across
``SystemBCIteration``'s inner re-solve iterations.
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tango_next.core.locked_state import LockedState
from tango_next.core.stream import Stream

_CONVERGENCE_SNAPSHOT_EXCLUDED_FIELDS = frozenset({"inlet", "outlet", "state", "history"})
"""Fields excluded from Component.snapshot_convergence_state()/restore_convergence_state().

- inlet/outlet: must evolve iteration-to-iteration during a convergence loop
  (e.g. the injection-temperature guess literally propagates through them
  around the circuit) — restoring them would prevent any loop from moving.
- state: every solve() unconditionally rewrites every one of its LockedState
  fields each call, so restoring it first is always discarded work.
- history: only touched by record(), called once per timestep after any
  convergence loop finishes, never during it — and it grows every timestep,
  so repeatedly deep-copying it inside a convergence loop gets more
  expensive over the course of a run for zero benefit.
"""


class Component(BaseModel, ABC):
    """Abstract base for all tango_next physical components.

    Subclass this and declare YAML-configuration fields as normal Pydantic
    fields.  Override ``init()`` to compute derived quantities.
    Override ``record(timestep)`` to append to history.

    The orchestrator sets ``inlet`` before calling ``solve()``;
    ``solve()`` reads ``inlet`` and writes ``outlet``.

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
    # Runtime streams — set by the orchestrator before/after solve()
    # ------------------------------------------------------------------
    inlet: Stream = Field(default_factory=Stream)
    """Upstream stream — written by the orchestrator before solve()."""
    outlet: Stream = Field(default_factory=Stream)
    """Downstream stream — written by solve()."""

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
    def solve(self) -> None:
        """Compute outlet stream state from the current inlet stream state."""

    def mark_all_stale(self) -> None:
        """Mark every ``LockedState`` field, and every ``state``-like container, stale.

        Called by the orchestrator immediately before each ``solve()`` —
        staleness is owned by whatever dispatches ``solve()``, not by
        ``solve()`` itself. Walks this component's own attributes rather
        than hardcoding field names, so any future ``LockedState`` field —
        whether a bare ``Component`` attribute (e.g. ``energy_extracted``)
        or nested inside a container exposing its own ``mark_all_stale()``
        (e.g. ``state``) — is picked up for free.
        """
        for value in vars(self).values():
            if isinstance(value, LockedState):
                value.mark_stale()
                continue
            candidate = getattr(value, "mark_all_stale", None)
            if callable(candidate):
                candidate()

    def snapshot_convergence_state(self) -> dict[str, Any]:
        """Deep-copy every field that must not leak across a within-timestep re-solve.

        Used by orchestrators that re-solve a component more than once for
        the same calendar timestep (e.g. an injection-temperature
        convergence loop): restore this snapshot before every re-solve so
        each attempt starts from "state as committed at the end of the
        previous timestep," not from whatever the last attempt left behind.

        Scope: every non-frozen *declared Pydantic field* except ``inlet``/
        ``outlet``/``state``/``history`` (see
        ``_CONVERGENCE_SNAPSHOT_EXCLUDED_FIELDS``) — categorical, not a
        hand-maintained list of field names, so a future field of the same
        kind (persists across timesteps, mutated by ``solve()``) is
        protected automatically. Deliberately scoped to
        ``type(self).model_fields`` rather than ``vars(self)``: some
        components (e.g. ``GraphSurface``) keep private, non-field
        attributes (a live TESPy network/connections) that ``init()``
        builds once and ``solve()`` mutates through TESPy's own machinery —
        those must never be snapshotted/deep-copied/replaced.
        """
        return {
            name: copy.deepcopy(getattr(self, name))
            for name, info in type(self).model_fields.items()
            if not info.frozen and name not in _CONVERGENCE_SNAPSHOT_EXCLUDED_FIELDS
        }

    def restore_convergence_state(self, snapshot: dict[str, Any]) -> None:
        """Write a fresh deep copy of a ``snapshot_convergence_state()`` snapshot back onto self.

        Deep-copies again at restore time, not just at snapshot time — the
        snapshot must stay pristine across repeated restores within the
        same timestep, so a ``solve()`` call's in-place mutation of what
        was handed out on one attempt must not corrupt what the next
        attempt reads back.
        """
        for name, value in snapshot.items():
            setattr(self, name, copy.deepcopy(value))

    def record(self, timestep: int) -> None:
        """Append the current ``state`` to ``history`` if ``save_interval`` permits.

        Called by the orchestrator after every ``solve()``.  Override in
        subclasses that track history.

        Args:
            timestep: Zero-based timestep index.

        """
