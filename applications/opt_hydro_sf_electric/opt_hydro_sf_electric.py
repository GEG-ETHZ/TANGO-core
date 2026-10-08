"""Multi-objective optimization of the single-flash hydrothermal electric example.

Searches mass flow rate, injection pressure, target extraction pressure, the
injection and production well diameters, the surface pipe diameter, and the
flash valve's outlet (separator) pressure with NSGA2 to minimize LCOE and
maximize mean net electric power. Production temperature, specific investment
cost, and OPEX are reporting-only read-outs.

Not tuned: the turbine/condenser pressure, which follows from the site's
cooling limit (surface temperature plus ``approach_temperature``), so it is a
site condition rather than a design choice.

The injection policy is forced to ``manual-fracking-check``: the ``auto-*``
policies solve for mass flow rate or injection pressure on every pass, which
would fight the optimizer over the same variables, and the fracking check
rejects designs that would fracture the reservoir.

The ``ParamSpec``/``ObjectiveSpec`` factories are defined here, not in
``pymoo_api.py``, which stays generic (see ``ParamSpec``'s docstring); the
CLI, baseline, search, and plots come from ``tango.pymoo_api.OptApp``.

Usage: ``dvc repro`` from this directory (or ``just slurm opt_hydro_sf_electric``
on Euler) runs the ``optimize`` and ``plot`` stages in ``dvc.yaml``. Running
this script directly with ``uv run python opt_hydro_sf_electric.py`` also
works but bypasses DVC's tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


DEFAULT_BOUNDS: dict[str, tuple[float, float]] = {
    "mass_rate_kg_per_s": (10.0, 100.0),
    "injection_pressure_Pa": (1.0e6, 8.0e6),
    # (0.7, 1.5)x the base YAML's 7.0 MPa, the same scale factor
    # run_hydro_df_electric_sweep uses for this field on the same wells.
    "target_extraction_pressure_Pa": (4.9e6, 10.5e6),
    # 6-24 inch wellbores, bracketing the base YAML's 0.41 m.
    "injection_well_diameter_m": (0.15, 0.6),
    "production_well_diameter_m": (0.15, 0.6),
    "surface_pipe_diameter_m": (0.2, 0.75),
    # Above the 0.005 MPa condenser, and up to where ~177 degC brine barely
    # flashes; a valve set above the arriving fluid's saturation pressure
    # makes no steam and fails as infeasible.
    "flash_pressure_MPa": (0.01, 0.6),
}


def param_specs(bounds: dict[str, tuple[float, float]]) -> list[ParamSpec]:
    """Decision variables.

    - ``target_extraction_pressure_Pa`` is ``sim_config``'s single shared
      value, threaded to the surface and the pump-bearing production well.
    - ``production_well_diameter_m`` sets both production well sections
      together: ``DoubletEconomicComponent`` costs them as one well and
      requires one diameter.
    - ``flash_pressure_MPa`` is the flash valve's outlet, which sets the
      separator and turbine-inlet pressure.
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
        _param(
            "flash_pressure_MPa",
            bounds["flash_pressure_MPa"],
            "components.surface.power_plant.nodes.flash_valve.p_out_megapascals",
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
        net_power_w: list[float] = wf._orchestrator.components["surface"].history.net_power_W  # noqa: SLF001
        return -sum(net_power_w) / len(net_power_w)


@dataclass
class _NegativeProductionTemperatureEvaluate:
    """Picklable ``ObjectiveSpec.evaluate``: ``-`` final production-well outlet temperature (degC).

    The final timestep, not a run average: it's the longest-run outlet
    temperature the plant has to keep working with.
    """

    well: str

    def __call__(self, wf: Workflow) -> float:
        t_outlet_k: list[float] = wf._orchestrator.components[self.well].history.T_outlet  # noqa: SLF001
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
        evaluate=_NegativeProductionTemperatureEvaluate("production_well_upper"),
    ),
    ObjectiveSpec(
        name="specific_investment_cost",
        evaluate=_EconomicStateEvaluate("specific_investment_cost"),
    ),
    ObjectiveSpec(name="OPEX", evaluate=_EconomicStateEvaluate("OPEX")),
]

APP = OptApp(
    title="hydro_sf_electric",
    description="Multi-objective optimization of the single-flash hydrothermal electric example.",
    config_path=HERE.parents[1] / "example_configs" / "hydro_sf_electric.yml",
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
        "flash_pressure_MPa": "par:flash_pressure [MPa]",
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
