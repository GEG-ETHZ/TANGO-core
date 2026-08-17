r"""Doublet CAPEX/LCOE economic component for tango_next.

Ported from ``src/tango/units/native/economic/{economic,wells,surface,
permitting,exploration}.py`` (~2877 lines), scoped to what a hydrothermal
DOUBLET + double-flash (or single-flash) plant actually needs — see
``docs/tango_next_tasks.md``/the ``DoubletEconomicComponent`` plan for the
full old-tango reading that produced this scope. Not a general-purpose
economic engine: only the ``gengeo`` well-cost model, H2O (no CO2 add-ons),
and the ``flexible_pp``-style generic TESPy-node surface-plant cost engine
are ported. AGS/5-spot/CPG/ORC-specific cost paths are NOT — this only
covers what ``examples/tango_next/hydro_df_electric.yml``'s topology needs.

Runs exactly once, after all physical timesteps — see
``EconomicComponent``'s (``base.py``) and ``SystemDirect.finalize()``'s
docstrings for why. Surface-plant CAPEX sizing and the LCOE denominator use
the RUN-AVERAGED power/heat-duty of each turbine/pump/condenser — the
simple arithmetic mean over every recorded timestep, NOT any single
timestep's value. This was initially implemented as final-timestep-only
(a wrong assumption — "``economic.execute()`` runs once, after the
timestep loop" was misread as "uses the live network's current value,"
without checking what it does internally), then corrected 2026-08-10
after re-tracing old tango's actual call chain for its ``flexible_pp``
surface-plant cost engine (which is what every topology this component is
scoped to uses): ``EconUnitSurfacePowerPlant._execute_flexible_pp`` →
``PowerPlantCost.compute_total_cost_with_averaged_results`` →
``create_power_plant_with_averaged_results`` — the last of which
literally overwrites each node's ``P.val``/``Q.val`` with
``average_fp_result[f"{{label}}_power_real"]`` (or ``_heat_transfer_real``),
itself the simple mean of that quantity's FULL per-timestep history
(``EconomicUnitNative.calculate_and_set_average``), before any cost
formula ever runs. Verified to 7 significant figures: the mean of old
tango's own 20-timestep turbine-power history for
``flexible_SF_manual.yml`` is 1,782,871.45 W — exactly the number this
component's earlier (wrong) final-timestep-only implementation had
mistaken for old tango's *final*-timestep value. See ``docs/bugs-fixed-in-tango-next.md``
for the full writeup.

Sign-convention note (see ``project_economic_model_wackiness`` memory for
the full investigation): old tango's cost formulas hardcode sign-specific
literals (e.g. ``-1.34 * W_pump``) that assume a particular raw TESPy
``P.val`` sign — which turned out to be a wiring-convention artifact, not a
physical constant: verified empirically that tango_next's own
``GraphSurface`` wiring gives pumps POSITIVE ``P.val`` (consumes energy)
and turbines NEGATIVE (generates energy) — the OPPOSITE convention from
whatever old tango's own ``SurfaceUnitFlexiblePP`` network happens to
produce for pumps. A literal port would either silently zero out (via old
tango's defensive clamps) or NaN (via ``numpy.float64(negative)**fractional``)
every pump/turbine cost. This component uses ``abs()`` on every raw node
power before applying a fractional-exponent formula instead — mathematically
identical to old tango's result for old tango's own (already
consistently-signed) values, and correct regardless of which TESPy
in/out port order a given surface implementation happens to use.

Not ported (documented, deliberate gaps — see the module docstring
sections above for why each is safe to omit for this topology):
- Well-cost models other than ``gengeo`` (halliburton/st_gallen/bavaria/
  swiss/ppgd) — ``gengeo`` is old tango's own default.
- CO2-specific add-ons everywhere (wells/permitting/exploration) — this
  component is H2O-only.
- The 2-stream ``HeatExchanger`` (preheater/boiler/recuperator) cost path —
  not present in the target double-flash/single-flash topologies.
- **Any direct-heat district-heating exchanger's own equipment cost.**
  Confirmed by running ``AGS_direct_heat.yml``/``EGS_direct_heat.yml``
  through this component (no crash, but ``CAPEX_surface_plant`` comes back
  exactly ``0.0``): a plain district-heating ``SimpleHeatExchanger`` node
  has no ``Subtype: cooler``/``condenser`` tag, so it isn't picked up by
  ``_cooler_condenser_cost`` (the only ``SimpleHeatExchanger`` cost path
  ported) — old tango's `flexible_pp` cost engine has no direct-heat
  exchanger cost formula either (it's a turbine/pump/cooler-condenser
  model), so there's nothing to port for this case yet. ``CAPEX_total``/
  LCOH for a direct-heat config is therefore real but understates true
  cost until a direct-heat-exchanger formula exists somewhere to port.
- The production-well-pump "lineshaft" cost add-on — old tango only fires
  it when the average production-pump power is negative; tango_next's own
  ``LumpedProductionWellWithPump.pump_power_watts`` formula is
  non-negative by construction (``well/lumped.py``), so the condition can
  never trigger here.
- PPI-table/cost-multiplier-table Excel lookup and cost-year interpolation
  — tango_next has no calendar concept (``SimConfig`` has no ``start_date``),
  so a fixed 2019-row snapshot is hardcoded instead (``core/economic_constants.py``).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import Field

from tango_next.components.economic.base import EconomicComponent
from tango_next.components.surface.base import SurfaceComponent
from tango_next.components.well.base import WellComponent
from tango_next.core.constants import W_TO_KW, YEAR_TO_HOUR
from tango_next.core.economic_constants import (
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
from tango_next.core.locked_state import LockedState
from tango_next.core.policies import MainProduct, ProjectMaturity

if TYPE_CHECKING:
    from tango_next.core.component import Component

# Old tango default (src/tango/units/dataclasses.py's WellSpecs.probability_of_success);
# not exposed as a tango_next config field since nothing varies it yet.
_DEFAULT_PROBABILITY_OF_SUCCESS: float = 0.95

# Old tango default (src/tango/units/dataclasses.py's temperature_range field, unset by
# every example this component is scoped to) — see the BAC regression note below.
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
    # ("CO2", "OPEN") unsupported — old tango raises for this combination too.
}


def _bac_regression(
    coeffs: tuple[float, float, float, float],
    dt_approach: float,
    t_ambient: float,
    dt_range: float,
) -> float:
    """Baltimore Aircoil regression model shape (surface.py's ``_BAC_regression_model``).

    Shared by the cooler/condenser COST formula (``_BAC_COEFFS_WET``/``_DRY``)
    and the cooler/condenser PARASITIC POWER formula
    (``_BAC_POWER_COEFFS_WET``/``_DRY``) — same shape, different fitted
    coefficients depending on which quantity is being estimated.
    """
    a, b, c, d = coeffs
    return a / dt_approach + b * t_ambient + c * t_ambient / dt_approach + d / (dt_approach + dt_range)


def _ls(value: float = 0.0) -> LockedState[float]:
    ls: LockedState[float] = LockedState(value)
    ls.mark_stale()
    return ls


@dataclass(frozen=True)
class EconomicState:
    """Final CAPEX/LCOE result of one ``DoubletEconomicComponent.solve()`` call.

    Computed exactly once (see module docstring) — unlike every other
    component's ``state``, this is never recomputed per-timestep, but still
    uses ``LockedState`` for consistency with the rest of tango_next's
    write-once-per-solve convention.
    """

    CAPEX_well: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    CAPEX_permitting: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    CAPEX_exploration: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    CAPEX_surface_pipes: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    CAPEX_surface_plant: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    CAPEX_total: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    net_power_W: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    net_thermal_W: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    LCOE: LockedState[float] = field(default_factory=lambda: _ls(float("nan")))

    def mark_all_stale(self) -> None:
        """Mark every ``LockedState`` field stale."""
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if isinstance(value, LockedState):
                value.mark_stale()


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

    state: EconomicState = Field(default_factory=EconomicState)

    def solve(self) -> None:
        """Compute CAPEX + LCOE from ``self._components`` (set by the orchestrator).

        Raises:
            RuntimeError: If called without ``self._components`` having been
                set first (i.e. called directly rather than via
                ``SystemDirect.finalize()``).

        """
        components: dict[str, Component] | None = getattr(self, "_components", None)
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

    # ------------------------------------------------------------------
    # Wells (src/tango/units/native/economic/wells.py, gengeo model only)
    # ------------------------------------------------------------------

    def _well_section_cost(self, length_m: float, diameter_m: float) -> float:
        """One well "section"'s cost via the gengeo formula (wells.py:262-264).

        ``C = X_IC * X_PC * PPI_O&G * (0.105*L^2 + 1776*d*L + 275300)``
        (H2O — the CO2-specific ``dC_CO2_well`` add-on is 0 for this fluid).
        """
        return (
            X_IC_WELLS
            * X_PC_WELLS
            * PPI_O_AND_G
            * (0.105 * length_m**2 + 1776.0 * diameter_m * length_m + 275_300.0)
        )

    def _compute_well_capex(self, wells: list[WellComponent]) -> float:
        """Injection + production well CAPEX, DOUBLET pattern (1 of each).

        The injection well is identified as the ``WellComponent`` at
        ``component_idx == 0`` (the circuit entry — see ``Component``'s
        class docstring); every other ``WellComponent`` is part of the
        SAME production well, split across multiple physics sub-components
        (e.g. a lower section + an upper section with a pump) — combined
        into one total depth before costing, matching old tango's actual
        design (confirmed with Chad, and via ``examples/flexible_DF_manual.yml``'s
        ``production_well.well_length_seq: [5000.]`` — the combined 4000 m
        + 1000 m total, NOT a separate per-sub-component cost — see
        ``docs/bugs-fixed-in-tango-next.md`` for the investigation that got this wrong
        the first time). Costing each sub-component as an independent well
        would double- (or triple-) count the gengeo formula's fixed
        mobilization term (``+275300``) once per sub-component, which
        isn't physically meaningful for what is structurally one wellbore.
        """
        injection = [w for w in wells if w.component_idx == 0]
        production = [w for w in wells if w.component_idx != 0]

        cost_inj = 0.0
        if self.project_maturity != ProjectMaturity.BROWN_FIELD:
            cost_inj = sum(self._well_section_cost(w.well_length, w.diameter) for w in injection)
            cost_inj /= _DEFAULT_PROBABILITY_OF_SUCCESS

        prod_length, prod_diameter = self._combined_production_length_and_diameter(production)
        cost_prod = self._well_section_cost(prod_length, prod_diameter)
        cost_prod /= _DEFAULT_PROBABILITY_OF_SUCCESS

        return cost_inj + cost_prod

    def _combined_production_length_and_diameter(
        self,
        production: list[WellComponent],
    ) -> tuple[float, float]:
        """Combine every production-side ``WellComponent`` into one well's total depth.

        Diameter: takes the (assumed uniform) diameter shared by every
        production-side component — true in every example checked so far.
        Raises rather than silently picking one if that's ever not true:
        real multi-segment costing (varying outer/casing diameter by
        depth) is a planned tango_next feature, not built yet (see
        ``docs/tango_next_tasks.md``'s open items) — silently ignoring a
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
                "(see docs/tango_next_tasks.md's open items).",
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

        Matches old tango's ``create_power_plant_with_averaged_results``
        (see module docstring) — CAPEX sizing for a ``flexible_pp``-style
        surface plant uses the simple arithmetic mean of each component's
        power/heat-duty history, not any single timestep's value.
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
        ``hydro_df_electric.yml``'s condenser1/condenser2) works
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

        Matches old tango's ``prod_pump_w_list`` average, added
        (subtracted here, given tango_next's non-negative sign convention
        — see ``project_economic_model_wackiness`` memory) into
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

        Net electric power is old tango's ``compute_net_power()`` exactly:
        ``turbine + surface_pump - (cooling_parasitic + condensing_parasitic)
        + production_downhole_pump``. The first term is already correctly
        netted in ``GraphSurface.history.net_power_W`` (a per-timestep sum
        of signed node contributions — turbines positive, surface pumps
        negative — see that class's docstring); mean-of-sum equals
        sum-of-means since the mean is linear, so averaging that series is
        exactly equivalent to old tango's separately-averaged-then-summed
        turbine/pump terms, not merely an approximation. The remaining two
        terms (cooling-tower/condenser parasitic power, production
        downhole pump) are NOT part of that surface-node sum at all — old
        tango adds them at the economic layer specifically, and this
        component does the same (see ``_cooling_condenser_parasitic_power``/
        ``_production_pump_parasitic_power``). Net thermal power is
        unaffected — old tango only ever adds ``dh_component`` nodes to it
        (none exist in the double-flash/single-flash topologies this
        component is scoped to).
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

        Deliberate deviation from old tango: old tango's ``_get_LCOE`` only
        guards ``CAPEX <= 0``, not the power denominator — a negative net
        power (a real, observed case, ~53/500 designs in the Triemli AGS
        sweep per ``docs/TANGO_vision_and_roadmap.md``'s "Pump electricity
        accounting" section) silently produces a deeply negative "cost"
        rather than an explicit not-a-number. This component also guards
        ``main_power_w <= 0`` → NaN, since a negative LCOE doesn't mean
        anything physically. Both the target parity case
        (``hydro_df_electric.yml``) and old tango's own ``flexible_DF_manual.yml``
        reference case have strictly positive net power, so this guard
        never changes the parity-tested value — it only changes behavior
        for a scenario neither reference case exercises.
        """
        if capex_total <= 0:
            return float("nan")

        if self.main_product == MainProduct.ELECTRICITY:
            main_power_w, bi_power_w, bi_price = net_power_w, net_thermal_w, self.heat_price
        else:
            main_power_w, bi_power_w, bi_price = net_thermal_w, net_power_w, self.electricity_price

        if main_power_w <= 0:
            return float("nan")

        d = self.discount_rate
        t = self._total_project_years
        crf = d * (1.0 + d) ** t / ((1.0 + d) ** t - 1.0)
        f_om = self.opex_cost_fraction - (bi_power_w * W_TO_KW * YEAR_TO_HOUR * bi_price) / capex_total
        return capex_total * (crf + f_om) / (main_power_w * W_TO_KW * self.capacity_factor * YEAR_TO_HOUR)

    @property
    def _total_project_years(self) -> float:
        """Total simulated project lifetime (years) — set by ``compute()``'s caller.

        Populated by ``Workflow.__init__``/``SystemDirect`` at construction
        time (``num_tsteps * dt_years``) since this component itself has no
        ``sim_config`` access — see ``_total_project_years`` assignment in
        ``workflows/workflow.py``.
        """
        return getattr(self, "_total_years", float("nan"))
