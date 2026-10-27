"""Component base class for tango.

Components are Pydantic models — the instantiated object is 1:1 with the YAML
input file.  All fields, including runtime state, history, and derived quantities,
are public Pydantic fields so that solved models can be serialized and restored.

Two classes:

- ``Component``: what every component shares — YAML config fields, ``state``/
  ``history``, serde, and convergence snapshot/restore.
- ``FlowComponent(Component)``: a component the working fluid flows through
  (wells, reservoir, surface plant). Adds the ``outlet`` Stream and
  ``solve(inlet) -> Stream``, which returns that outlet so the orchestrator
  can pass it straight to the next component. The economic component is a
  plain ``Component``: it has no fluid inlet or outlet.

Fields that are absent from YAML (state, history, outlet, derived quantities)
use ``default_factory`` and are populated when ``init()`` runs or, in the case of
state/history/outlet, when ``solve()``/``record()`` run. ``inlet`` is NOT a
field — see ``FlowComponent.solve()``'s docstring for why.

Serialization design
--------------------
``model_dump()`` returns all fields, including state, history, and (for a
``FlowComponent``) outlet.
This allows a solved model to be saved and later restored via ``from_dict()``.

Round-trip test pattern (config-only, skip_init=True)::

    comp1 = MyComponent.from_dict(d, skip_init=True)
    json1 = comp1.model_dump()
    comp2 = MyComponent.model_validate(json1)
    json2 = comp2.model_dump()
    assert json1 == json2

``skip_init=True`` leaves derived fields at their defaults (zero / empty list)
and is used for serde round-trip tests. Derived fields that are pure
functions of the inputs may be excluded from serialization (e.g.
``NumericalWell``'s), so a restored model that will be solved again needs
``init()``.

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
``history``, plus ``outlet``/``outlet_history`` for a ``FlowComponent``). Orchestrator.record()
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
see ``Workflow``'s class docstring for a worked example.

This is deliberately NOT applied to every field. Some fields are plain
Pydantic fields (not ``LockedState``-wrapped) that are legitimately
reassigned during the simulation itself, not by a user tweaking config —
freezing these would break ``init()``/``solve()``, not protect anything:

- ``FlowComponent.outlet`` — reassigned by ``solve()`` every timestep.
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
import math
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tango.core.errors import ConfigError
from tango.core.state_methods import StateMethods
from tango.core.stream import Stream, StreamHistory


class Component(BaseModel, ABC, StateMethods):
    """Abstract base for every tango component.

    Subclass this (usually through ``FlowComponent``) and declare
    YAML-configuration fields as normal Pydantic fields. Override ``init()``
    to compute derived quantities. ``record(timestep)`` (inherited from
    ``StateMethods``) already appends to history generically — override
    ``_state_history_pairs()`` instead if a subclass has more
    ``(state, history)``-shaped pairs to push than ``state``/``history``.

    The orchestrator calls ``mark_all_stale()`` immediately before every
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
    every timestep (matches the original ``record_history=True`` behavior).
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, config: dict[str, Any], skip_init: bool = False) -> Component:
        """Instantiate from a merged YAML config dict.

        Args:
            config: Merged dict of common + layout + component-specific fields.
            skip_init: If ``True``, skip ``init()`` — for serde round-trip
                tests that compare serialized fields only.

        """
        obj = cls.model_validate(config)
        if not skip_init:
            obj.init()
        return obj

    def _set_derived(self, **values: Any) -> None:
        """Assign fields computed by ``init()``, rejecting a config value that disagrees.

        A derived field is a pure function of other inputs, so a config that
        supplies one (by hand, or as a stale copy left in an edited
        ``to_dict()`` output) and gets a different value back would otherwise
        have its value silently replaced. Only fields the config explicitly
        set are checked (``model_fields_set``), so re-running ``init()`` on an
        already-initialized component is fine.

        Raises:
            ConfigError: A field in ``values`` was given in the config with a
                different value (beyond float noise).
        """
        for name, value in values.items():
            if name in self.model_fields_set and not _same_value(getattr(self, name), value):
                raise ConfigError(
                    f"{type(self).__name__}.{name} given in the config ({_short(getattr(self, name))}) doesn't "
                    f"match the value computed from its inputs ({_short(value)}). It is derived, not an "
                    "input: leave it out of the config.",
                )
            setattr(self, name, value)

    def init(self) -> None:
        """Compute derived quantities from validated input fields.

        Called by ``from_dict()`` unless ``skip_init=True``.  Override in
        subclasses to pre-compute geometry constants, look-up tables, etc.
        """

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
        by ``solve()``. A ``FlowComponent``'s ``inlet``/``outlet`` are
        excluded implicitly (they aren't part of ``state``) because they must
        evolve iteration-to-iteration during a convergence loop — restoring
        them would prevent any loop from moving. ``history`` is excluded the same way — only
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


class FlowComponent(Component):
    """Abstract base for a component the working fluid flows through: wells, reservoir, surface plant.

    The orchestrator passes ``inlet`` directly into ``solve(inlet)`` — it is
    NOT a stored field (see ``solve()``'s docstring for why). ``solve()``
    writes ``outlet``, which IS a stored field, and returns it; the
    orchestrator hands the returned Stream to the next component.
    """

    # ------------------------------------------------------------------
    # Runtime stream — written and returned by solve()
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

    @abstractmethod
    def solve(self, inlet: Stream) -> Stream:
        """Compute this component's outlet from ``inlet``, store it in ``outlet``, and return it.

        ``inlet`` is passed as an explicit call parameter — never a stored
        field — and the outlet comes back as the return value, so that the
        whole hand-off reads at one place: the orchestrator's wiring code
        (``outlet = component.solve(self._next_inlet(component))``, then
        ``self._record_outlet(component, outlet)``, tracked in
        ``SystemDirect._pending_inlets``). That one site tells you exactly
        which upstream component a given component's input causally depends
        on, for a given pass.

        Every concrete ``solve()`` records ``inlet`` into its own
        ``state.T_inlet``/``P_inlet``/``mass_rate`` (``LockedState``-
        protected, restored by ``restore_convergence_state()``), the durable
        record of "what this component's inlet was, this solve"; the
        parameter itself is transient.

        Returns:
            ``self.outlet``, freshly written by this call. Callers that keep
            it past the next ``solve()`` should copy its values (as
            ``SystemDirect._record_outlet`` does), since the next call
            overwrites them.

        """

    def _state_history_pairs(self) -> list[tuple[Any, Any]]:
        """Add ``(outlet, outlet_history)`` to ``StateMethods``'s default ``(state, history)`` pair."""
        pairs = super()._state_history_pairs()
        pairs.append((self.outlet, self.outlet_history))
        return pairs


_DERIVED_REL_TOL = 1e-9
"""Relative tolerance for a supplied derived value to count as matching (float noise only)."""


def _same_value(given: Any, computed: Any) -> bool:
    if isinstance(computed, float) or isinstance(given, float):
        return math.isclose(float(given), float(computed), rel_tol=_DERIVED_REL_TOL)
    if isinstance(computed, list):
        return (
            isinstance(given, list)
            and len(given) == len(computed)
            and all(_same_value(g, c) for g, c in zip(given, computed, strict=True))
        )
    return bool(given == computed)


def _short(value: Any) -> str:
    if isinstance(value, list):
        return f"{len(value)} values, first {value[0]:.6g}" if value else "[]"
    return f"{value:.6g}" if isinstance(value, float) else repr(value)
