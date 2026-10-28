"""StateMethods — mixin providing recursive state-lifecycle operations.

Any class that either IS a ``*State``/``Stream``-shaped leaf (its own
fields are ``LockedState``) or CONTAINS such state (``Component``, which
holds ``state``/``outlet``) inherits this mixin. Recursion targets are
found generically — by ``isinstance`` check against ``LockedState`` or
``StateMethods`` — never by field name (``"state"``) or class name
(``"...State"``). This one mechanism (inheriting ``StateMethods``) serves
as both "this class participates in state tracking" and "here is where
recursion should continue," with no separate naming convention or
field-attribute marker needed.

The lifecycle operations provided:

- ``mark_fresh``/``check_and_reset`` — recursive freshness tracking, one
  set of names covering every nested ``LockedState``/``StateMethods``
  field.
- ``record(timestep)`` — pushes ``(state, history)`` pairs, honoring
  ``save_interval`` when present. Matches tango's existing name
  (every concrete ``Component.record()`` already did this by hand before
  this mixin existed — see ``_state_history_pairs()``).
- ``set_cumulative``/``reset_cumulative`` — no automatic derivation is
  possible here: accumulating a rate × dt into a running total needs
  physics-specific knowledge of which field is the rate and which is the
  total. The mixin's default only recurses; a leaf class with a genuine
  accumulator (e.g. ``LumpedReservoirState.energy_extracted``) overrides
  it with real physics.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from tango_core.core.locked_state import LockedState


class StateMethods:
    """Mixin providing recursive state-lifecycle operations. See module docstring."""

    def _state_fields(self) -> list[tuple[str, Any]]:
        """Return ``(name, value)`` for every field declared on ``self``.

        Uses ``dataclasses.fields()`` for dataclass ``StateMethods``
        subclasses (every ``*State``/``Stream``/``*History`` class);
        falls back to ``vars(self)`` for non-dataclass subclasses
        (``Component``, a Pydantic model).
        """
        if dataclasses.is_dataclass(self):
            return [(f.name, getattr(self, f.name)) for f in dataclasses.fields(self)]
        return list(vars(self).items())

    def mark_all_stale(self) -> None:
        """Recursively mark every ``LockedState`` field stale.

        Called by the orchestrator immediately before each ``solve()`` —
        see ``Component.mark_all_stale()``'s own docstring for the
        write-slot lifecycle this opens.
        """
        for _, value in self._state_fields():
            if isinstance(value, LockedState):
                value.mark_stale()
            elif isinstance(value, StateMethods):
                value.mark_all_stale()

    def mark_fresh(self) -> None:
        """Recursively force every ``LockedState`` field fresh, without writing a new value.

        See ``LockedState.mark_fresh()``'s own docstring for when this is
        the right call instead of ``update()``.
        """
        for _, value in self._state_fields():
            if isinstance(value, (LockedState, StateMethods)):
                value.mark_fresh()

    def check_and_reset(self) -> None:
        """Recursively assert every ``LockedState`` field is fresh, then mark it stale.

        End-of-timestep validation: raises if any field was never written
        this cycle, catching a silently-skipped update rather than letting
        it carry a stale value into the next timestep unnoticed.
        """
        for _, value in self._state_fields():
            if isinstance(value, (LockedState, StateMethods)):
                value.check_and_reset()

    def set_cumulative(self, dt_years: float) -> None:
        """Update this instance's cumulative (rate × dt) fields, then recurse.

        No-op at this level — see module docstring's ``SetCumulative``
        section. A leaf class with a genuine accumulator overrides this to
        do the actual ``increment()`` call(s); this base implementation
        only propagates to nested ``StateMethods`` fields, so overriding
        classes should call ``super().set_cumulative(dt_years)`` too
        (or recurse themselves) to keep propagation working.
        """
        for _, value in self._state_fields():
            if isinstance(value, StateMethods):
                value.set_cumulative(dt_years)

    def reset_cumulative(self) -> None:
        """Reset this instance's cumulative fields to zero, then recurse.

        No-op at this level — see ``set_cumulative()``. A leaf class with a
        genuine accumulator overrides this to zero it (used when
        re-running from ``t=0`` without reconstructing the component).
        """
        for _, value in self._state_fields():
            if isinstance(value, StateMethods):
                value.reset_cumulative()

    def _state_history_pairs(self) -> list[tuple[Any, Any]]:
        """Return ``(state, history)`` pairs to push in ``record()``.

        Default: ``[(self.state, self.history)]`` if both attributes
        exist (every ``*State``-shaped leaf class returns ``[]`` here,
        since it has neither — nothing to do when ``record()`` is called
        on a leaf directly, which shouldn't normally happen anyway).
        Override to add more pairs — e.g. ``Component`` subclasses with an
        ``outlet``/``outlet_history`` pair alongside ``state``/``history``.
        """
        state = getattr(self, "state", None)
        history = getattr(self, "history", None)
        if state is not None and history is not None:
            return [(state, history)]
        return []

    def record(self, timestep: int) -> None:
        """Push every ``(state, history)`` pair due this timestep.

        Honors ``self.save_interval`` if the attribute exists (``None``
        disables recording entirely; otherwise records every Nth
        timestep).
        """
        if hasattr(self, "save_interval"):
            save_interval = self.save_interval
            if save_interval is None or timestep % save_interval != 0:
                return
        for state_obj, history_obj in self._state_history_pairs():
            history_obj.record(state_obj)
