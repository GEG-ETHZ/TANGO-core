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
see ``examples/tango_next/sweep_demo_AGS_direct_heat.py`` for a worked
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
  ``NumericalWell.t_d_old`` and ``LumpedReservoir.energy_extracted``/
  ``p1``/``p2``/``p3`` — see each class's own comments for why.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tango_next.core.stream import Stream


class Component(BaseModel, ABC):
    """Abstract base for all tango_next physical components.

    Subclass this and declare YAML-configuration fields as normal Pydantic
    fields.  Override ``init()`` to compute derived quantities.
    Override ``record(timestep)`` to append to history.

    The orchestrator sets ``inlet`` before calling ``solve()``;
    ``solve()`` reads ``inlet`` and writes ``outlet``.
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

    def record(self, timestep: int) -> None:
        """Append the current ``state`` to ``history`` if ``save_interval`` permits.

        Called by the orchestrator after every ``solve()``.  Override in
        subclasses that track history.

        Args:
            timestep: Zero-based timestep index.

        """
