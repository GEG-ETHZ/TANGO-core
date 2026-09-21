"""Custom exceptions for tango."""

from __future__ import annotations


class TangoError(Exception):
    """Base class for all tango errors."""


class ConvergenceError(TangoError):
    """Raised when an iterative solver fails to converge within its iteration budget."""


class ComponentSolveError(TangoError):
    """Raised when a component's solve() encounters an unrecoverable error."""


class SaturationError(TangoError):
    """Raised when a fluid state unexpectedly enters or approaches a two-phase region."""


class ConfigError(TangoError):
    """Raised when an input configuration is invalid or inconsistent."""


class FrackingViolationError(TangoError):
    """Raised when injection would exceed a hydraulic-fracking threshold.

    Covers both mechanisms ``InjectionPolicy`` distinguishes (see
    ``core/policies.py``): flow-induced (mass rate too high) and
    pressure-induced (wellhead pressure too high after hydrostatic head and
    friction losses). Catch this specifically to distinguish "the reservoir
    would be damaged by this injection schedule" from any other simulation
    failure (e.g. a fluid-property lookup error or non-convergence).

    Deliberately raised rather than silently capping the offending value
    down to a safe threshold: a silent correction would let a caller mistake
    a corrected-but-different run for the one they actually asked for, with
    no signal that anything was adjusted. Surfacing it as an explicit,
    specifically-typed error keeps that decision visible and in the
    caller's hands.
    """


class InvalidPowerStateError(TangoError):
    """Raised when a component reports a power value that is physically invalid.

    Covers two known-fragile spots near a design's feasibility boundary:
    a passive downhole pump reporting *negative* power draw (``pump_power_watts
    < 0`` — a pump cannot generate power), and a surface plant reporting
    negative net electric output for a timestep (``net_power_W < 0`` fed into
    an averaged economic calculation). Both were observed silently producing
    a deceptively low LCOE (a negative pump term was fed into
    ``DoubletEconomicComponent._read_net_power`` unclamped, flipping a
    subtraction into an addition) rather than an explicit failure. Deliberately
    raised rather than clamped to zero, for the same reason as
    ``FrackingViolationError``: a silent correction would let a caller mistake
    a corrected-but-different run for the one they actually asked for.
    """


class CoolPropError(TangoError):
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


class TESPyError(TangoError):
    """Wraps a failure raised by the TESPy network solver itself.

    Use this for TESPy failures unrelated to fluid-property lookups (e.g.
    network non-convergence, infeasible component specification). If the
    root cause is a CoolProp property lookup failing *inside* a TESPy solve,
    raise ``TESPyCoolPropError`` instead so it's still catchable as a
    CoolProp-rooted error.

    TESPy integration is real (``GraphSurface`` solves an actual TESPy
    ``Network`` each timestep), but no call site wraps a TESPy solve failure
    in this class yet — ``GraphSurface.solve()`` lets TESPy's own exceptions
    propagate directly. This class exists so the error taxonomy is ready to
    wrap those failures (see vision doc, Future Direction — AI-Assisted
    Error Interpretation, for why this taxonomy matters).
    """


class TESPyCoolPropError(TESPyError, CoolPropError):
    """Wraps a CoolProp failure that surfaced through a TESPy network solve.

    Inherits from both ``TESPyError`` and ``CoolPropError`` so callers can
    catch either: ``except TESPyError`` to catch any TESPy-related failure,
    or ``except CoolPropError`` to catch any CoolProp-rooted failure
    regardless of whether it was raised directly or via TESPy.

    Not yet wired to any call site — see ``TESPyError`` docstring.
    """


class LockedStateError(TangoError):
    """Base class for all LockedState contract violations."""


class StaleAccessError(LockedStateError):
    """Raised by ``LockedState.get_fresh()`` when the field has not been set yet this timestep."""


class FreshAccessError(LockedStateError):
    """Raised by ``LockedState.get_stale()`` when the field has already been updated this timestep."""


class DoubleWriteError(LockedStateError):
    """Raised by ``LockedState.set()`` when the field has already been set once this timestep."""
