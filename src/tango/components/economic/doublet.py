r"""Doublet CAPEX/LCOE economic component for tango.

Computes total CAPEX (wells, permitting, exploration, surface pipes,
surface plant) and levelized cost (LCOE or LCOH, via ``MainProduct``) for
a hydrothermal DOUBLET topology — one injection well, one production well
(itself possibly split across several physics sub-components, or paired
with a separate horizontal loop segment — see ``_compute_well_capex``),
and a TESPy-node-based surface plant. Well costs use a single fixed
formula (the ``gengeo`` model — see ``_well_section_cost``); its three
coefficients are overridable ``Field``s, but the formula's SHAPE is not
configurable, and no alternative well-cost model is supported. Only H2O
is supported (no CO2-specific cost terms). This is not a general-purpose
economic engine — it covers exactly the well/surface-plant shapes tango's
own templates use today, nothing broader.

Runs exactly once, after every physical timestep completes — see
``EconomicComponent``'s (``base.py``) and ``SystemDirect.finalize()``'s
docstrings for why. Surface-plant CAPEX sizing and the LCOE denominator use
the RUN-AVERAGED power/heat-duty of each turbine/pump/condenser node — the
simple arithmetic mean over every recorded timestep, not any single
timestep's snapshot — since a single timestep's value isn't representative
of the plant's actual annual output/cost basis the way a full-run average is.

Sign convention: ``GraphSurface``'s own TESPy wiring gives pumps POSITIVE
node power (consumes energy) and turbines NEGATIVE (generates energy). Every
cost formula that takes a fractional-exponent power of a raw node value
(e.g. a pump/turbine equipment-cost curve) applies ``abs()`` to that value
first, so it stays correct regardless of a given plant topology's exact
port wiring — a bare negative number raised to a fractional power would
otherwise silently NaN.

Known scope limits (real gaps, not oversights — flagged so a caller can
tell a config is hitting one rather than assume a wrong-looking number is
a bug):
- **Direct-heat district-heating exchanger equipment cost is not costed at
  all.** A plain district-heating ``SimpleHeatExchanger`` node isn't
  recognized by any surface-plant cost formula here (those only recognize
  cooler/condenser/turbine/pump-style equipment), so ``CAPEX_surface_plant``
  comes back exactly ``0.0`` for a pure direct-heat topology (e.g. AGS/EGS
  direct-heat configs). ``CAPEX_total``/LCOH for such a config is therefore
  real but understates true cost until a district-heat-exchanger cost
  formula is added.
- **No production-well-pump "lineshaft" cost add-on.** Would only ever
  apply when a production pump's average power is negative;
  ``LumpedProductionWellWithPump.pump_power_watts`` (``well/lumped.py``) is
  non-negative by construction, so that condition can never arise here.
- **No cost-year/PPI-table interpolation.** Uses a single fixed-year
  cost-index snapshot (``core/economic_constants.py``) rather than
  interpolating by calendar year, since tango has no calendar concept
  (no ``start_date``) yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import Field

from tango.components.economic.base import EconomicComponent
from tango.components.surface.base import SurfaceComponent
from tango.components.well.base import WellComponent
from tango.core.constants import W_TO_KW, YEAR_TO_HOUR
from tango.core.economic_constants import (
    BEC_MARKUP,
    EXPLORATION_BASE_COST_USD,
    PERMITTING_BASE_COST_USD,
    PPI_O_AND_G,
    PPI_O_AND_G_S,
    PPI_PE,
    PPI_PERMIT,
    PPI_PIPE,
    PPI_PUMP,
    PPI_T_G,
    TEC_MULTIPLIER,
    X_IC_SURFACE,
    X_IC_WELLS,
    X_PC_SURFACE,
    X_PC_WELLS,
)
from tango.core.locked_state import LockedState
from tango.core.policies import MainProduct, ProjectMaturity
from tango.core.state_methods import StateMethods

if TYPE_CHECKING:
    from tango.core.component import FlowComponent

# Default probability of success; not exposed as a tango config field
# since nothing varies it yet.
_DEFAULT_PROBABILITY_OF_SUCCESS: float = 0.95

# NumericalWell's angle_from_vert_deg convention (0 = injection, 180 =
# production, 90 = horizontal — see components/well/numerical.py's module
# docstring). Only NumericalWell carries this field at all; getattr(...,
# None) below defaults any well type lacking it (e.g. the Lumped* classes,
# which have no horizontal variant yet) to "not horizontal".
_HORIZONTAL_ANGLE_DEG: float = 90.0


def _is_horizontal(well: WellComponent) -> bool:
    """True if ``well`` is a horizontal segment (e.g. AGS's ``horizontal_well``).

    Used to exclude horizontal segments from the vertical production well's
    combined-length/single-diameter costing — see
    ``DoubletEconomicComponent._compute_well_capex``'s docstring for why a
    horizontal segment is costed as its own separate well section instead.
    """
    return getattr(well, "angle_from_vert_deg", None) == _HORIZONTAL_ANGLE_DEG


# Default temperature range, unset by every example this component is
# scoped to — see the BAC regression note below.
_DEFAULT_TEMPERATURE_RANGE_K: float = 0.0

_BAC_COEFFS_WET: dict[str, tuple[float, float, float, float]] = {
    "cooling": (5.58e3, 0.0, -1.77e1, 1.96e2),
    "condensing": (4.08e3, -1.54e-2, -1.24e1, 0.0),
}
_BAC_COEFFS_DRY: dict[str, tuple[float, float, float, float]] = {
    "cooling": (7.31e3, 0.0, 0.0, 1.23e3),
    "condensing": (1.91e3, 0.0, 0.0, 0.0),
}
# Separate coefficient sets for PARASITIC POWER (cooling-tower fan/pump
# electricity, a fraction of heat duty) — surface.py's
# _get_parasitic_power_fraction_cooling/_condensing, NOT the cost
# coefficients above (same BAC-regression formula shape, different fitted
# constants). Needed for the LCOE denominator's net power, not for CAPEX.
_BAC_POWER_COEFFS_WET: dict[str, tuple[float, float, float, float]] = {
    "cooling": (1.2, 0.0, -3.79e-3, 1.95e-2),
    "condensing": (1.65, -6.24e-6, -5.03e-3, 0.0),
}
_BAC_POWER_COEFFS_DRY: dict[str, tuple[float, float, float, float]] = {
    "cooling": (7.65e-1, 0.0, 0.0, 1.28e-1),
    "condensing": (0.619, 0.0, 0.0, 0.0),
}
_TOWER_DESIGN_COEFFICIENT: dict[tuple[str, str], float] = {
    ("H2O", "CLOSED"): 1.0,
    ("H2O", "OPEN"): 0.252,
    ("CO2", "CLOSED"): 1.2,
    # ("CO2", "OPEN") unsupported.
}


def _bac_regression(
    coeffs: tuple[float, float, float, float],
    dt_approach: float,
    t_ambient: float,
    dt_range: float,
) -> float:
    """Baltimore Aircoil regression model shape.

    Shared by the cooler/condenser COST formula (``_BAC_COEFFS_WET``/``_DRY``)
    and the cooler/condenser PARASITIC POWER formula
    (``_BAC_POWER_COEFFS_WET``/``_DRY``) — same shape, different fitted
    coefficients depending on which quantity is being estimated.

    All temperature arguments are in Kelvin, matching every other
    temperature in tango — there is no unit conversion at this function's
    call sites, and none should be added without re-verifying the fitted
    coefficients against real reference output, since no original source
    for those coefficients is available to check the intended unit
    against directly.

    Args:
        coeffs: ``(a, b, c, d)`` fitted regression coefficients — one of
            ``_BAC_COEFFS_WET``/``_DRY`` (cost) or
            ``_BAC_POWER_COEFFS_WET``/``_DRY`` (parasitic power fraction).
        dt_approach: Approach temperature difference (K) — ``surface``'s
            own ``approach_temperature``.
        t_ambient: Ambient temperature (K) — ``common.surface_temperature``.
        dt_range: Condensation temperature range (K) — always
            ``_DEFAULT_TEMPERATURE_RANGE_K`` (0.0) at every call site in
            this module today; kept as its own parameter (rather than a
            hardcoded 0 inside this function) since it's a genuine,
            independent term in the BAC regression's own formula, not an
            artifact of how tango happens to call it.

    Returns:
        The regression's dimensionless output — either a cost multiplier
        or a parasitic-power fraction, depending on which ``coeffs`` set
        was passed in.
    """
    a, b, c, d = coeffs
    return a / dt_approach + b * t_ambient + c * t_ambient / dt_approach + d / (dt_approach + dt_range)


def _ls(value: float = 0.0) -> LockedState[float]:
    ls: LockedState[float] = LockedState(value)
    ls.mark_stale()
    return ls


@dataclass(frozen=True)
class EconomicState(StateMethods):
    """Final CAPEX/LCOE result of one ``DoubletEconomicComponent.solve()`` call.

    Computed exactly once (see module docstring) — unlike every other
    component's ``state``, this is never recomputed per-timestep, but still
    uses ``LockedState`` for consistency with the rest of tango's
    write-once-per-solve convention. Deliberately has no ``*History``
    analog (see ``CONTRIBUTING.md``'s ``*State``/``*History`` parity
    commandment for this exception) — ``EconomicComponent`` runs exactly
    once, via ``finalize()``, never through ``record()``.
    """

    CAPEX_well: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Capital cost of the injection, horizontal, and production wells, divided by the drilling
    success probability ($); only the production well is charged for ``BROWN_FIELD``."""
    CAPEX_permitting: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Capital cost of permitting ($)."""
    CAPEX_exploration: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Capital cost of exploration ($)."""
    CAPEX_surface_pipes: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Capital cost of the surface pipe between the two wellheads, one run of length ``well_spacing`` ($)."""
    CAPEX_surface_plant: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Capital cost of the surface-plant equipment ($)."""
    CAPEX_total: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Sum of all CAPEX categories above ($)."""
    net_power_W: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Run-averaged net electric power after parasitic loads (W)."""
    net_thermal_W: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Run-averaged net thermal power (W)."""
    LCOE: LockedState[float] = field(default_factory=lambda: _ls(float("nan")))
    """Levelized cost of the main product, electricity or heat ($/kWh); NaN when undefined."""
    specific_investment_cost: LockedState[float] = field(default_factory=lambda: _ls(float("nan")))
    """CAPEX_total per unit of main-product power ($/kW) -- see ``_compute_specific_investment_cost``."""
    OPEX: LockedState[float] = field(default_factory=lambda: _ls(float("nan")))  # noqa: N815
    """Net annual O&M cost ($/yr) -- see ``_compute_opex``."""


class DoubletEconomicComponent(EconomicComponent):
    """CAPEX + LCOE for a hydrothermal DOUBLET plant — see module docstring for scope."""

    capacity_factor: float = Field(default=0.9, frozen=True)
    """Plant capacity factor (dimensionless fraction)."""
    opex_cost_fraction: float = Field(default=0.045, frozen=True)
    """Base O&M cost as a fraction of CAPEX, before by-product revenue offset."""
    electricity_price: float = Field(default=0.25, frozen=True)
    """By-product electricity price ($/kWh) — used only when main_product is HEAT."""
    heat_price: float = Field(default=0.05, frozen=True)
    """By-product heat price ($/kWh) — used only when main_product is ELECTRICITY."""

    gengeo_quadratic_length_coeff: float = Field(default=0.105, frozen=True)
    """``_well_section_cost``'s ``L^2`` coefficient — economies-of-scale term
    on a well section's own combined depth. GenGEO's default cost basis;
    override from YAML if a different cost basis is needed."""
    gengeo_diameter_length_coeff: float = Field(default=1776.0, frozen=True)
    """``_well_section_cost``'s ``d*L`` coefficient (diameter- and
    length-dependent casing/material cost). GenGEO's default cost basis."""
    gengeo_mobilization_cost_usd: float = Field(default=275_300.0, frozen=True)
    """``_well_section_cost``'s fixed mobilization cost, charged once per
    well SECTION (see ``_compute_well_capex``'s docstring for what counts as
    one section). GenGEO's default cost basis."""

    state: EconomicState = Field(default_factory=EconomicState)
    """Final economic results, computed once after the last timestep."""

    def solve(self) -> None:
        """Compute CAPEX + LCOE from ``self._components`` (set by the orchestrator).

        Raises:
            RuntimeError: If called without ``self._components`` having been
                set first (i.e. called directly rather than via
                ``SystemDirect.finalize()``).

        """
        components: dict[str, FlowComponent] | None = getattr(self, "_components", None)
        if components is None:
            raise RuntimeError(
                "DoubletEconomicComponent.solve() requires self._components to be set "
                "first — call via SystemDirect.finalize(), not directly.",
            )
        s = self.state

        wells = [c for c in components.values() if isinstance(c, WellComponent)]
        surfaces = [c for c in components.values() if isinstance(c, SurfaceComponent)]
        surface = surfaces[0] if surfaces else None

        node_detail = self._averaged_node_detail(surface)

        capex_well = self._compute_well_capex(wells)
        capex_permitting = self._compute_permitting_capex()
        capex_exploration = self._compute_exploration_capex()
        capex_pipes = self._compute_surface_pipe_capex(surface)
        capex_plant = self._compute_surface_plant_capex(surface, node_detail)
        capex_total = capex_well + capex_permitting + capex_exploration + capex_pipes + capex_plant

        net_power_w, net_thermal_w = self._read_net_power(surface, node_detail, wells)

        s.CAPEX_well.update(capex_well)
        s.CAPEX_permitting.update(capex_permitting)
        s.CAPEX_exploration.update(capex_exploration)
        s.CAPEX_surface_pipes.update(capex_pipes)
        s.CAPEX_surface_plant.update(capex_plant)
        s.CAPEX_total.update(capex_total)
        s.net_power_W.update(net_power_w)
        s.net_thermal_W.update(net_thermal_w)
        s.LCOE.update(self._compute_lcoe(capex_total, net_power_w, net_thermal_w))
        s.specific_investment_cost.update(
            self._compute_specific_investment_cost(capex_total, net_power_w, net_thermal_w),
        )
        s.OPEX.update(self._compute_opex(capex_total, net_power_w, net_thermal_w))

    # ------------------------------------------------------------------
    # Wells (gengeo model only — see module docstring's scope-limit list)
    # ------------------------------------------------------------------

    def _well_section_cost(self, length_m: float, diameter_m: float) -> float:
        """One well "section"'s cost via the gengeo formula.

        ``C = X_IC * X_PC * PPI_O&G * (a*L^2 + b*d*L + c)``, where
        ``a``/``b``/``c`` are ``gengeo_quadratic_length_coeff``/
        ``gengeo_diameter_length_coeff``/``gengeo_mobilization_cost_usd``
        (H2O — the CO2-specific ``dC_CO2_well`` add-on is 0 for this fluid).
        """
        return (
            X_IC_WELLS
            * X_PC_WELLS
            * PPI_O_AND_G
            * (
                self.gengeo_quadratic_length_coeff * length_m**2
                + self.gengeo_diameter_length_coeff * diameter_m * length_m
                + self.gengeo_mobilization_cost_usd
            )
        )

    def _compute_well_capex(self, wells: list[WellComponent]) -> float:
        """Injection + horizontal-loop + production well CAPEX, DOUBLET pattern.

        The injection well is identified as the ``WellComponent`` at
        ``component_idx == 0`` (the circuit entry — see ``Component``'s
        class docstring). Every other ``WellComponent`` is split further by
        orientation (``_is_horizontal``): a HORIZONTAL segment (e.g. AGS's
        ``horizontal_well``, ``angle_from_vert_deg: 90``) is costed as its
        own, independent well section — it's a physically separate drilling
        operation from the vertical production well, so its own mobilization
        charge is correct, not double-counting. Everything remaining
        (VERTICAL production segments) is combined into one total depth
        before costing: a single physical production wellbore is sometimes
        represented by several ``WellComponent`` instances for physics/
        solve-order reasons (e.g. a lower section plus a separate upper
        section carrying a pump), and costing each sub-component as an
        independent well would double- (or triple-) count the gengeo
        formula's fixed mobilization term once per sub-component — not
        physically meaningful for what is structurally one wellbore. A
        horizontal segment does NOT have this double-counting risk with the
        vertical production well, since it's a genuinely separate wellbore,
        not a segment of the same one.
        """
        injection = [w for w in wells if w.component_idx == 0]
        others = [w for w in wells if w.component_idx != 0]
        horizontal = [w for w in others if _is_horizontal(w)]
        production = [w for w in others if not _is_horizontal(w)]

        cost_inj = 0.0
        cost_horizontal = 0.0
        if self.project_maturity != ProjectMaturity.BROWN_FIELD:
            cost_inj = sum(self._well_section_cost(w.well_length, w.diameter) for w in injection)
            cost_inj /= _DEFAULT_PROBABILITY_OF_SUCCESS
            cost_horizontal = sum(self._well_section_cost(w.well_length, w.diameter) for w in horizontal)
            cost_horizontal /= _DEFAULT_PROBABILITY_OF_SUCCESS

        prod_length, prod_diameter = self._combined_production_length_and_diameter(production)
        cost_prod = self._well_section_cost(prod_length, prod_diameter)
        cost_prod /= _DEFAULT_PROBABILITY_OF_SUCCESS

        return cost_inj + cost_horizontal + cost_prod

    def _combined_production_length_and_diameter(
        self,
        production: list[WellComponent],
    ) -> tuple[float, float]:
        """Combine every VERTICAL production-side ``WellComponent`` into one well's total depth.

        ``production`` excludes any horizontal segment (see
        ``_compute_well_capex``, which costs those separately) — this
        assumes only the remaining vertical segments of one production
        wellbore (e.g. a lower section + an upper section with a pump).

        Diameter: takes the (assumed uniform) diameter shared by every
        vertical production-side component — true in every example checked
        so far. Raises rather than silently picking one if that's ever not
        true: real multi-segment costing (varying outer/casing diameter by
        depth) is a planned tango feature, not built yet (see
        ``docs/tango_tasks.md``'s open items) — silently ignoring a
        real diameter difference here would misrepresent cost rather than
        just being an approximation.
        """
        if not production:
            return 0.0, 0.0
        total_length = sum(w.well_length for w in production)
        diameters = {w.diameter for w in production}
        if len(diameters) > 1:
            raise ValueError(
                f"Production-side wells have differing diameters {sorted(diameters)!r} — "
                "DoubletEconomicComponent's well-cost model assumes one uniform diameter "
                "for the combined well until real multi-segment costing is built "
                "(see docs/tango_tasks.md's open items).",
            )
        return total_length, next(iter(diameters))

    # ------------------------------------------------------------------
    # Permitting / exploration (permitting.py, exploration.py — H2O only)
    # ------------------------------------------------------------------

    def _compute_permitting_capex(self) -> float:
        """``C = X_IC*X_PC*PPI_Permit*665700`` (H2O; 0 for BROWN_FIELD)."""
        if self.project_maturity == ProjectMaturity.BROWN_FIELD:
            return 0.0
        return X_IC_WELLS * X_PC_WELLS * PPI_PERMIT * PERMITTING_BASE_COST_USD

    def _compute_exploration_capex(self) -> float:
        """``C = X_IC*X_PC*PPI_O&G-s*508000`` (H2O; 0 for BROWN_FIELD)."""
        if self.project_maturity == ProjectMaturity.BROWN_FIELD:
            return 0.0
        return X_IC_WELLS * X_PC_WELLS * PPI_O_AND_G_S * EXPLORATION_BASE_COST_USD

    # ------------------------------------------------------------------
    # Surface gathering pipes (surface.py:59-96)
    # ------------------------------------------------------------------

    def _compute_surface_pipe_capex(self, surface: SurfaceComponent | None) -> float:
        """``C = X_PC*X_IC*PPI_Pipe*(2205*D^2+134)*L``, DOUBLET: L = well_spacing."""
        if surface is None:
            return 0.0
        length_m: float = getattr(surface, "well_spacing", 0.0)
        diameter_m = surface.pipe_diameter
        return X_PC_SURFACE * X_IC_SURFACE * PPI_PIPE * (2205.0 * diameter_m**2 + 134.0) * length_m

    # ------------------------------------------------------------------
    # Surface plant (surface.py's PowerPlantCost — flexible_pp path)
    # ------------------------------------------------------------------

    def _averaged_node_detail(self, surface: SurfaceComponent | None) -> dict[str, dict[str, float]]:
        """Mean of each node's P/Q (and any other recorded quantity) over the whole run.

        CAPEX sizing for a ``flexible_pp``-style surface plant uses the
        simple arithmetic mean of each component's power/heat-duty
        history, not any single timestep's value.
        """
        history = getattr(surface, "history", None)
        node_history: dict[str, dict[str, list[float]]] = getattr(history, "node_history", {})
        return {
            node_name: {
                quantity: (sum(values) / len(values) if values else 0.0)
                for quantity, values in quantities.items()
            }
            for node_name, quantities in node_history.items()
        }

    def _compute_surface_plant_capex(
        self,
        surface: SurfaceComponent | None,
        node_detail: dict[str, dict[str, float]],
    ) -> float:
        """Turbine-generator + injection-pump + cooler/condenser cost, markup-adjusted.

        Dispatches on ``power_plant.nodes.<name>.type`` (the same strings
        GraphSurface itself uses to build the TESPy network) rather than
        ``isinstance`` against TESPy classes directly — this component
        reads ``history.node_history``'s already-collected per-timestep P/Q
        values (averaged via ``_averaged_node_detail``, computed once in
        ``solve()`` and threaded through), not live TESPy objects, so it
        never needs to import ``tespy`` itself.
        """
        power_plant: dict[str, Any] = getattr(surface, "power_plant", {})
        node_cfgs: dict[str, dict[str, Any]] = power_plant.get("nodes", {})
        if not node_cfgs or not node_detail:
            return 0.0

        primary_equipment_cost = 0.0
        primary_equipment_cost += self._turbine_generator_cost(node_cfgs, node_detail)
        primary_equipment_cost += self._injection_pump_cost(node_cfgs, node_detail)
        primary_equipment_cost += self._cooler_condenser_cost(surface, node_cfgs, node_detail)

        total_equipment_cost = TEC_MULTIPLIER * primary_equipment_cost
        bare_erected_cost = total_equipment_cost * BEC_MARKUP
        return X_PC_SURFACE * X_IC_SURFACE * bare_erected_cost

    def _turbine_generator_cost(
        self,
        node_cfgs: dict[str, dict[str, Any]],
        node_detail: dict[str, dict[str, float]],
    ) -> float:
        """``Σ 0.67*PPI_T-G*(2830*(|W|/1e3)^0.745 + 3680*(|W|/1e3)^0.617)`` over Turbine nodes.

        ``S_T_fluid`` (turbine cost multiplier) is 1.0 for H2O — omitted
        (this component is H2O-only, see module docstring).
        """
        total = 0.0
        for name, cfg in node_cfgs.items():
            if cfg.get("type") != "Turbine":
                continue
            w_turbine = abs(node_detail.get(name, {}).get("P", 0.0))
            total += (
                0.67
                * PPI_T_G
                * (2830.0 * (w_turbine / 1.0e3) ** 0.745 + 3680.0 * (w_turbine / 1.0e3) ** 0.617)
            )
        return total

    def _injection_pump_cost(
        self,
        node_cfgs: dict[str, dict[str, Any]],
        node_detail: dict[str, dict[str, float]],
    ) -> float:
        """``Σ PPI_Pump*1750*(1.34*|W|/1e3)^0.7`` over Compressor nodes.

        ``S_pump`` (pump material cost multiplier) is 1.0 for H2O — omitted.
        """
        total = 0.0
        for name, cfg in node_cfgs.items():
            if cfg.get("type") != "Compressor":
                continue
            w_pump = abs(node_detail.get(name, {}).get("P", 0.0))
            total += PPI_PUMP * 1750.0 * (1.34 * w_pump / 1.0e3) ** 0.7
        return total

    def _cooler_condenser_cost(
        self,
        surface: SurfaceComponent | None,
        node_cfgs: dict[str, dict[str, Any]],
        node_detail: dict[str, dict[str, float]],
    ) -> float:
        """BAC regression cost, grouped by ``set_number`` (surface.py's cooler/condenser path).

        Every ``SimpleHeatExchanger`` node with ``Subtype: cooler`` or
        ``Subtype: condenser`` joins its ``set_number``'s group; a
        singleton set (condenser only, no paired cooler — the case for
        ``hydro_df_electric.yml``'s high_pressure_condenser/low_pressure_condenser) works
        correctly: ``F_cooling -> 0``, cost reduces to the condensing term
        alone.
        """
        if surface is None:
            return 0.0
        t_ambient = surface.common.surface_temperature
        dt_approach = surface.approach_temperature
        dt_range = _DEFAULT_TEMPERATURE_RANGE_K

        sets: dict[Any, dict[str, Any]] = {}
        for name, cfg in node_cfgs.items():
            if cfg.get("type") != "SimpleHeatExchanger":
                continue
            subtype = str(cfg.get("Subtype", "")).lower()
            if subtype not in ("cooler", "condenser"):
                continue
            set_number = cfg.get("set_number")
            if set_number is None:
                continue
            design = str(cfg.get("design", "closed")).upper()
            mode = str(cfg.get("cooling_tower_mode", "WET")).upper()
            entry = sets.setdefault(
                set_number,
                {"Q_cooler": 0.0, "Q_condenser": 0.0, "mode": mode, "design": design},
            )
            q = abs(node_detail.get(name, {}).get("Q", 0.0))
            entry["Q_cooler" if subtype == "cooler" else "Q_condenser"] = q

        total = 0.0
        q_ref_bac = 1.0e6
        for entry in sets.values():
            coeffs = _BAC_COEFFS_WET if entry["mode"] == "WET" else _BAC_COEFFS_DRY
            tdc = _TOWER_DESIGN_COEFFICIENT[(surface.common.fluid_name, entry["design"])]

            q_cooler = entry["Q_cooler"]
            q_condenser = entry["Q_condenser"]
            f_cooling = q_cooler / (q_cooler + q_condenser + 1e-10)
            bac_cooling = _bac_regression(coeffs["cooling"], dt_approach, t_ambient, dt_range)
            bac_condensing = _bac_regression(coeffs["condensing"], dt_approach, t_ambient, dt_range)
            c_ref_bac = (
                PPI_PE
                * q_ref_bac
                * tdc
                * (f_cooling * (bac_cooling / 1e3) + (1 - f_cooling) * (bac_condensing / 1e3))
            )
            total += c_ref_bac * ((q_cooler + q_condenser) / q_ref_bac) ** 0.8
        return total

    def _cooling_condenser_parasitic_power(
        self,
        surface: SurfaceComponent | None,
        node_cfgs: dict[str, dict[str, Any]],
        node_detail: dict[str, dict[str, float]],
    ) -> float:
        """Cooling-tower/condenser parasitic electric power (W) — surface.py's ``compute_cooler_condenser_power``.

        Unlike the COST formula (which groups cooler+condenser by
        ``set_number`` into one combined per-set calculation), this is a
        plain per-node sum: each cooler/condenser's own averaged heat duty
        times its own parasitic-power fraction (same BAC-regression
        formula shape as the cost path, POWER coefficients instead of cost
        coefficients — ``_BAC_POWER_COEFFS_WET``/``_DRY``). Subtracted from
        gross electric output in ``_read_net_power`` — this is real
        cooling-tower fan/pump electricity consumption, not thermal duty.
        """
        if surface is None:
            return 0.0
        t_ambient = surface.common.surface_temperature
        dt_approach = surface.approach_temperature
        dt_range = _DEFAULT_TEMPERATURE_RANGE_K

        total = 0.0
        for name, cfg in node_cfgs.items():
            if cfg.get("type") != "SimpleHeatExchanger":
                continue
            subtype = str(cfg.get("Subtype", "")).lower()
            if subtype not in ("cooler", "condenser"):
                continue
            mode = str(cfg.get("cooling_tower_mode", "WET")).upper()
            coeffs = _BAC_POWER_COEFFS_WET if mode == "WET" else _BAC_POWER_COEFFS_DRY
            coeffs_key = "cooling" if subtype == "cooler" else "condensing"
            q = abs(node_detail.get(name, {}).get("Q", 0.0))
            fraction = _bac_regression(coeffs[coeffs_key], dt_approach, t_ambient, dt_range)
            total += q * fraction
        return total

    def _production_pump_parasitic_power(self, wells: list[WellComponent]) -> float:
        """Mean downhole production-pump power draw (W) over the whole run.

        Subtracted (given tango's non-negative sign convention — see this
        module's own "Sign convention" note above) into
        ``compute_net_power()`` separately from the surface TESPy network
        — the production well's downhole pump isn't a ``power_plant`` node
        at all, so this can't come from ``node_detail``/``node_history``.
        """
        total = 0.0
        for w in wells:
            if w.component_idx == 0:
                continue
            history = getattr(w, "history", None)
            pump_history: list[float] = getattr(history, "pump_power_watts", [])
            if pump_history:
                total += sum(pump_history) / len(pump_history)
        return total

    # ------------------------------------------------------------------
    # LCOE (economic.py:588-634)
    # ------------------------------------------------------------------

    def _read_net_power(
        self,
        surface: SurfaceComponent | None,
        node_detail: dict[str, dict[str, float]],
        wells: list[WellComponent],
    ) -> tuple[float, float]:
        """Run-averaged net electric/thermal power (W) — see module docstring.

        Net electric power is ``turbine + surface_pump -
        (cooling_parasitic + condensing_parasitic) -
        production_downhole_pump``. The first term is already correctly
        netted in ``GraphSurface.history.net_power_W`` (a per-timestep sum
        of signed node contributions — turbines positive, surface pumps
        negative — see that class's docstring); mean-of-sum equals
        sum-of-means since the mean is linear, so averaging that series is
        exactly equivalent to separately averaging then summing the
        turbine/pump terms, not merely an approximation. The remaining two
        terms (cooling-tower/condenser parasitic power, production
        downhole pump) are NOT part of that surface-node sum at all —
        this component adds them at the economic layer specifically (see
        ``_cooling_condenser_parasitic_power``/
        ``_production_pump_parasitic_power``).
        """
        if surface is None:
            return 0.0, 0.0
        history = getattr(surface, "history", None)
        net_power_history: list[float] = getattr(history, "net_power_W", [])
        net_thermal_history: list[float] = getattr(history, "net_thermal_W", [])
        surface_power_w = sum(net_power_history) / len(net_power_history) if net_power_history else 0.0
        thermal_w = sum(net_thermal_history) / len(net_thermal_history) if net_thermal_history else 0.0

        power_plant: dict[str, Any] = getattr(surface, "power_plant", {})
        node_cfgs: dict[str, dict[str, Any]] = power_plant.get("nodes", {})
        cooling_condensing_parasitic = self._cooling_condenser_parasitic_power(
            surface,
            node_cfgs,
            node_detail,
        )
        production_pump_parasitic = self._production_pump_parasitic_power(wells)

        power_w = surface_power_w - cooling_condensing_parasitic - production_pump_parasitic
        return power_w, thermal_w

    def _compute_lcoe(self, capex_total: float, net_power_w: float, net_thermal_w: float) -> float:
        r"""``CAPEX*(CRF+F_OM) / (main_product*W_TO_KW*CF*YEAR_TO_HOUR)``.

        ``t`` (project lifetime, years) is ``num_tsteps * dt_years``, set on
        this component by ``Workflow.__init__`` (``_total_project_years``)
        since it has no ``sim_config`` access of its own.

        Guards ``CAPEX <= 0`` and also ``main_power_w <= 0`` → NaN, since a
        negative net power (a real, observed case, ~53/500 designs in the
        Triemli AGS sweep per ``docs/TANGO_vision_and_roadmap/README.md``'s
        "Pump electricity accounting" section) would otherwise silently
        produce a deeply negative "cost" rather than an explicit
        not-a-number, and a negative LCOE doesn't mean anything physically.
        """
        if capex_total <= 0:
            return float("nan")

        main_power_w, bi_power_w, bi_price = self._main_and_byproduct_power(net_power_w, net_thermal_w)
        if main_power_w <= 0:
            return float("nan")

        d = self.discount_rate
        t = self._total_project_years
        crf = d * (1.0 + d) ** t / ((1.0 + d) ** t - 1.0)
        f_om = self.opex_cost_fraction - (bi_power_w * W_TO_KW * YEAR_TO_HOUR * bi_price) / capex_total
        return capex_total * (crf + f_om) / (main_power_w * W_TO_KW * self.capacity_factor * YEAR_TO_HOUR)

    def _main_and_byproduct_power(
        self,
        net_power_w: float,
        net_thermal_w: float,
    ) -> tuple[float, float, float]:
        """``(main_power_w, byproduct_power_w, byproduct_price)`` for ``self.main_product``.

        Shared by ``_compute_lcoe`` and ``_compute_specific_investment_cost``
        so both metrics are computed against the SAME product's power — not
        two independently-guessed choices that could silently drift apart.
        """
        if self.main_product == MainProduct.ELECTRICITY:
            return net_power_w, net_thermal_w, self.heat_price
        return net_thermal_w, net_power_w, self.electricity_price

    def _compute_specific_investment_cost(
        self,
        capex_total: float,
        net_power_w: float,
        net_thermal_w: float,
    ) -> float:
        """``CAPEX_total / (main_product_power * W_TO_KW)`` -- total investment cost per unit power ($/kW).

        Unlike ``_compute_lcoe``, this has no discount rate/OPEX/capacity-factor
        term at all -- it's a simple CAPEX-per-capacity ratio, the metric a
        financing decision typically starts from before levelized-cost
        modeling. Uses the SAME main-product power selection as
        ``_compute_lcoe`` (via ``_main_and_byproduct_power``) so the two
        metrics are directly comparable, not on different bases.

        Same caveat as ``_compute_lcoe``'s own denominator: ``net_power_w``/
        ``net_thermal_w`` are RUN-AVERAGED power (``_read_net_power``), not
        nameplate/rated capacity -- specific investment cost is
        conventionally CAPEX per unit of RATED capacity, so this is a
        deliberate, pragmatic deviation to stay on the same power basis
        LCOE already uses, not an oversight (see this module's own
        docstring for the broader run-averaged-vs-nameplate discussion).
        """
        if capex_total <= 0:
            return float("nan")
        main_power_w, _bi_power_w, _bi_price = self._main_and_byproduct_power(net_power_w, net_thermal_w)
        if main_power_w <= 0:
            return float("nan")
        return capex_total / (main_power_w * W_TO_KW)

    def _compute_opex(self, capex_total: float, net_power_w: float, net_thermal_w: float) -> float:
        """Net annual O&M cost ($/yr) -- ``f_om * CAPEX_total``, exposed as its own dollar value.

        ``f_om`` (``opex_cost_fraction`` minus the by-product revenue
        credit) is exactly ``_compute_lcoe``'s own intermediate term --
        this is literally the SAME annual operating cost figure LCOE's
        formula already charges internally, just reported directly rather
        than folded into one levelized ratio. Can come out NEGATIVE for a
        strong by-product revenue stream (the credit exceeds the base O&M
        fraction) -- that's the same behavior ``f_om`` already has inside
        ``_compute_lcoe``, not a new edge case introduced here.
        """
        if capex_total <= 0:
            return float("nan")
        _main_power_w, bi_power_w, bi_price = self._main_and_byproduct_power(net_power_w, net_thermal_w)
        f_om = self.opex_cost_fraction - (bi_power_w * W_TO_KW * YEAR_TO_HOUR * bi_price) / capex_total
        return f_om * capex_total

    @property
    def _total_project_years(self) -> float:
        """Total simulated project lifetime (years) — set by ``compute()``'s caller.

        Populated by ``Workflow.__init__``/``SystemDirect`` at construction
        time (``num_tsteps * dt_years``) since this component itself has no
        ``sim_config`` access — see ``_total_project_years`` assignment in
        ``workflows/workflow.py``.
        """
        return getattr(self, "_total_years", float("nan"))
