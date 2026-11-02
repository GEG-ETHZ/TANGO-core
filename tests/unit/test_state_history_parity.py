"""Enforces the TANGO Commandment (CONTRIBUTING.md, rule-state-history-parity):
every attribute in a ``*State`` class (``Stream`` included) must have an
analog in its ``*History`` class.

``*History`` classes are hand-written, not auto-derived (a runtime
``dataclasses.make_dataclass()`` derivation was tried and rejected — it
produces classes ``mypy --strict`` cannot type-check at all, see git
history/session notes) — so this test is what actually enforces the
commandment: it fails CI the moment a ``*State``/``Stream`` field is added
without a matching ``*History`` field, rather than relying on a manual
per-PR audit.
"""

from __future__ import annotations

import dataclasses
import typing

import pytest

from tango.components.reservoir.lumped import LumpedReservoirHistory, LumpedReservoirState
from tango.components.surface.graph import GraphSurfaceHistory, GraphSurfaceState
from tango.components.well.grouped_subsurface import GroupedSubsurfaceHistory, GroupedSubsurfaceState
from tango.components.well.lumped import (
    ProductionWellWithPumpHistory,
    ProductionWellWithPumpState,
    WellboreHistory,
    WellboreState,
)
from tango.components.well.numerical import NumericalWellHistory, NumericalWellState
from tango.core.locked_state import LockedState
from tango.core.stream import Stream, StreamHistory
from tango.external.raft_wrapper import RaftWrapperHistory, RaftWrapperState

# Fields whose *State type isn't a plain scalar/list LockedState and has a
# deliberately differently-shaped *History analog instead of a literal
# same-named field — see the referenced class's own docstring for why.
_DOCUMENTED_EXCEPTIONS: dict[type, frozenset[str]] = {
    # GraphSurfaceState.node_detail (dict[node][quantity] snapshot) -> its
    # analog is node_history (dict[node][quantity] -> list[value]),
    # transposed by node/quantity rather than by timestep.
    GraphSurfaceState: frozenset({"node_detail"}),
}

_PAIRS: list[tuple[type, type]] = [
    (Stream, StreamHistory),
    (WellboreState, WellboreHistory),
    (ProductionWellWithPumpState, ProductionWellWithPumpHistory),
    (NumericalWellState, NumericalWellHistory),
    (LumpedReservoirState, LumpedReservoirHistory),
    (GraphSurfaceState, GraphSurfaceHistory),
    (GroupedSubsurfaceState, GroupedSubsurfaceHistory),
    (RaftWrapperState, RaftWrapperHistory),
]


def _locked_state_field_names(cls: type) -> set[str]:
    """Return the names of every ``LockedState``-typed field on a dataclass."""
    hints = typing.get_type_hints(cls)
    return {f.name for f in dataclasses.fields(cls) if typing.get_origin(hints.get(f.name)) is LockedState}


@pytest.mark.parametrize("state_cls,history_cls", _PAIRS, ids=[s.__name__ for s, _ in _PAIRS])
def test_every_state_attribute_has_history_analog(state_cls: type, history_cls: type) -> None:
    """Every LockedState field on `state_cls` has a same-named field on `history_cls`."""
    state_fields = _locked_state_field_names(state_cls)
    exceptions = _DOCUMENTED_EXCEPTIONS.get(state_cls, frozenset())
    history_field_names = {f.name for f in dataclasses.fields(history_cls)}

    missing = (state_fields - exceptions) - history_field_names
    assert not missing, (
        f"{state_cls.__name__} field(s) {sorted(missing)} have no analog in "
        f"{history_cls.__name__} (CONTRIBUTING.md's *State/*History parity "
        "commandment). Add a matching list[T] field and append it in "
        "record(), or add the field name to _DOCUMENTED_EXCEPTIONS above "
        "with a docstring explaining the differently-shaped analog — see "
        "GraphSurfaceState.node_detail for the pattern."
    )

    # Exceptions must be real: every listed name must actually be a
    # LockedState field on state_cls, or the exception is stale.
    stale_exceptions = exceptions - state_fields
    assert not stale_exceptions, (
        f"_DOCUMENTED_EXCEPTIONS[{state_cls.__name__}] lists {sorted(stale_exceptions)}, "
        "which are no longer LockedState fields on that class — remove the stale exception."
    )
