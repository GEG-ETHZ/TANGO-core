"""Abstract base for economic components in tango_next."""

from __future__ import annotations

from abc import abstractmethod

from tango_next.core.component import Component


class EconomicComponent(Component):
    """Abstract base for economic components.

    Economic components run after all physical timesteps are complete
    and compute project-level metrics (NPV, LCOE, IRR, etc.) from
    the accumulated simulation results.
    """

    project_maturity: str
    """Project maturity stage: 'green_field' or 'brown_field'."""
    discount_rate: float
    """Discount rate as a dimensionless fraction (e.g. 0.095 = 9.5%)."""

    @abstractmethod
    def solve(self) -> None:
        """Compute economic metrics from accumulated physical simulation results."""
        ...
