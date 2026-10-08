"""Multi-objective optimization of the hydrothermal binary-cycle (ORC) electric example.

Searches mass flow rate, injection pressure, target extraction pressure,
injection and production well diameters, surface pipe diameter, and ORC feed-
pump (evaporating) pressure with NSGA2 to minimize LCOE and maximize mean net
electric power. Production temperature, specific investment cost, and OPEX are
reporting-only read-outs.

Not tuned: the ORC condensing pressure
(``orc_turbine``/``orc_desuperheater``/``orc_condenser``), which follows from
the site's cooling limit (surface temperature plus ``approach_temperature``),
so it is a site condition rather than a design choice.

The injection policy is forced to ``manual-fracking-check``: the ``auto-*``
policies solve for mass flow rate or injection pressure on every pass, which
would fight the optimizer over the same variables, and the fracking check
rejects designs that would fracture the reservoir.

The ``ParamSpec``/``ObjectiveSpec`` factories are defined here, not in
``pymoo_api.py``, which stays generic (see ``ParamSpec``'s docstring); the CLI,
baseline, search, and plots come from ``tango.pymoo_api.OptApp``.

Usage: ``dvc repro`` from this directory (or ``just slurm
opt_hydro_ORC_electric`` on Euler) runs the ``optimize`` and ``plot`` stages in
``dvc.yaml``. Running this script directly with ``uv run python
opt_hydro_ORC_electric.py`` also works but bypasses DVC's tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from CoolProp.CoolProp import PropsSI

from tango.core.policies import InjectionPolicy
from tango.pymoo_api import ObjectiveScatter, ObjectiveSpec, OptApp, ParamSpec
from tango.workflows.workflow import Workflow

HERE = Path(__file__).parent


# ---------------------------------------------------------------------------
# Decision variables
# ---------------------------------------------------------------------------


@dataclass
class _PathsApply:
    """Picklable ``ParamSpec.apply`` that sets one value at several config paths.

    A module-level dataclass rather than a closure, so it pickles for
    ``n_processes > 1``. ``read`` returns the value at the first path.
    """

    paths: tuple[tuple[str, ...], ...]

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        for path in self.paths:
            target = cfg
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = float(value)
        return cfg

    def read(self, cfg: dict[str, Any]) -> float:
        value: Any = cfg
        for key in self.paths[0]:
            value = value[key]
        return float(value)


def _param(name: str, bounds: tuple[float, float], *paths: str) -> ParamSpec:
    """``ParamSpec`` setting ``name`` at each dotted config path in ``paths``."""
    return ParamSpec(name=name, apply=_PathsApply(tuple(tuple(p.split(".")) for p in paths)), bounds=bounds)


@dataclass
class _WellDiameterApply:
    """Picklable ``ParamSpec.apply`` for a wellbore diameter that also moves the reservoir's effective diameter.

    ``reservoir.well_eff_diameter`` is the average of the injection and
    production well diameters. Each diameter param recomputes it from
    whatever the config holds for the other, so the result is the same in
    either application order.
    """

    wells: tuple[str, ...]

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        components = cfg["components"]
        for well in self.wells:
            components[well]["diameter"] = float(value)
        components["reservoir"]["well_eff_diameter"] = 0.5 * (
            components["injection_well"]["diameter"] + components["production_well_lower"]["diameter"]
        )
        return cfg

    def read(self, cfg: dict[str, Any]) -> float:
        return float(cfg["components"][self.wells[0]]["diameter"])


@dataclass
class _OrcFeedPumpPressureApply:
    """Picklable ``ParamSpec.apply`` for the ORC feed-pump outlet pressure (MPa).

    ``orc_feed_pump``'s outlet pressure is the ORC's high pressure: the
    preheater and evaporator both have ``pressure_ratio2: 1.0``, so it is also
    the evaporating pressure and the turbine inlet pressure. The evaporator's
    ``vapor_mass_fraction_out2: 1`` then fixes the evaporating temperature at
    R245fa's saturation temperature at this pressure.

    Also moves the TESPy starting guesses that depend on this pressure, since
    a guess left at the base design's value makes the solve fail at many
    pressures inside the bounds:

    - the preheater's and evaporator's ``p0_out2``, to this pressure;
    - the evaporator's ``h0_out1`` (geofluid outlet enthalpy), to its exact
      solved value: R245fa enters the evaporator as saturated liquid
      (``preheater.vapor_mass_fraction_out2: 0``), so ``ttd_l`` puts the
      geofluid outlet at the saturation temperature plus ``ttd_l``. Taken as
      saturated-liquid geofluid at that temperature, which is within a
      fraction of a percent of the compressed-liquid value.
    """

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        nodes = cfg["components"]["surface"]["power_plant"]["nodes"]
        nodes["orc_feed_pump"]["p_out_megapascals"] = float(value)
        nodes["preheater"]["p0_out2"] = float(value)
        nodes["evaporator"]["p0_out2"] = float(value)

        orc_fluid = nodes["preheater"]["fluid_out2"]
        geofluid = cfg["common"]["fluid_name"]
        t_saturation_k = PropsSI("T", "P", float(value) * 1.0e6, "Q", 0, orc_fluid)
        t_geofluid_out_k = t_saturation_k + float(nodes["evaporator"]["ttd_l"])
        nodes["evaporator"]["h0_out1"] = (
            PropsSI("H", "T", t_geofluid_out_k, "Q", 0, geofluid) / 1.0e3
        )  # J/kg -> kJ/kg
        return cfg

    def read(self, cfg: dict[str, Any]) -> float:
        return float(
            cfg["components"]["surface"]["power_plant"]["nodes"]["orc_feed_pump"]["p_out_megapascals"],
        )


DEFAULT_BOUNDS: dict[str, tuple[float, float]] = {
    "mass_rate_kg_per_s": (10.0, 100.0),
    "injection_pressure_Pa": (1000000.0, 8000000.0),
    # (0.7, 1.5)x the config's own value, the same scale factor
    # run_hydro_df_electric_sweep uses.
    "target_extraction_pressure_Pa": (2100000.0, 4500000.0),
    # 6-24 inch wellbores.
    "injection_well_diameter_m": (0.15, 0.6),
    "production_well_diameter_m": (0.15, 0.6),
    "surface_pipe_diameter_m": (0.2, 0.75),
    # Lower bound stays well above the ORC condensing pressure, so the feed
    # pump always raises pressure. Upper bound saturates R245fa at ~142 degC,
    # 0.65 MPa below its 3.65 MPa critical pressure; designs whose produced
    # fluid is too cool for the chosen pressure fail to solve and are rejected
    # as infeasible.
    "orc_feed_pump_pressure_MPa": (0.35, 3.0),
}


def param_specs(bounds: dict[str, tuple[float, float]]) -> list[ParamSpec]:
    """Decision variables.

    - ``target_extraction_pressure_Pa`` is ``sim_config``'s single shared
      value, threaded to the surface and the pump-bearing production well.
    - ``production_well_diameter_m`` sets both production well sections
      together: ``DoubletEconomicComponent`` costs them as one well and
      requires one diameter. Both diameters also move
      ``reservoir.well_eff_diameter``, their average.
    - ``surface_pipe_diameter_m`` sets both the surface pipe's friction
      pressure drop and its cost.
    """
    return [
        _param("mass_rate_kg_per_s", bounds["mass_rate_kg_per_s"], "sim_config.mass_rate"),
        _param(
            "injection_pressure_Pa",
            bounds["injection_pressure_Pa"],
            "components.surface.injection_pressure",
        ),
        _param(
            "target_extraction_pressure_Pa",
            bounds["target_extraction_pressure_Pa"],
            "sim_config.target_extraction_pressure",
        ),
        ParamSpec(
            name="injection_well_diameter_m",
            apply=_WellDiameterApply(("injection_well",)),
            bounds=bounds["injection_well_diameter_m"],
        ),
        ParamSpec(
            name="production_well_diameter_m",
            apply=_WellDiameterApply(("production_well_lower", "production_well_upper")),
            bounds=bounds["production_well_diameter_m"],
        ),
        _param(
            "surface_pipe_diameter_m",
            bounds["surface_pipe_diameter_m"],
            "components.surface.pipe_diameter",
        ),
        ParamSpec(
            name="orc_feed_pump_pressure_MPa",
            apply=_OrcFeedPumpPressureApply(),
            bounds=bounds["orc_feed_pump_pressure_MPa"],
        ),
    ]


# ---------------------------------------------------------------------------
# Objectives and reports
# ---------------------------------------------------------------------------


@dataclass
class _EconomicStateEvaluate:
    """Picklable ``ObjectiveSpec.evaluate`` reading one ``economic.state`` value."""

    key: str

    def __call__(self, wf: Workflow) -> float:
        return float(wf.to_dict()["economic"]["state"][self.key])


@dataclass
class _NegativeMeanPowerEvaluate:
    """Picklable ``ObjectiveSpec.evaluate``: ``-`` mean of the surface's ``history.net_power_W``."""

    def __call__(self, wf: Workflow) -> float:
        values: list[float] = wf._orchestrator.components["surface"].history.net_power_W  # noqa: SLF001
        return -sum(values) / len(values)


