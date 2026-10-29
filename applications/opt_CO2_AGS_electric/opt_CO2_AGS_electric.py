"""Multi-objective optimization of the CO2 AGS direct-turbine electric example.

Searches well depth, horizontal loop length, horizontal loop diameter, vertical
well diameter, mass flow rate, injection pressure, surface pipe diameter, and
CO2 condensing pressure with NSGA2 to minimize LCOE and maximize mean net
electric power. Production temperature, specific investment cost, and OPEX are
reporting-only read-outs.

Not tuned: nothing else in the plant.

``target_extraction_pressure`` is left out: it is read only by pump-bearing
production wells, and AGS's ``production_well`` is a plain numerical well, so
the value is inert.

The injection policy is forced to ``manual``: the ``auto-*`` policies solve for
mass flow rate or injection pressure on every pass, which would fight the
optimizer over the same variables, and AGS has no reservoir for ``manual-
fracking-check`` to protect.

The ``ParamSpec``/``ObjectiveSpec`` factories are defined here, not in
``pymoo_api.py``, which stays generic (see ``ParamSpec``'s docstring); the CLI,
baseline, search, and plots come from ``tango.pymoo_api.OptApp``.

Usage: ``dvc repro`` from this directory (or ``just slurm
opt_CO2_AGS_electric`` on Euler) runs the ``optimize`` and ``plot`` stages in
``dvc.yaml``. Running this script directly with ``uv run python
opt_CO2_AGS_electric.py`` also works but bypasses DVC's tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tango.components.well.numerical import WellLengthSideEffect, set_well_length
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
class _DepthApply:
    """Picklable ``ParamSpec.apply`` for the loop's depth, i.e. the injection well's length.

    The production well's length and the horizontal well's starting depth
    are derived from it (``tango.workflows.linked_quantities``). The length
    changes through ``set_well_length`` with ``KEEP_CELL_LENGTH``, so the
    well's axial resolution stays what the config asked for (or the
    default) instead of stretching a fixed cell count over the new length.
    """

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        set_well_length(
            cfg["components"]["injection_well"],
            float(value),
            WellLengthSideEffect.KEEP_CELL_LENGTH,
        )
        return cfg

    def read(self, cfg: dict[str, Any]) -> float:
        return float(cfg["components"]["injection_well"]["well_length"])


@dataclass
class _LoopLengthApply:
    """Picklable ``ParamSpec.apply`` for the horizontal loop's length.

    ``layout.well_spacing`` is derived from it. See ``_DepthApply`` for why
    the length goes through ``set_well_length``.
    """

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        set_well_length(
            cfg["components"]["horizontal_well"],
            float(value),
            WellLengthSideEffect.KEEP_CELL_LENGTH,
        )
        return cfg

    def read(self, cfg: dict[str, Any]) -> float:
        return float(cfg["components"]["horizontal_well"]["well_length"])


DEFAULT_BOUNDS: dict[str, tuple[float, float]] = {
    # Brackets the config's own depth.
    # The front sits on the deep cap: deeper rock is hotter and nothing in the
    # model pushes back (1 km deeper is ~9-12% cheaper). Whether the cap is a
    # real drilling limit, and whether well cost holds beyond ~8 km, is open
    # (#120).
    "depth_m": (6000.0, 10000.0),
    # Loop geometry and diameters: the same ranges as opt_AGS_direct_heat.
    # Loop length and diameter sit at their caps but are near their optima:
    # 9 km or 0.85 m changes LCOE by at most ~2%, sometimes for the worse.
    "loop_length_m": (500.0, 8000.0),
    "loop_diameter_m": (0.15, 0.75),
    "vertical_well_diameter_m": (0.2, 0.75),
    # The front sits on the 70 kg/s cap, but near its optimum: 80 kg/s is
    # slightly more expensive.
    "mass_rate_kg_per_s": (5.0, 70.0),
    "injection_pressure_Pa": (5000000.0, 12000000.0),
    "surface_pipe_diameter_m": (0.2, 0.75),
    # Lower bound: the pressure at which 3 K subcooled CO2 (the config's
    # subcooling_K, set so the condensate entering the injection well keeps a
    # 5% margin to saturation) reaches the site's cooling limit (lower fails
    # CoolingLimitError). Upper bound stays below CO2's 7.38 MPa critical
    # pressure.
    "condensing_pressure_MPa": (5.87, 7.0),
}


def param_specs(bounds: dict[str, tuple[float, float]]) -> list[ParamSpec]:
    """Decision variables.

    - ``depth_m`` sets both vertical wells and the horizontal loop's starting
      depth.
    - ``loop_length_m`` sets the horizontal well's length; ``layout.well_spacing``
      (the surface pipe run) is derived from it, since the wellheads are a loop
      length apart.
    - ``vertical_well_diameter_m`` sets the injection and production wells
      together, which also satisfies ``DoubletEconomicComponent``'s uniform-
      diameter requirement on the production side.
    - ``surface_pipe_diameter_m`` sets both the surface pipe's friction
      pressure drop and its cost.
    - ``condensing_pressure_MPa`` sets the turbine's exhaust and the
      condenser's outlet together, since the turbine expands straight to the
      condensing pressure.
    """
    return [
        ParamSpec(name="depth_m", apply=_DepthApply(), bounds=bounds["depth_m"]),
        ParamSpec(name="loop_length_m", apply=_LoopLengthApply(), bounds=bounds["loop_length_m"]),
        _param("loop_diameter_m", bounds["loop_diameter_m"], "components.horizontal_well.diameter"),
        _param(
            "vertical_well_diameter_m",
            bounds["vertical_well_diameter_m"],
            "components.injection_well.diameter",
            "components.production_well.diameter",
        ),
        _param("mass_rate_kg_per_s", bounds["mass_rate_kg_per_s"], "sim_config.mass_rate"),
        _param(
            "injection_pressure_Pa",
            bounds["injection_pressure_Pa"],
            "components.surface.injection_pressure",
        ),
        _param(
            "surface_pipe_diameter_m",
            bounds["surface_pipe_diameter_m"],
            "components.surface.pipe_diameter",
        ),
        _param(
            "condensing_pressure_MPa",
            bounds["condensing_pressure_MPa"],
            "components.surface.power_plant.nodes.turbine.p_out_megapascals",
            "components.surface.power_plant.nodes.condenser.p_out_megapascals",
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

    def __call__(self, wf: Workflow) -> float:
        t_outlet_k: list[float] = wf._orchestrator.components["production_well"].history.T_outlet  # noqa: SLF001
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
    title="CO2_AGS_electric",
    description="Multi-objective optimization of the CO2 AGS direct-turbine electric example.",
    config_path=HERE.parents[1] / "templates" / "CO2_AGS_electric.yml",
    app_dir=HERE,
    injection_mode=InjectionPolicy.MANUAL,
    default_bounds=DEFAULT_BOUNDS,
    param_factory=param_specs,
    objective_specs=OBJECTIVES,
    report_specs=REPORTS,
    display_rename={
        "negative_mean_power_W": "mean_power_W",
        "negative_production_temperature_C": "production_temperature_C",
    },
    column_labels={
        "depth_m": "par:depth [m]",
        "loop_length_m": "par:loop_length [m]",
        "loop_diameter_m": "par:loop_diameter [m]",
        "vertical_well_diameter_m": "par:vertical_well_diameter [m]",
        "mass_rate_kg_per_s": "par:mass_rate [kg/s]",
        "injection_pressure_Pa": "par:injection_pressure [Pa]",
        "surface_pipe_diameter_m": "par:surface_pipe_diameter [m]",
        "condensing_pressure_MPa": "par:condensing_pressure [MPa]",
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
