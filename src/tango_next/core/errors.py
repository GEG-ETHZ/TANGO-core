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
