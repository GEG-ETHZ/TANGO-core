"""Abstract base for economic components in tango."""

from __future__ import annotations

from abc import abstractmethod

from pydantic import Field, PositiveFloat, PrivateAttr

from tango_core.core.component import Component, FlowComponent
from tango_core.core.policies import MainProduct, ProjectMaturity


class EconomicComponent(Component):
    """Abstract base for economic components.

    Economic components run exactly once, after all physical timesteps are
    complete, and compute project-level metrics (CAPEX, LCOE, etc.) from the
    other components' final solved state — not once per timestep like every
    other component. It is a plain ``Component``, not a ``FlowComponent``:
    no fluid flows through it, so it has no ``inlet``/``outlet`` and its
    ``solve()`` takes no inlet. See ``SystemDirect.finalize()`` and
    ``Workflow._build_economic_component()`` for how this is wired: an
    economic component is deliberately excluded from the per-timestep
    ``_ordered``/``_by_idx`` circuit (no ``prev``/``next``), and instead
    receives every other component by
    reference (``self._components``, set by the orchestrator immediately
    before calling ``solve()``) — see ``DoubletEconomicComponent`` for the
    concrete implementation.

    ``_components``/``_total_years`` are declared ``PrivateAttr`` (rather
    than left as bare, undeclared attributes the way ``GraphSurface``'s
    TESPy network is — see that class's docstring) specifically so
    external callers (``SystemDirect.finalize()``, ``Workflow.__init__``)
    setting them from OUTSIDE this class type-check under mypy; a bare
    undeclared assignment only type-checks from within the defining
    class's own methods.
    """

    _components: dict[str, FlowComponent] = PrivateAttr(default_factory=dict)
    """Every other component in the Workflow, keyed by YAML name — set by
    ``SystemDirect.finalize()`` immediately before calling ``solve()``."""
    _total_years: PositiveFloat = PrivateAttr(default=float("nan"))
    """Total simulated project lifetime (``num_tsteps * dt_years``) — set
    by ``Workflow.__init__`` (this component has no ``sim_config`` access
    of its own)."""

    project_maturity: ProjectMaturity = Field(frozen=True)
    """Whether wells/permitting/exploration already exist (BROWN_FIELD) or
    must still be paid for (GREEN_FIELD)."""
    discount_rate: float = Field(frozen=True)
    """Discount rate as a dimensionless fraction (e.g. 0.095 = 9.5%)."""
    main_product: MainProduct = Field(default=MainProduct.ELECTRICITY, frozen=True)
    """Which output is the plant's primary product — determines LCOE vs LCOH."""

    @abstractmethod
    def solve(self) -> None:
        """Compute economic metrics from the other components' final solved state.

        Reads sibling components via ``self._components`` (a private,
        non-Pydantic attribute set by the orchestrator right before this
        call — see the class docstring).
        """
        ...
