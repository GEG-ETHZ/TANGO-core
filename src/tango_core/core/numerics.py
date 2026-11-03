# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Small, dependency-free numerical root-finding helpers for tango.

Kept separate from any one component so multiple components can share the
same convergence contract (real tolerance check, no fixed iteration count)
without duplicating the loop itself.
"""

from __future__ import annotations

from collections.abc import Callable

from tango_core.core.errors import ConvergenceError

# Shared defaults for the production-well pump-boost convergence
# (LumpedProductionWellWithPump/NumericalProductionWellWithPump) — kept here,
# not duplicated per module, so both stay in sync.
PUMP_BOOST_TOL_PA = 1.0
PUMP_BOOST_MAX_ITER = 20


def secant_solve(
    residual: Callable[[float], float],
    x0: float,
    x1: float,
    tol: float,
    max_iter: int,
    error_context: str,
) -> float:
    """Find a root of ``residual`` via the secant method.

    Evaluates ``residual(x0)``/``residual(x1)`` first — if ``x1`` already
    satisfies ``tol``, returns immediately without computing a third point.
    Otherwise iterates the standard secant update
    ``x_{n+1} = x_n - f(x_n) * (x_n - x_{n-1}) / (f(x_n) - f(x_{n-1}))``
    until convergence or ``max_iter`` is exhausted.

    Args:
        residual: ``(x) -> f(x)``; a root (``f(x) = 0``) is being sought.
        x0: First initial guess.
        x1: Second initial guess (should differ meaningfully from ``x0``).
        tol: Convergence tolerance on ``abs(residual(x))``.
        max_iter: Maximum number of ADDITIONAL evaluations beyond the initial
            ``x0``/``x1`` pair before raising.
        error_context: Prefix for the ``ConvergenceError`` message, so a
            caller-specific failure is identifiable without a traceback.

    Raises:
        ConvergenceError: If ``max_iter`` is exhausted without ``tol`` being
            met, or if two consecutive residuals are identical (the secant
            step's denominator would be zero — no further progress possible).

    """
    f0 = residual(x0)
    f1 = residual(x1)
    if abs(f1) < tol:
        return x1

    for _ in range(max_iter):
        if f1 == f0:
            raise ConvergenceError(
                f"{error_context}: secant method stalled — two consecutive residuals "
                f"were identical ({f1:.6g}), no further progress possible.",
            )
        x2 = x1 - f1 * (x1 - x0) / (f1 - f0)
        f2 = residual(x2)
        if abs(f2) < tol:
            return x2
        x0, f0 = x1, f1
        x1, f1 = x2, f2

    raise ConvergenceError(
        f"{error_context}: secant method did not converge within {max_iter} iterations "
        f"(final residual={f1:.6g}, tol={tol:.6g}).",
    )
