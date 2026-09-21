"""Tests for LockedState — single-value fresh/stale wrapper.

Each test targets one of the six contracted behaviours:

  1. get_fresh() errors when stale
  2. get_fresh() succeeds when fresh
  3. get_stale() errors when fresh
  4. get_stale() succeeds when stale
  5. update() on a stale field succeeds and marks it fresh
  6. update() on a fresh field raises DoubleWriteError

Plus lifecycle, check_and_reset(), and usage as a dataclass field.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from tango.core.errors import DoubleWriteError, FreshAccessError, StaleAccessError
from tango.core.locked_state import LockedState

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fresh() -> LockedState[float]:
    """A LockedState[float] that starts fresh at 300.0 (default on construction)."""
    return LockedState(300.0)


@pytest.fixture()
def stale(fresh: LockedState[float]) -> LockedState[float]:
    """The same LockedState after mark_stale(), so it is stale."""
    fresh.mark_stale()
    return fresh


# ---------------------------------------------------------------------------
# 1. get_fresh() errors when stale
# ---------------------------------------------------------------------------


def test_get_fresh_raises_when_stale(stale: LockedState[float]) -> None:
    """get_fresh() on a stale LockedState raises StaleAccessError."""
    with pytest.raises(StaleAccessError):
        stale.get_fresh()


# ---------------------------------------------------------------------------
# 2. get_fresh() succeeds when fresh
# ---------------------------------------------------------------------------


def test_get_fresh_succeeds_when_fresh(fresh: LockedState[float]) -> None:
    """get_fresh() on a fresh LockedState returns the stored value."""
    assert fresh.get_fresh() == 300.0


# ---------------------------------------------------------------------------
# 3. get_stale() errors when fresh
# ---------------------------------------------------------------------------


def test_get_stale_raises_when_fresh(fresh: LockedState[float]) -> None:
    """get_stale() on a fresh LockedState raises FreshAccessError."""
    with pytest.raises(FreshAccessError):
        fresh.get_stale()


# ---------------------------------------------------------------------------
# 4. get_stale() succeeds when stale
# ---------------------------------------------------------------------------


def test_get_stale_succeeds_when_stale(stale: LockedState[float]) -> None:
    """get_stale() on a stale LockedState returns the previous-timestep value."""
    assert stale.get_stale() == 300.0


# ---------------------------------------------------------------------------
# 5. update() on stale succeeds and marks fresh
# ---------------------------------------------------------------------------


def test_update_stale_marks_fresh(stale: LockedState[float]) -> None:
    """update() on a stale LockedState writes the value and marks it fresh."""
    stale.update(350.0)
    assert stale.is_fresh()
    assert stale.get_fresh() == 350.0


# ---------------------------------------------------------------------------
# 6. update() on fresh raises DoubleWriteError
# ---------------------------------------------------------------------------


def test_update_fresh_raises(fresh: LockedState[float]) -> None:
    """update() on an already-fresh LockedState raises DoubleWriteError."""
    with pytest.raises(DoubleWriteError):
        fresh.update(350.0)


# ---------------------------------------------------------------------------
# check_and_reset()
# ---------------------------------------------------------------------------


def test_check_and_reset_on_fresh_marks_stale(fresh: LockedState[float]) -> None:
    """check_and_reset() on a fresh value validates and advances to stale."""
    fresh.check_and_reset()
    assert fresh.is_stale()
    # Value is preserved as the "previous timestep" value.
    assert fresh.get_stale() == 300.0


def test_check_and_reset_on_stale_raises(stale: LockedState[float]) -> None:
    """check_and_reset() on a stale value raises — update() was never called."""
    with pytest.raises(StaleAccessError):
        stale.check_and_reset()


# ---------------------------------------------------------------------------
# Full single-timestep lifecycle
# ---------------------------------------------------------------------------


def test_single_timestep_lifecycle() -> None:
    """Exercise the canonical mark_stale → get_stale → update → get_fresh cycle."""
    s: LockedState[float] = LockedState(300.0)

    # Fresh on construction — previous timestep value is authoritative.
    assert s.is_fresh()

    # Advance to the new timestep.
    s.mark_stale()
    assert s.is_stale()

    # Read previous-timestep value during solve.
    prev = s.get_stale()
    assert prev == 300.0

    # Compute and write new value.
    s.update(prev + 50.0)
    assert s.is_fresh()
    assert s.get_fresh() == 350.0


# ---------------------------------------------------------------------------
# Usage as a typed field inside a state dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _DemoState:
    """Minimal component state — frozen=True prevents wrapper replacement."""

    T: LockedState[float] = field(default_factory=lambda: LockedState(300.0))
    P: LockedState[float] = field(default_factory=lambda: LockedState(1e5))


def test_as_dataclass_field() -> None:
    """LockedState fields on a state dataclass are independent per instance."""
    s = _DemoState()

    # Both start fresh.
    assert s.T.is_fresh()
    assert s.P.is_fresh()

    # Mark stale and update only T.
    s.T.mark_stale()
    s.P.mark_stale()
    s.T.update(350.0)

    # T is fresh, P is still stale.
    assert s.T.is_fresh()
    assert s.P.is_stale()
    assert s.T.get_fresh() == 350.0
    assert s.P.get_stale() == 1e5


def test_dataclass_instances_are_independent() -> None:
    """Two _DemoState instances do not share LockedState objects."""
    a = _DemoState()
    b = _DemoState()

    a.T.mark_stale()
    a.T.update(400.0)

    # b.T is unaffected.
    assert b.T.is_fresh()
    assert b.T.get_fresh() == 300.0


# ---------------------------------------------------------------------------
# Bypass prevention
# ---------------------------------------------------------------------------


def test_frozen_dataclass_blocks_wrapper_replacement() -> None:
    """frozen=True on the state dataclass prevents replacing the LockedState object."""
    from dataclasses import FrozenInstanceError  # type: ignore[attr-defined]

    s = _DemoState()
    with pytest.raises(FrozenInstanceError):
        s.T = LockedState(999.0)  # type: ignore[misc]


def test_name_mangling_blocks_underscore_access(fresh: LockedState[float]) -> None:
    """Double-underscore slots mean _value and __value are both unreachable externally."""
    # Single underscore: no slot named _value exists.
    with pytest.raises(AttributeError):
        fresh._value = 999.0  # type: ignore[attr-defined]

    # Double underscore: mangled to _CallerModule__value, which also has no slot.
    with pytest.raises(AttributeError):
        fresh.__value = 999.0  # type: ignore[attr-defined]

    # Arbitrary new attribute: __slots__ blocks addition entirely.
    with pytest.raises(AttributeError):
        fresh.anything = 999.0  # type: ignore[attr-defined]