@dataclass
class _NegativeProductionTemperatureEvaluate:
    """Picklable ``ObjectiveSpec.evaluate``: ``-`` final production-well outlet temperature (degC).

    The final timestep, not a run average: it's the longest-run outlet
    temperature the plant has to keep working with.
    """

    def __call__(self, wf: Workflow) -> float:
        t_outlet_k: list[float] = wf._orchestrator.components["production_well_upper"].history.T_outlet  # noqa: SLF001
        return -(t_outlet_k[-1] - 273.15)


# Mean rather than total energy: every timestep has the same duration, so the
# two carry the same optimization signal, and a mean in W is easier to read.
OBJECTIVES = [
    ObjectiveSpec(name="LCOE", evaluate=_EconomicStateEvaluate("LCOE")),
    ObjectiveSpec(name="negative_mean_power_W", evaluate=_NegativeMeanPowerEvaluate()),
]
REPORTS = [
    ObjectiveSpec(
        name="negative_production_temperature_C",
        evaluate=_NegativeProductionTemperatureEvaluate(),
    ),
    ObjectiveSpec(
        name="specific_investment_cost",
        evaluate=_EconomicStateEvaluate("specific_investment_cost"),
    ),
    ObjectiveSpec(name="OPEX", evaluate=_EconomicStateEvaluate("OPEX")),
]

