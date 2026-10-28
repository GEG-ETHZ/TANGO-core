"""LockedState — single-value wrapper that enforces one update per timestep.

Motivation
----------
Any multi-component simulation can accidentally read or write a state variable
at the wrong point in the solve order — reading a value before its upstream
dependency has been updated, or writing it twice in the same timestep.  These
bugs are hard to catch by inspection because the code *looks* correct; the error
is in which loop level it runs inside.  ``LockedState`` catches them immediately
at the call site rather than letting them propagate silently into results. The
risk is especially acute in iterative solvers that mix a *convergence loop*
(repeated passes until a boundary condition is satisfied) with a *timestep loop*
(advancing the simulation forward in time).

``LockedState`` addresses this by embedding the enforcement in the data itself
rather than relying on caller discipline.  Any solver — existing or future —
that tries to write a state variable twice in the same timestep receives an
immediate ``DoubleWriteError`` at the call site.  This is the *solver-neutral*
property: the constraint travels with the variable, not with the caller, so new
orchestrators and new convergence strategies cannot accidentally violate it.

The overhead is a single enum comparison on each read/write — negligible
relative to any CoolProp or TESPy call.

Bypass prevention
-----------------
In a language with real module-private fields, the compiler could enforce
this contract directly — code outside the defining module simply couldn't
name the internal fields. Python has no equivalent mechanism; every
attribute is reachable at runtime.  We use three layers to make bypass
*obvious* rather than *impossible*:

**Layer 1 — ``__slots__``**: prevents attribute *addition*.  A caller cannot
do ``ls.value = x`` (no slot named ``value``); Python raises ``AttributeError``
immediately.  This eliminates the most common accidental bypass — mis-spelling
the API method and inadvertently creating a shadow attribute.

**Layer 2 — double-underscore name mangling on ``__value`` and ``__status``**:
Python mangles any identifier of the form ``__name`` (two leading underscores,
at most one trailing) inside a class body to ``_ClassName__name``.  The
``__slots__`` declaration is subject to the same mangling, so the actual slot
names stored on the class are ``_LockedState__value`` and
``_LockedState__status``.  The practical effect on callers outside the class:

- ``ls.__value = x`` — Python mangles this to ``ls._CallerModule__value``
  (or ``ls.__value`` at module top-level, which mangles differently again);
  neither name matches the real slot → ``AttributeError``.
- ``ls._value = x`` — no slot named ``_value`` exists at all → ``AttributeError``.

The only remaining bypass route is the deliberately ugly
``ls._LockedState__value = x``.  Anyone who types that knows exactly what the
mangled name convention means and is making a conscious choice to circumvent a
documented safety mechanism.  That is a meaningful barrier: it eliminates all
*accidental* bypasses and transforms any *intentional* bypass into an
unambiguous red flag in code review.

**Layer 3 — ``@dataclass(frozen=True)`` on every containing state class**:
prevents ``state.T = LockedState(350.0)``, which would silently replace the
whole wrapper object, discarding its status and losing any pending fresh value.
``frozen=True`` raises ``FrozenInstanceError`` on attribute *re-assignment*
while leaving all method calls (``state.T.update(...)``, ``state.T.mark_stale()``)
fully functional.  Every state dataclass in tango that holds ``LockedState``
fields **must** use ``frozen=True``::

    @dataclass(frozen=True)
    class ReservoirState:
        T_outlet:         LockedState[float] = field(default_factory=lambda: LockedState(300.0))
        energy_extracted: LockedState[float] = field(default_factory=lambda: LockedState(0.0))

What is still NOT prevented
---------------------------
``ls._LockedState__value = x`` works at the Python runtime level and always
will — Python's name mangling is a renaming convention, not true access
control.  We do not try to block this with ``__setattr__`` overrides because
doing so would force every internal write inside ``update()``, ``__init__()``,
etc. to use ``object.__setattr__(self, '_LockedState__value', x)`` — a
significant readability and maintenance cost for zero practical benefit, since
anyone reaching through name mangling *by definition* understands what they
are doing.

Each state variable in a component's ``state`` dataclass is a ``LockedState``
instance::

    from dataclasses import dataclass, field
    from tango_core.core.locked_state import LockedState

    @dataclass(frozen=True)
    class ReservoirState:
        T_outlet:         LockedState[float] = field(default_factory=lambda: LockedState(300.0))
        energy_extracted: LockedState[float] = field(default_factory=lambda: LockedState(0.0))

A new ``LockedState`` starts **fresh** — the initial value is authoritative for
the 0th timestep.  Immediately before each ``solve()`` call, the orchestrator
calls ``component.mark_all_stale()`` (``core/component.py``), which cascades
down to ``mark_stale()`` on every state field (or ``check_and_reset()`` for
combined validate-and-advance) — components no longer call this on
themselves.  During ``solve()``, ``update()`` writes the new value and
re-marks it fresh.  ``get_fresh()`` / ``get_stale()`` assert the expected
status before returning the value.

Status semantics
----------------
**fresh** — the value has been computed for the *current* timestep.
  - ``get_fresh()`` succeeds.
  - ``get_stale()`` raises ``FreshAccessError``.
  - ``update()`` raises ``DoubleWriteError``.

**stale** — the value has not yet been computed for the current timestep; it
holds the result from the *previous* timestep (or the initial value).
  - ``get_stale()`` succeeds.
  - ``get_fresh()`` raises ``StaleAccessError``.
  - ``update()`` succeeds and marks fresh.

Lifecycle per timestep::

    state.T_outlet.mark_stale()           # ① advance to new timestep
    prev = state.T_outlet.get_stale()     # ② read previous value during solve
    state.T_outlet.update(prev + delta)   # ③ write new value, marks fresh
    cur  = state.T_outlet.get_fresh()     # ④ read current value (post-solve)
    state.T_outlet.check_and_reset()      # ⑤ validate fresh, then mark stale
                                          #    (alternative to explicit ①)
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Generic, TypeVar, get_args

from tango_core.core.errors import (
    DoubleWriteError,
    FreshAccessError,
    StaleAccessError,
)

if TYPE_CHECKING:
    import pydantic

T = TypeVar("T")


class _Status(Enum):
    FRESH = auto()
    STALE = auto()


class LockedState(Generic[T]):
    """Single-value wrapper that enforces exactly one ``update()`` per timestep.

    Args:
        initial_value: The value held on construction.  Status starts **fresh**
            (the initial value is authoritative; call ``mark_stale()`` before
            the first ``solve()`` pass to open the first write slot).

    """

    # ``__slots__`` with double-underscore names enables Python name mangling,
    # which is the primary bypass-prevention mechanism for this class.
    #
    # The slot names ``__value`` and ``__status`` are mangled by Python to
    # ``_LockedState__value`` and ``_LockedState__status``.  As a result:
    #
    #   • Inside this class:  ``self.__value`` works — Python mangles it to
    #     ``self._LockedState__value`` in the class body automatically.
    #
    #   • Outside this class: ``ls.__value = x`` or ``ls._value = x`` both raise
    #     ``AttributeError`` — neither name matches the actual slot.  The only
    #     path to the raw value is the explicitly ugly ``ls._LockedState__value``,
    #     which is an unambiguous signal of deliberate bypass.
    #
    # See module docstring for the full three-layer bypass discussion.
    __slots__ = ("__value", "__status")

    def __init__(self, initial_value: T) -> None:
        """Initialize with ``initial_value``; status starts **fresh**."""
        self.__value: T = initial_value
        self.__status: _Status = _Status.FRESH

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    def is_fresh(self) -> bool:
        """Return ``True`` if the value has been updated this timestep."""
        return self.__status is _Status.FRESH

    def is_stale(self) -> bool:
        """Return ``True`` if the value has not yet been updated this timestep."""
        return self.__status is _Status.STALE

    # ------------------------------------------------------------------
    # Read with status assertion
    # ------------------------------------------------------------------

    def get_fresh(self) -> T:
        """Return the value, asserting it is fresh.

        Raises:
            StaleAccessError: The value has not been updated this timestep.

        """
        if self.__status is _Status.STALE:
            raise StaleAccessError("LockedState is stale — call update() before get_fresh().")
        return self.__value

    def get_stale(self) -> T:
        """Return the value, asserting it is stale (i.e. from the previous timestep).

        Raises:
            FreshAccessError: The value has already been updated this timestep.

        """
        if self.__status is _Status.FRESH:
            raise FreshAccessError(
                "LockedState is fresh — call mark_stale() before get_stale(), "
                "or use get_fresh() to read the current value.",
            )
        return self.__value

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def update(self, value: T) -> None:
        """Write a new value and mark fresh.

        Raises:
            DoubleWriteError: The value has already been updated this timestep.

        """
        if self.__status is _Status.FRESH:
            raise DoubleWriteError("LockedState is already fresh — call mark_stale() before updating again.")
        self.__value = value
        self.__status = _Status.FRESH

    def increment(self, delta: T) -> None:
        """Add ``delta`` to the current value and mark fresh.

        For accumulator-style state (e.g. cumulative extracted energy) that
        must be updated by ``+=`` rather than whole-value replacement, while
        still enforcing the same "exactly once per timestep" contract as
        ``update()``. Only meaningful for a ``T`` that supports ``+``.

        Raises:
            DoubleWriteError: The value has already been updated this timestep.

        """
        if self.__status is _Status.FRESH:
            raise DoubleWriteError("LockedState is already fresh — call mark_stale() before updating again.")
        self.__value = self.__value + delta  # type: ignore[operator]
        self.__status = _Status.FRESH

    # ------------------------------------------------------------------
    # Timestep boundary
    # ------------------------------------------------------------------

    def mark_stale(self) -> None:
        """Mark as stale, opening the write slot for the next timestep."""
        self.__status = _Status.STALE

    def mark_fresh(self) -> None:
        """Assert stale, then mark fresh WITHOUT writing a new value.

        For the case where a value is being treated as already-current by
        some other means (e.g. restored from a snapshot/reconstruction that
        doesn't go through the normal ``solve()`` write path) and just
        needs its write-once guard opened up for reading, not recomputed.
        Distinct from ``update()``, which requires (and consumes) a new
        value. ``StateMethods.mark_fresh()`` (``core/state_methods.py``)
        calls this recursively; ``LockedState`` itself has no dependency on
        that module.

        Raises:
            FreshAccessError: The value is already fresh — mirrors
                ``update()``'s own guard, since forcing an already-fresh
                value fresh again would silently mask a real double-write.

        """
        if self.__status is _Status.FRESH:
            raise FreshAccessError("LockedState is already fresh — call mark_stale() before mark_fresh().")
        self.__status = _Status.FRESH

    def check_and_reset(self) -> None:
        """Assert fresh, then mark stale.

        Combines end-of-timestep validation with advance: verifies that
        ``update()`` was called during the solve, then resets for the next
        timestep.  Raises ``StaleAccessError`` if the value was never updated.

        """
        if self.__status is _Status.STALE:
            raise StaleAccessError(
                "LockedState is still stale at check_and_reset() — update() was never called this timestep.",
            )
        self.__status = _Status.STALE

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        """Return a string showing the value and current status."""
        status = "fresh" if self.is_fresh() else "stale"
        return f"LockedState({self.__value!r}, {status})"

    # ------------------------------------------------------------------
    # Pydantic v2 transparent serialization
    # ------------------------------------------------------------------

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: pydantic.GetCoreSchemaHandler,
    ) -> Any:
        """Teach pydantic v2 to treat LockedState as a transparent wrapper.

        Serialization: ``LockedState(v)`` → ``v`` (just the raw value).
        Validation/deserialization: plain ``v`` → ``LockedState(v)`` starting
        **fresh** (readable immediately via ``get_fresh()``, same as any
        newly-constructed ``LockedState`` — see ``__init__``).

        This means that in any YAML/JSON save file, a ``LockedState[float]``
        field appears as a bare float with no ``value``/``status`` keys — the
        ``LockedState`` wrapper is invisible to the serialized format.
        """
        import pydantic_core  # noqa: PLC0415

        args = get_args(source_type)
        inner_type: Any = args[0] if args else Any
        inner_schema = handler(inner_type)

        inner_validator = pydantic_core.SchemaValidator(inner_schema)

        def _validate(v: object) -> LockedState[Any]:
            if isinstance(v, LockedState):
                return v
            # Plain value from YAML/JSON/msgpack → validate inner type then wrap.
            validated = inner_validator.validate_python(v)
            return cls(validated)

        return pydantic_core.core_schema.no_info_plain_validator_function(
            _validate,
            serialization=pydantic_core.core_schema.plain_serializer_function_ser_schema(
                # Access via mangled name — intentional, documented bypass.
                lambda ls: ls._LockedState__value,
                info_arg=False,
            ),
        )
