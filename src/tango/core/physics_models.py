"""Selectable physics-model enums and dispatch functions for tango.

Several physical phenomena have multiple competing correlations in the
literature (e.g. friction factor, wellbore heat loss). Rather than hardcoding
one choice per component, each such phenomenon gets a ``StrEnum`` (selectable
via a YAML spec field, default matching whatever was already implemented) and
a dispatch function here that maps the enum value to the underlying formula
in ``core/fluid_utils.py``.

To add a new variant of an existing model: add the formula to
``fluid_utils.py``, add an enum member here, and add a branch to the
corresponding dispatch function. To add an entirely new selectable model
(e.g. a future reservoir-flow model choice): follow this same pattern with a
new enum + dispatch function, rather than hardcoding the choice in the
component.
"""

from __future__ import annotations

import enum

from tango.core.fluid_utils import (
    friction_factor_darcy,
    friction_factor_haaland,
    heat_loss_zhang_2011,
)


class FrictionModel(enum.StrEnum):
    """Selects which Darcy-Weisbach friction-factor correlation to use."""

    HAALAND = "haaland"
    """Haaland (1983) explicit approximation (docs/SOURCES.md#haaland1983).
    Default; the discretized wellbore models are pinned to this variant."""

    SWAMEE_JAIN = "swamee-jain"
    """Swamee-Jain (1976) explicit approximation (docs/SOURCES.md#swameejain1976) — see
    fluid_utils.friction_factor_darcy's docstring for the "human review
    needed" caveat."""


class HeatTransferModel(enum.StrEnum):
    """Selects which wellbore radial heat-loss correlation to use."""

    ZHANG_2011 = "zhang-2011"
    """
    Zhang et al. (2011) transient conductive heat-loss correlation
    (dimensionless-time beta). Default.

    See docs/SOURCES.md#zhang2011 and fluid_utils.heat_loss_zhang_2011.
    """

    NONE = "none"
    """Perfectly insulated wellbore — zero heat loss. Matches the
    simplification used by LumpedInjectionWell / LumpedProductionWell."""


def compute_friction_factor(
    model: FrictionModel,
    Re: float,
    diameter: float,
    roughness: float,
) -> float:
    """Dispatch to the friction-factor formula selected by ``model``."""
    if model == FrictionModel.HAALAND:
        return friction_factor_haaland(Re, diameter, roughness)
    if model == FrictionModel.SWAMEE_JAIN:
        return friction_factor_darcy(Re, diameter, roughness)
    raise ValueError(f"Unhandled FrictionModel: {model!r}")  # pragma: no cover — exhaustive enum


def compute_heat_loss(
    model: HeatTransferModel,
    *,
    dL: float,
    rock_k: float,
    t_d: float,
    delta_T: float,
) -> float:
    """Dispatch to the wellbore heat-loss formula selected by ``model`` (W)."""
    if model == HeatTransferModel.ZHANG_2011:
        return heat_loss_zhang_2011(dL, rock_k, t_d, delta_T)
    if model == HeatTransferModel.NONE:
        return 0.0
    raise ValueError(f"Unhandled HeatTransferModel: {model!r}")  # pragma: no cover — exhaustive enum
