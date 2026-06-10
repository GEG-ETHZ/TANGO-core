"""Abstract base for economic components in tango_next."""

from __future__ import annotations

from abc import abstractmethod

from pydantic import ConfigDict

from tango_next.core.component import Component, ComponentSpec


class EconomicSpec(ComponentSpec):
    """Base specification for economic components."""

    model_config = ConfigDict(frozen=True)

    project_maturity: str
    """Project maturity stage: 'green_field' or 'brown_field'."""
    discount_rate: float
    """Discount rate as a dimensionless fraction (e.g. 0.095 = 9.5%)."""


class EconomicComponent(Component):
    """Abstract base for economic components.

    Economic components run after all physical timesteps are complete
    and compute project-level metrics (NPV, LCOE, IRR, etc.) from
    the accumulated simulation results.
    """

    @property
    @abstractmethod
    def spec(self) -> EconomicSpec:
        """The typed economic specification."""
        ...

    @abstractmethod
    def solve(self) -> None:
        """Compute economic metrics from accumulated physical simulation results."""
        ...
