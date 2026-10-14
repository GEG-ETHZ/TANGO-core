"""Multi-objective optimization of the CO2 AGS binary-cycle (ORC) electric example.

Searches well depth, horizontal loop length, horizontal loop diameter, vertical
well diameter, mass flow rate, injection pressure, surface pipe diameter,
``preheater``'s outlet pressure, and ORC feed-pump (evaporating) pressure with
NSGA2 to minimize LCOE and maximize mean net electric power. Production
temperature, specific investment cost, and OPEX are reporting-only read-outs.

Not tuned: the ORC condensing pressure
(``orc_turbine``/``orc_desuperheater``/``orc_condenser``), which follows from
the site's cooling limit (surface temperature plus ``approach_temperature``),
so it is a site condition rather than a design choice.

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
opt_CO2_AGS_ORC_electric`` on Euler) runs the ``optimize`` and ``plot`` stages
in ``dvc.yaml``. Running this script directly with ``uv run python
opt_CO2_AGS_ORC_electric.py`` also works but bypasses DVC's tracking.
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


@dataclass
class _OrcFeedPumpPressureApply:
    """Picklable ``ParamSpec.apply`` for the ORC feed-pump outlet pressure (MPa).

    ``orc_feed_pump``'s outlet pressure is the ORC's high pressure: the
    preheater and evaporator both have ``pressure_ratio2: 1.0``, so it is also
    the evaporating pressure and the turbine inlet pressure. The evaporator's
    ``vapor_mass_fraction_out2: 1`` then fixes the evaporating temperature at
    the working fluid's saturation temperature at this pressure.

    Also moves the preheater's and evaporator's ``p0_megapascals_out2`` (TESPy starting
    guesses for those same connections) to this pressure. The evaporator's
    CO2-side enthalpy guess (``h0_out1``) is left at the config's value: CO2's
    enthalpy there depends strongly on a pressure that isn't known until the
    wells are solved.
    """

    def __call__(self, cfg: dict[str, Any], value: float) -> dict[str, Any]:
        nodes = cfg["components"]["surface"]["power_plant"]["nodes"]
        nodes["orc_feed_pump"]["p_out_megapascals"] = float(value)
        nodes["preheater"]["p0_megapascals_out2"] = float(value)
        nodes["evaporator"]["p0_megapascals_out2"] = float(value)
        return cfg

    def read(self, cfg: dict[str, Any]) -> float:
        return float(
            cfg["components"]["surface"]["power_plant"]["nodes"]["orc_feed_pump"]["p_out_megapascals"],
        )


DEFAULT_BOUNDS: dict[str, tuple[float, float]] = {
    # Brackets the config's own depth.
    "depth_m": (6000.0, 10000.0),
    # Loop geometry and diameters: the same ranges as opt_AGS_direct_heat.
    "loop_length_m": (500.0, 8000.0),
    "loop_diameter_m": (0.15, 0.75),
    "vertical_well_diameter_m": (0.2, 0.75),
    "mass_rate_kg_per_s": (5.0, 70.0),
    "injection_pressure_Pa": (5000000.0, 12000000.0),
    "surface_pipe_diameter_m": (0.2, 0.75),
    "preheater_outlet_pressure_MPa": (7.5, 11.0),
    # Lower bound stays well above the ORC condensing pressure, so the feed
    # pump always raises pressure. Upper bound saturates R245fa at ~110 degC:
    # the produced CO2 arrives at roughly 90-120 degC, and evaporating closer
    # to that leaves too little heat transfer for the ORC to cover the plant's
    # pumps (random samples above ~1 MPa were almost all net power consumers).
    "orc_feed_pump_pressure_MPa": (0.35, 1.5),
}


def param_specs(bounds: dict[str, tuple[float, float]]) -> list[ParamSpec]:
    """Decision variables.

    - ``depth_m`` sets both vertical wells and the horizontal loop's starting
      depth.
    - ``loop_length_m`` also sets ``layout.well_spacing`` (the surface pipe
      run), which by convention equals the loop length; it is set only there,
      since ``tango`` rejects component-level overrides of ``layout:`` fields.
    - ``vertical_well_diameter_m`` sets the injection and production wells
      together, which also satisfies ``DoubletEconomicComponent``'s uniform-
      diameter requirement on the production side.
    - ``surface_pipe_diameter_m`` sets both the surface pipe's friction
      pressure drop and its cost.
    - ``preheater_outlet_pressure_MPa`` is the CO2 side's outlet pressure at
      ``preheater``, kept above CO2's 7.38 MPa critical pressure; a value above
      the pressure actually arriving there is rejected as free compression.
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
            "preheater_outlet_pressure_MPa",
            bounds["preheater_outlet_pressure_MPa"],
            "components.surface.power_plant.nodes.preheater.p_out_megapascals",
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
    title="CO2_AGS_ORC_electric",
    description="Multi-objective optimization of the CO2 AGS binary-cycle (ORC) electric example.",
    config_path=HERE.parents[1] / "example_configs" / "CO2_AGS_ORC_electric.yml",
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
        "preheater_outlet_pressure_MPa": "par:preheater_outlet_pressure [MPa]",
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
