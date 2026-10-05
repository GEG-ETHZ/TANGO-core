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


class NegativeNetPowerError(InvalidPowerStateError):
    """Raised when a power plant with a turbine is a net consumer of electricity.

    The turbine's output no longer covers the plant's own pump load, e.g.
    once the reservoir has cooled. Kept distinct from the other
    ``InvalidPowerStateError`` cases because it doesn't depend on whether a
    ``PumpOrValve`` node resolves to a valve or a pump: as a pump it would
    only draw more power, so ``GraphSurface`` re-raises it rather than
    retrying with the pump.
    """


class PassivePressureRiseError(InvalidPowerStateError):
    """Raised when a passive surface-plant component raises its fluid's pressure.

    Heat exchangers, valves, separators, mixers and cycle closers do no
    work, so pressure can only fall (or stay level) across them. TESPy
    solves such a network anyway when a component has a fixed absolute
    outlet pressure above what actually arrives at its inlet: the
    component compresses the fluid for free, and the pump work that rise
    would really cost is never charged. A subclass of
    ``InvalidPowerStateError`` because the result is the same kind of
    error, uncharged work, and so that an optimizer treats it as an
    infeasible design point.
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

    ``GraphSurface`` raises the subclasses ``TESPyConvergenceError`` (the
    solve didn't converge) and ``TESPyCoolPropError`` (a property lookup
    failed inside the solve).
    """


class TESPyConvergenceError(TESPyError, ConvergenceError):
    """Raised when a TESPy network solve returns without converging.

    TESPy's ``Network.solve()`` returns normally when it stops short of its
    convergence tolerance, leaving outlet values that may be wrong. A
    subclass of ``ConvergenceError`` too, so an optimizer treats it as an
    infeasible design point.
    """


class TESPyCoolPropError(TESPyError, CoolPropError):
    """Wraps a CoolProp failure that surfaced through a TESPy network solve.

    Inherits from both ``TESPyError`` and ``CoolPropError`` so callers can
    catch either: ``except TESPyError`` to catch any TESPy-related failure,
    or ``except CoolPropError`` to catch any CoolProp-rooted failure
    regardless of whether it was raised directly or via TESPy.
    """


class LockedStateError(TangoError):
    """Base class for all LockedState contract violations."""


class StaleAccessError(LockedStateError):
    """Raised by ``LockedState.get_fresh()`` when the field has not been set yet this timestep."""


class FreshAccessError(LockedStateError):
    """Raised by ``LockedState.get_stale()`` when the field has already been updated this timestep."""


class DoubleWriteError(LockedStateError):
    """Raised by ``LockedState.set()`` when the field has already been set once this timestep."""
