"""Custom exceptions for tango_next."""

from __future__ import annotations


class TangoNextError(Exception):
    """Base class for all tango_next errors."""


class ConvergenceError(TangoNextError):
    """Raised when an iterative solver fails to converge within its iteration budget."""


class ComponentSolveError(TangoNextError):
    """Raised when a component's solve() encounters an unrecoverable error."""


class SaturationError(TangoNextError):
    """Raised when a fluid state unexpectedly enters or approaches a two-phase region."""


class ConfigError(TangoNextError):
    """Raised when an input configuration is invalid or inconsistent."""


class CoolPropError(TangoNextError):
    """Wraps a CoolProp failure raised by *our own* direct property lookup.

    Callers at any layer of the stack can ``except CoolPropError`` to know
    immediately that a fluid-property lookup is in the error chain, rather
    than catching a bare ``ValueError`` or CoolProp's own internal exception
    type. See ``core/fluid_state.py`` for where this is raised.

    For a CoolProp failure that surfaces *through* TESPy (TESPy calls
    CoolProp internally during its network solve), use
    ``TESPyCoolPropError`` instead — it subclasses both this class and
    ``TESPyError`` so it's catchable either way.
    """


class TESPyError(TangoNextError):
    """Wraps a failure raised by the TESPy network solver itself.

    Use this for TESPy failures unrelated to fluid-property lookups (e.g.
    network non-convergence, infeasible component specification). If the
    root cause is a CoolProp property lookup failing *inside* a TESPy solve,
    raise ``TESPyCoolPropError`` instead so it's still catchable as a
    CoolProp-rooted error.

    Not yet wired to any call site — ``tango_next`` has no TESPy integration
    yet (``SingleFlashSurface`` is a Phase 1 placeholder). This class exists
    so the error taxonomy is ready when the real TESPy-based power plant
    lands (see vision doc, Future Direction — AI-Assisted Error
    Interpretation, for why this taxonomy matters).
    """


class TESPyCoolPropError(TESPyError, CoolPropError):
    """Wraps a CoolProp failure that surfaced through a TESPy network solve.

    Inherits from both ``TESPyError`` and ``CoolPropError`` so callers can
    catch either: ``except TESPyError`` to catch any TESPy-related failure,
    or ``except CoolPropError`` to catch any CoolProp-rooted failure
    regardless of whether it was raised directly or via TESPy.

    Not yet wired to any call site — see ``TESPyError`` docstring.
    """


class LockedStateError(TangoNextError):
    """Base class for all LockedState contract violations."""


class StaleAccessError(LockedStateError):
    """Raised by ``LockedState.get_fresh()`` when the field has not been set yet this timestep."""


class FreshAccessError(LockedStateError):
    """Raised by ``LockedState.get_stale()`` when the field has already been updated this timestep."""


class DoubleWriteError(LockedStateError):
    """Raised by ``LockedState.set()`` when the field has already been set once this timestep."""
