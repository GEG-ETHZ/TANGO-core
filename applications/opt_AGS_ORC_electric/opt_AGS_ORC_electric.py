"""Multi-objective optimization of the AGS binary-cycle (ORC) electric example.

Searches well depth, horizontal loop length, horizontal loop diameter,
vertical well diameter, surface pipe diameter, injection pressure, mass flow
rate, and the ORC feed-pump outlet pressure with NSGA2 to minimize LCOE and
maximize mean net electric power. Production temperature, specific investment
cost, and OPEX are reporting-only read-outs.

Every decision variable ``AGS_ORC_electric.yml`` exposes is included, except:

- ``target_extraction_pressure``: read only by pump-bearing production wells.
  AGS's ``production_well`` is a plain numerical well, so the value is inert
  for this topology.
- The ORC condensing pressure (``orc_turbine``/``orc_desuperheater``/
  ``orc_condenser``'s ``p_out_megapascals``): it follows from the site's
  cooling limit (surface temperature plus ``approach_temperature``), so it is
  a site condition, not a design choice.

The injection policy is forced to ``manual``: the ``auto-*`` policies solve
for mass flow rate or injection pressure on every pass, which would fight the
optimizer over the same variables, and AGS has no reservoir for
``manual-fracking-check`` to protect.

The ``ParamSpec``/``ObjectiveSpec`` factories are defined here, not in
``pymoo_api.py``, which stays generic (see ``ParamSpec``'s docstring); the
CLI, baseline, search, and plots come from ``tango.pymoo_api.OptApp``.

Usage: ``dvc repro`` from this directory (or ``just slurm opt_AGS_ORC_electric``
on Euler) runs the ``optimize`` and ``plot`` stages in ``dvc.yaml``. Running
this script directly with ``uv run python opt_AGS_ORC_electric.py`` also
works but bypasses DVC's tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from CoolProp.CoolProp import PropsSI

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
    R245fa's saturation temperature at this pressure.

    Also moves the TESPy starting guesses that depend on this pressure, since
    a guess left at the base design's value makes the solve fail at many
    pressures inside the bounds:

    - the preheater's and evaporator's ``p0_megapascals_out2``, to this pressure;
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
        nodes["preheater"]["p0_megapascals_out2"] = float(value)
        nodes["evaporator"]["p0_megapascals_out2"] = float(value)

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
    # Brackets the base YAML's 8000 m. The shallow end is where produced
    # fluid gets too cool to evaporate R245fa at the lower feed-pump
    # pressures; the deep end matches the deepest closed-loop concepts.
    # The front sits on the deep cap: deeper rock is hotter and nothing in the
    # model pushes back (1 km deeper is ~9-12% cheaper). Whether the cap is a
    # real drilling limit, and whether well cost holds beyond ~8 km, is open
    # (#120).
    "depth_m": (6_000.0, 10_000.0),
    # Same ranges as opt_AGS_direct_heat for the loop geometry and well
    # diameters (the AGS sweep's own loop length/diameter axes).
    # Loop length and diameter sit at their caps but are near their optima:
    # 9 km or 0.85 m changes LCOE by at most ~2%, sometimes for the worse.
    "loop_length_m": (500.0, 8_000.0),
    "loop_diameter_m": (0.15, 0.75),
    "vertical_well_diameter_m": (0.2, 0.75),
    # The front sits on the 0.2 m floor: pipe friction is free while the
    # thermosiphon has spare pressure for circulation_control to throttle, so
    # a smaller pipe is only cheaper. The real limit, flow velocity, isn't
    # modeled; 0.2 m stands in for it (#120).
    "surface_pipe_diameter_m": (0.2, 0.75),
    "injection_pressure_Pa": (0.5e6, 6.0e6),
    "mass_rate_kg_per_s": (5.0, 70.0),
    # Lower bound stays well above the 0.125 MPa condensing pressure, so the
    # feed pump always raises pressure. Upper bound saturates R245fa at
    # ~142 degC, 0.65 MPa below its 3.65 MPa critical pressure; designs whose
    # produced fluid is too cool for the chosen pressure fail to solve and are
    # rejected as infeasible.
    "orc_feed_pump_pressure_MPa": (0.35, 3.0),
}


def param_specs(bounds: dict[str, tuple[float, float]]) -> list[ParamSpec]:
    """Decision variables.

    - ``depth_m`` sets both vertical wells and the horizontal loop's starting
      depth.
    - ``loop_length_m`` also sets ``layout.well_spacing`` (the surface pipe
      run), which by convention equals the loop length; it is set only there,
      since ``tango`` rejects component-level overrides of ``layout:`` fields.
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
    title="AGS_ORC_electric",
    description="Multi-objective optimization of the AGS binary-cycle (ORC) electric example.",
    config_path=HERE.parents[1] / "templates" / "AGS_ORC_electric.yml",
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
        "surface_pipe_diameter_m": "par:surface_pipe_diameter [m]",
        "injection_pressure_Pa": "par:injection_pressure [Pa]",
        "mass_rate_kg_per_s": "par:mass_rate [kg/s]",
        "orc_feed_pump_pressure_MPa": "par:orc_feed_pump_pressure [MPa]",
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
