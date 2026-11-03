# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Multi-objective optimization of the double-flash hydrothermal electric example.

Searches mass flow rate, injection pressure, target extraction pressure, the
injection and production well diameters, the surface pipe diameter, and both
flash pressures with NSGA2 to minimize LCOE and maximize mean net electric
power. Production temperature, specific investment
cost, and OPEX are reporting-only read-outs.

Not tuned: the turbines'/condensers' pressure, which follows from the site's
cooling limit (surface temperature plus ``approach_temperature``), so it is a
site condition rather than a design choice.

The injection policy is forced to ``manual-fracking-check``: the ``auto-*``
policies solve for mass flow rate or injection pressure on every pass, which
would fight the optimizer over the same variables, and the fracking check
rejects designs that would fracture the reservoir.

The ``ParamSpec``/``ObjectiveSpec`` factories are defined here, not in
``pymoo_api.py``, which stays generic (see ``ParamSpec``'s docstring); the
CLI, baseline, search, and plots come from ``tango_core.pymoo_api.OptApp``.

Usage: ``dvc repro`` from this directory (or ``just slurm opt_hydro_df_electric``
on Euler) runs the ``optimize`` and ``plot`` stages in ``dvc.yaml``. Running
this script directly with ``uv run python opt_hydro_df_electric.py`` also
works but bypasses DVC's tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tango_core.core.policies import InjectionPolicy
from tango_core.pymoo_api import ObjectiveScatter, ObjectiveSpec, OptApp, ParamSpec
from tango_core.workflows.workflow import Workflow

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
            if path[-1] not in target:
                raise KeyError(f"config has no {'.'.join(path)} to set (typo in this param's path?)")
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
    """Picklable ``ParamSpec.apply`` for a wellbore diameter, set on every well segment in ``wells``.

    ``reservoir.well_eff_diameter``, the average of the injection and
    production well diameters, is derived from these
    (``tango_core.workflows.linked_quantities``).
    """

    wells: tuple[str, ...]

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        components = cfg["components"]
        for well in self.wells:
            components[well]["diameter"] = float(value)
        return cfg

    def read(self, cfg: dict[str, Any]) -> float:
        return float(cfg["components"][self.wells[0]]["diameter"])


@dataclass
class _HighFlashPressureApply:
    """Picklable ``ParamSpec.apply`` for the high-pressure flash, keeping the low/high ratio.

    The config stores both valves' absolute pressures, but the search sets
    the low-pressure one as a ratio of the high-pressure one
    (``_LowFlashPressureRatioApply``). Moving the high-pressure valve
    therefore moves the low-pressure one with it at the current ratio, so
    the two params give the same config in either application order.
    """

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        nodes = cfg["components"]["surface"]["power_plant"]["nodes"]
        high, low = nodes["high_pressure_flash_valve"], nodes["low_pressure_flash_valve"]
        ratio = float(low["p_out_megapascals"]) / float(high["p_out_megapascals"])
        high["p_out_megapascals"] = float(value)
        low["p_out_megapascals"] = ratio * float(value)
        return cfg

    def read(self, cfg: dict[str, Any]) -> float:
        return float(
            cfg["components"]["surface"]["power_plant"]["nodes"]["high_pressure_flash_valve"][
                "p_out_megapascals"
            ],
        )


@dataclass
class _LowFlashPressureRatioApply:
    """Picklable ``ParamSpec.apply`` for the low-pressure flash as a fraction of the high-pressure flash.

    Setting the low-pressure valve as a ratio of the high-pressure one keeps
    ``high > low`` by construction. ``_HighFlashPressureApply`` keeps this
    ratio when it moves the high-pressure valve, so the order the two params
    are applied in doesn't matter.
    """

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        nodes = cfg["components"]["surface"]["power_plant"]["nodes"]
        nodes["low_pressure_flash_valve"]["p_out_megapascals"] = (
            float(value) * nodes["high_pressure_flash_valve"]["p_out_megapascals"]
        )
        return cfg

    def read(self, cfg: dict[str, Any]) -> float:
        nodes = cfg["components"]["surface"]["power_plant"]["nodes"]
        return float(
            nodes["low_pressure_flash_valve"]["p_out_megapascals"]
            / nodes["high_pressure_flash_valve"]["p_out_megapascals"],
        )


DEFAULT_BOUNDS: dict[str, tuple[float, float]] = {
    # Up to 150 kg/s: with the old 100 kg/s cap the whole front sat on it.
    # The front's high-power end now reaches 150 kg/s, but more flow doesn't
    # pay: LCOE rises again by 175 kg/s, and by 200 kg/s the fluid boils in
    # the production well below the pump (SaturationError).
    "mass_rate_kg_per_s": (10.0, 150.0),
    "injection_pressure_Pa": (1.0e6, 8.0e6),
    # Floor: just above water's saturation pressure (1.25 MPa) at the
    # estimated reservoir temperature, 288 K + 5000 m x 0.035 K/m ~ 190 degC,
    # so the produced fluid can't flash in the production well. Pressure
    # above that buys nothing in a flash plant: the flash valve throws it
    # away, so the production pump's extra work is wasted, and the old
    # (0.7x config value) floor pinned every Pareto front. Until the target
    # can be solved from a saturation margin instead (#108).
    "target_extraction_pressure_Pa": (1.3e6, 10.5e6),
    # 6-24 inch wellbores, bracketing the base YAML's 0.41 m.
    "injection_well_diameter_m": (0.15, 0.6),
    "production_well_diameter_m": (0.15, 0.6),
    # The front sits on the 0.2 m floor: pipe friction is free while the
    # surface plant throttles the fluid anyway (flash valve or
    # circulation_control), so a smaller pipe is only cheaper. The real limit,
    # flow velocity, isn't modeled; 0.2 m stands in for it (#120).
    "surface_pipe_diameter_m": (0.2, 0.75),
    # Up to where ~177 degC brine barely flashes; a valve set above the
    # arriving fluid's saturation pressure makes no steam and fails as
    # infeasible.
    "high_flash_pressure_MPa": (0.03, 0.8),
    # Fraction of the high-pressure flash. At the lowest high-pressure flash,
    # 0.2 still keeps the low-pressure flash (0.006 MPa) above the 0.005 MPa
    # condensers.
    "low_flash_pressure_ratio": (0.2, 0.9),
}


def param_specs(bounds: dict[str, tuple[float, float]]) -> list[ParamSpec]:
    """Decision variables.

    - ``target_extraction_pressure_Pa`` is ``sim_config``'s single shared
      value, threaded to the surface and the pump-bearing production well.
    - ``production_well_diameter_m`` sets both production well sections
      together: ``DoubletEconomicComponent`` costs them as one well and
      requires one diameter.
    - ``high_flash_pressure_MPa`` and ``low_flash_pressure_ratio`` set the two
      flash valves' outlets (separator and turbine-inlet pressures) so that
      high > low > condenser.
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
            name="high_flash_pressure_MPa",
            apply=_HighFlashPressureApply(),
            bounds=bounds["high_flash_pressure_MPa"],
        ),
        ParamSpec(
            name="low_flash_pressure_ratio",
            apply=_LowFlashPressureRatioApply(),
            bounds=bounds["low_flash_pressure_ratio"],
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
    """Picklable ``ObjectiveSpec.evaluate``: ``-`` the run's mean net electric power (W).

    ``economic.state.net_power_W``: the surface plant's net output minus the
    cooling/condensing parasitics and any downhole production pump, the same
    net power LCOE divides by, so the two objectives agree on what a design
    produces.
    """

    def __call__(self, wf: Workflow) -> float:
        return -float(wf.to_dict()["economic"]["state"]["net_power_W"])


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
    title="hydro_df_electric",
    description="Multi-objective optimization of the double-flash hydrothermal electric example.",
    config_path=HERE.parents[1] / "templates" / "hydro_df_electric.yml",
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
        "high_flash_pressure_MPa": "par:high_flash_pressure [MPa]",
        "low_flash_pressure_ratio": "par:low_flash_pressure_ratio [-]",
        "LCOE": "obj:LCOE [$/kWh]",
        "mean_power_W": "obj:mean_power [W]",
        "production_temperature_C": "rep:production_temperature [°C]",
        "specific_investment_cost": "rep:specific_investment_cost [$/kW]",
        "OPEX": "rep:OPEX [$/yr]",
        "ideal_distance": "ideal_distance [normalized, 0 = ideal corner]",
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
