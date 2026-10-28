"""Multi-objective optimization of the AGS direct-heat (district heating) example.

Searches well depth, horizontal loop length, horizontal loop diameter,
vertical well diameter, surface pipe diameter, injection pressure, and mass
flow rate with NSGA2 to minimize LCOE and maximize mean net thermal power,
subject to the production-well outlet staying hot enough for district heating
(``--min-production-temperature-c``, 105 degC by default). Production
temperature, specific investment cost, and OPEX are reporting-only read-outs.

Every decision variable ``AGS_direct_heat.yml`` exposes is included, except
``target_extraction_pressure``: it is read only by pump-bearing production
wells, and AGS's ``production_well`` is a plain numerical well, so the value
is inert for this topology. The plant has no tunable pressures: the
district-heating exchanger's outlet is a ``pressure_ratio`` and
``circulation_control`` takes whatever pressure change ``injection_pressure``
requires.

The injection policy is forced to ``manual``: the ``auto-*`` policies solve
for mass flow rate or injection pressure on every pass, which would fight the
optimizer over the same variables, and AGS has no reservoir for
``manual-fracking-check`` to protect.

The ``ParamSpec``/``ObjectiveSpec``/``ConstraintSpec`` factories are defined
here, not in ``pymoo_api.py``, which stays generic (see ``ParamSpec``'s
docstring); the CLI, baseline, search, and plots come from
``tango.pymoo_api.OptApp``.

Usage: ``dvc repro`` from this directory (or ``just slurm opt_AGS_direct_heat``
on Euler) runs the ``optimize`` and ``plot`` stages in ``dvc.yaml``. Running
this script directly with ``uv run python opt_AGS_direct_heat.py`` also works
but bypasses DVC's tracking.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tango.components.well.numerical import WellLengthSideEffect, set_well_length
from tango.core.policies import InjectionPolicy
from tango.pymoo_api import ConstraintSpec, ObjectiveScatter, ObjectiveSpec, OptApp, ParamSpec
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
    # The front sits on the deep cap: deeper rock is hotter and nothing in the
    # model pushes back (1 km deeper is ~9-12% cheaper). Whether the cap is a
    # real drilling limit, and whether well cost holds beyond ~8 km, is open
    # (#120).
    "depth_m": (2_000.0, 4_500.0),
    # Loop length and diameter sit at their caps but are near their optima:
    # 9 km or 0.85 m changes LCOE by at most ~2%, sometimes for the worse.
    "loop_length_m": (500.0, 8_000.0),
    "loop_diameter_m": (0.15, 0.75),
    # From 6 inch (0.15 m), as in the other apps. Smaller vertical wells are
    # cheaper and lose less heat on the way up, so the front sat on the old
    # 0.2 m floor. At this app's low flow (~8 kg/s) friction barely matters
    # until ~0.08-0.10 m, where the production well can no longer lift the
    # fluid (it boils or its pressure collapses), so 0.15 m stays well clear.
    "vertical_well_diameter_m": (0.15, 0.75),
    # The front sits on the 0.2 m floor: pipe friction is free while the
    # thermosiphon has spare pressure for circulation_control to throttle, so
    # a smaller pipe is only cheaper. The real limit, flow velocity, isn't
    # modeled; 0.2 m stands in for it (#120).
    "surface_pipe_diameter_m": (0.2, 0.75),
    # The front sits on the 0.5 MPa floor, but the thermosiphon sets the
    # loop's pressure: 0.3 MPa gives the same LCOE.
    "injection_pressure_Pa": (0.5e6, 3.0e6),
    "mass_rate_kg_per_s": (3.5, 50.0),
}


def param_specs(bounds: dict[str, tuple[float, float]]) -> list[ParamSpec]:
    """Decision variables.

    - ``depth_m`` sets both vertical wells and the horizontal loop's starting
      depth.
    - ``loop_length_m`` sets the horizontal well's length; ``layout.well_spacing``
      (the surface pipe run) is derived from it, since the wellheads are a loop
      length apart.
    - ``vertical_well_diameter_m`` sets the injection and production wells
      together, which also satisfies ``DoubletEconomicComponent``'s
      uniform-diameter requirement on the production side.
    - ``surface_pipe_diameter_m`` sets both the surface pipe's friction
      pressure drop and its cost.
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
        _param(
            "surface_pipe_diameter_m",
            bounds["surface_pipe_diameter_m"],
            "components.surface.pipe_diameter",
        ),
        _param(
            "injection_pressure_Pa",
            bounds["injection_pressure_Pa"],
            "components.surface.injection_pressure",
        ),
        _param("mass_rate_kg_per_s", bounds["mass_rate_kg_per_s"], "sim_config.mass_rate"),
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
class _NegativeMeanThermalPowerEvaluate:
    """Picklable ``ObjectiveSpec.evaluate``: ``-`` mean of the surface's ``history.net_thermal_W``."""

    def __call__(self, wf: Workflow) -> float:
        net_thermal_w: list[float] = wf._orchestrator.components["surface"].history.net_thermal_W  # noqa: SLF001
        return -sum(net_thermal_w) / len(net_thermal_w)