APP = OptApp(
    title="hydro_ORC_electric",
    description="Multi-objective optimization of the hydrothermal binary-cycle (ORC) electric example.",
    config_path=HERE.parents[1] / "example_configs" / "hydro_ORC_electric.yml",
    app_dir=HERE,
    injection_mode=InjectionPolicy.MANUAL_FRACKING_CHECK,
    default_bounds=DEFAULT_BOUNDS,
    param_factory=param_specs,
    objective_specs=OBJECTIVES,
    report_specs=REPORTS,
    display_rename={
        "negative_mean_power_W": "mean_power_W",
        "negative_production_temperature_C": "production_temperature_C",
    },
    column_labels={
        "mass_rate_kg_per_s": "par:mass_rate [kg/s]",
        "injection_pressure_Pa": "par:injection_pressure [Pa]",
        "target_extraction_pressure_Pa": "par:target_extraction_pressure [Pa]",
        "injection_well_diameter_m": "par:injection_well_diameter [m]",
        "production_well_diameter_m": "par:production_well_diameter [m]",
        "surface_pipe_diameter_m": "par:surface_pipe_diameter [m]",
        "orc_feed_pump_pressure_MPa": "par:orc_feed_pump_pressure [MPa]",
        "LCOE": "obj:LCOE [$/kWh]",
        "mean_power_W": "obj:mean_power [W]",
        "production_temperature_C": "rep:production_temperature [°C]",
        "specific_investment_cost": "rep:specific_investment_cost [$/kW]",
        "OPEX": "rep:OPEX [$/yr]",
        "euclidean": "euclidean [z-score]",
    },
    scatter=ObjectiveScatter(
        x_col="LCOE",
        x_label="LCOE ($/kWh)",
        y_col="mean_power_W",
        y_label="Mean net electric power (MW)",
        y_scale=1.0e-6,
        color_col="production_temperature_C",
    ),
)

if __name__ == "__main__":
    APP.main()