def _final_production_temperature_c(wf: Workflow) -> float:
    """Final-timestep production-well outlet temperature (degC)."""
    t_outlet_k: list[float] = wf._orchestrator.components["production_well"].history.T_outlet  # noqa: SLF001
    return t_outlet_k[-1] - 273.15


@dataclass
class _NegativeProductionTemperatureEvaluate:
    """Picklable ``ObjectiveSpec.evaluate``: ``-`` final production-well outlet temperature (degC).

    The final timestep, not a run average: it's the longest-run outlet
    temperature the plant has to keep working with.
    """

    def __call__(self, wf: Workflow) -> float:
        return -_final_production_temperature_c(wf)


MIN_PRODUCTION_TEMPERATURE_C = 105.0
"""District-heating supply threshold (degC) for the production-temperature constraint."""


@dataclass
class _ProductionTemperatureConstraintEvaluate:
    """Picklable ``ConstraintSpec.evaluate``: kelvin below ``min_temperature_c`` (``<= 0`` is satisfied).

    A violation magnitude rather than a flat sign, so NSGA2 can climb back
    toward feasibility (see ``ConstraintSpec``).
    """

    min_temperature_c: float

    def __call__(self, wf: Workflow) -> float:
        return self.min_temperature_c - _final_production_temperature_c(wf)


def constraint_specs(args: argparse.Namespace) -> list[ConstraintSpec]:
    """The production-temperature floor, at ``--min-production-temperature-c``."""
    return [
        ConstraintSpec(
            name="production_temperature_constraint",
            evaluate=_ProductionTemperatureConstraintEvaluate(args.min_production_temperature_c),
        ),
    ]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """``--min-production-temperature-c``."""
    parser.add_argument(
        "--min-production-temperature-c",
        type=float,
        default=MIN_PRODUCTION_TEMPERATURE_C,
        help=(
            f"Production-temperature constraint threshold (degC, default {MIN_PRODUCTION_TEMPERATURE_C}). "
            "--smoke sets it to 0: a tiny population can miss the real threshold entirely and leave an "
            "empty Pareto front for the plots."
        ),
    )


# Mean rather than total energy: every timestep has the same duration, so the
# two carry the same optimization signal, and a mean in W is easier to read.
OBJECTIVES = [
    ObjectiveSpec(name="LCOE", evaluate=_EconomicStateEvaluate("LCOE")),
    ObjectiveSpec(name="negative_mean_thermal_power_W", evaluate=_NegativeMeanThermalPowerEvaluate()),
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
    title="AGS_direct_heat",
    description="Multi-objective optimization of the AGS direct-heat (district heating) example.",
    config_path=HERE.parents[1] / "templates" / "AGS_direct_heat.yml",
    app_dir=HERE,
    injection_mode=InjectionPolicy.MANUAL,
    default_bounds=DEFAULT_BOUNDS,
    param_factory=param_specs,
    objective_specs=OBJECTIVES,
    report_specs=REPORTS,
    constraint_factory=constraint_specs,
    configure_parser=add_arguments,
    smoke_args=["--min-production-temperature-c", "0"],
    display_rename={
        "negative_mean_thermal_power_W": "mean_thermal_power_W",
        "negative_production_temperature_C": "production_temperature_C",
    },
    column_labels={
        "depth_m": "par:depth [m]",
        "loop_length_m": "par:loop_length [m]",
        "loop_diameter_m": "par:loop_diameter [m]",
        "vertical_well_diameter_m": "par:vertical_well_diameter [m]",
        "surface_pipe_diameter_m": "par:surface_pipe_diameter [m]",
        "injection_pressure_Pa": "par:injection_pressure [Pa]",
        "mass_rate_kg_per_s": "par:mass_rate [kg/s]",
        "LCOE": "obj:LCOE [$/kWh]",
        "mean_thermal_power_W": "obj:mean_thermal_power [W]",
        "production_temperature_C": "rep:production_temperature [°C]",
        "specific_investment_cost": "rep:specific_investment_cost [$/kW]",
        "OPEX": "rep:OPEX [$/yr]",
        "ideal_distance": "ideal_distance [normalized, 0 = ideal corner]",
    },
    scatter=ObjectiveScatter(
        x_col="LCOE",
        x_label="LCOE ($/kWh)",
        y_col="mean_thermal_power_W",
        y_label="Mean net thermal power (MW)",
        y_scale=1.0e-6,
        color_col="production_temperature_C",
    ),
)

if __name__ == "__main__":
    APP.main()
