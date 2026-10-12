"""Shared constants and utilities for the tango double-flash sensitivity sweep pipeline.

The sweep design is one-at-a-time (OFAT): each parameter moves to its
low/high bound in its own design point, everything else at baseline —
see ``generate.py``'s module docstring for the full rationale (a full
simultaneous Latin Hypercube draw across ~23 continuous parameters has a
near-0% feasible-design rate against tango's validation, since most
random combinations push some part of the plant/well/reservoir model out
of its valid range at once).

``PARAMETER_BOUNDS`` below gives each parameter's low/high scale factor,
keyed by tango's nested
``common.*``/``layout.*``/``sim_config.*``/``components.<name>.*``
config-dict paths, targeting ``example_configs/hydro_df_electric.yml``.
Two parameters are excluded entirely (documented inline below) because
the corresponding tango schema field doesn't exist:

- ``props.brine_density`` — ``Common``'s schema (``core/specs.py``,
  ``extra="forbid"``) has no ``brine_density`` field; confirmed dead/removed
  from every ``example_configs/*.yml`` file already.
- ``schedule.num_pp`` — ``Layout``'s schema has no ``num_pp`` field at all;
  not a tango concept yet.

``injection_well.well_length`` is also excluded from the sweep bounds —
see ``sweep.py``'s sync step, which overwrites it with
``production_well.well_length + production_well_pump.well_length`` after all
other scale factors are applied.

Bounds reflect real validation limits, physics/CoolProp constraints, and
sensitivity considerations for each physical quantity (see inline
comments below).
"""

import shutil
from pathlib import Path

import yaml

# Paths
SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = SCRIPT_DIR.parents[1]
BASE_YAML = _REPO_ROOT / "example_configs" / "hydro_df_electric.yml"
DEFAULT_SWEEP_DIR = SCRIPT_DIR / "outputs"
PARAMS_FILE = SCRIPT_DIR / "params.yaml"

# Parameter bounds: (min_scale, max_scale) relative to base YAML values.
PARAMETER_BOUNDS: dict[str, tuple[float, float]] = {
    # --- Material properties (relatively flexible) ---
    # props.brine_density dropped — no tango Common field (see docstring).
    "common.rock_density": (0.8, 1.2),  # scale factor, ±20%
    "common.rock_cp": (0.5, 1.5),  # scale factor, 500-1500 J/(kg*K): the full range Common accepts
    "common.rock_k": (0.5, 2.0),  # scale factor, wide range ok
    "common.thermal_gradient": (0.7, 1.5),  # scale factor, ±30-50%
    # --- Surface parameters ---
    "common.surface_temperature": (0.9, 1.1),  # scale factor, ±10% (base ~288K)
    "common.surface_pressure": (0.9, 1.05),  # scale factor, 90-105 kPa (Common accepts 90-108.4 kPa)
    "components.surface.pipe_diameter": (0.5, 2.0),  # scale factor, max 5m validation limit
    "components.surface.approach_temperature": (0.5, 2.0),  # scale factor, 3.5-14K range
    "sim_config.target_extraction_pressure": (
        0.7,
        1.5,
    ),  # scale factor, CoolProp sensitive — sourced from sim_config: (not a
    # components.surface.* override, which Workflow rejects; see
    # _PROTECTED_COMPONENT_KEYS in workflows/workflow.py)
    # --- Reservoir parameters ---
    "components.reservoir.reservoir_depth": (0.5, 1.5),  # scale factor, 2.5-7.5km range
    "components.reservoir.thickness": (0.5, 2.0),  # scale factor, 150-600m range
    "components.reservoir.permeability": (
        0.1,
        10.0,
    ),  # scale factor, wide range (log-scale in reality)
    "components.reservoir.porosity": (0.5, 2.0),  # scale factor, 5-20% range
    "components.reservoir.hydro_static_pressure": (0.8, 1.2),  # scale factor, ±20%
    "components.reservoir.over_pressure_percentage": (0.5, 2.0),  # scale factor, 5-20% range
    # --- Well parameters (constrained by 15km max validation limit) ---
    # Base: inj=5km, prod=4km, pump=1km -> total prod=5km
    # injection_well.well_length dropped — synced post-hoc (see docstring
    # and sweep.py's _sync_injection_well_length), not swept independently.
    "components.injection_well.diameter": (0.5, 2.0),  # scale factor, max ~0.8m (under 5m limit)
    "components.production_well_lower.well_length": (0.5, 2.5),  # scale factor, max ~10km
    "components.production_well_lower.diameter": (
        0.5,
        2.0,
    ),  # scale factor; also sets the upper section (see LINKED_PATHS)
    "components.production_well_upper.well_length": (0.5, 2.5),  # scale factor, max ~2.5km
    # --- Schedule parameters ---
    "sim_config.mass_rate": (0.5, 2.0),  # scale factor, 25-100 kg/s
    "layout.well_spacing": (0.5, 2.0),  # scale factor, 350-1400m — the sole
    # source of this value (components.surface.* cannot override it; see
    # _PROTECTED_COMPONENT_KEYS in workflows/workflow.py)
    # schedule.num_pp dropped — no tango Layout field (see docstring).
    # --- Economic parameters (flexible) ---
    # Harmless to keep even though nothing reads economic.* yet — same as
    # the raw economic: block already retained verbatim in Workflow.to_dict().
    "economic.discount_rate": (0.5, 2.0),  # scale factor, 4.75-19%
    # --- Power plant components (pressure-sensitive, CoolProp constraints) ---
    # high_pressure_flash_valve/high_pressure_turbine/high_pressure_condenser/low_pressure_flash_valve/low_pressure_turbine/low_pressure_condenser/brine_pump/condensate_pump's
    # p_out fields are stored in MPa; since this is a scale-factor sweep,
    # the unit doesn't matter — the scale factor applies directly to
    # whatever unit is already there.
    "components.surface.power_plant.nodes.high_pressure_flash_valve.p_out_megapascals": (
        0.5,
        2.0,
    ),  # 0.5-2 bar equiv
    "components.surface.power_plant.nodes.high_pressure_turbine.efficiency": (
        0.7,
        1.0,
    ),  # 70-100% (capped at 1.0)
    # The condensing pressure: also sets both turbines' exhaust pressure (see
    # LINKED_PATHS), since each turbine expands straight to it.
    "components.surface.power_plant.nodes.high_pressure_condenser.p_out_megapascals": (0.5, 3.0),
    "components.surface.power_plant.nodes.high_pressure_condenser.subcooling_K": (
        1.0,
        1.0,
    ),  # fixed (no variation)
    "components.surface.power_plant.nodes.low_pressure_flash_valve.p_out_megapascals": (0.5, 2.0),
    "components.surface.power_plant.nodes.low_pressure_turbine.efficiency": (0.7, 1.0),
    # low_pressure_condenser has no p_out field at all (pinned via condensate_mixer's equal-pressure
    # constraint with high_pressure_condenser — see hydro_df_electric.yml's comment).
    "components.surface.power_plant.nodes.low_pressure_condenser.subcooling_K": (
        1.0,
        1.0,
    ),  # fixed (no variation)
    "components.surface.power_plant.nodes.brine_pump.efficiency": (0.7, 1.0),
    "components.surface.power_plant.nodes.condensate_pump.efficiency": (0.7, 1.0),
}

PARAMETERS = list(PARAMETER_BOUNDS.keys())

LINKED_PATHS: dict[str, tuple[str, ...]] = {
    # The cost model requires one production-well diameter.
    "components.production_well_lower.diameter": ("components.production_well_upper.diameter",),
    # Scaling a turbine's exhaust apart from the condenser it feeds would make
    # pressure rise across a passive part (rejected at config time).
    "components.surface.power_plant.nodes.high_pressure_condenser.p_out_megapascals": (
        "components.surface.power_plant.nodes.high_pressure_turbine.p_out_megapascals",
        "components.surface.power_plant.nodes.low_pressure_turbine.p_out_megapascals",
    ),
}
"""Extra config paths each listed parameter's scale factor also applies to, so
values that must stay equal move together."""

# Defaults (overridden by params.yaml if present)
DEFAULT_N_WORKERS = 8
DEFAULT_LOG_LEVEL = "NONE"


def load_params() -> dict:
    """Load parameters from params.yaml if it exists alongside the script."""
    if PARAMS_FILE.exists():
        return yaml.safe_load(PARAMS_FILE.read_text()) or {}
    return {}


def clean_sweep_dir(sweep_dir: Path, quiet: bool = False) -> None:
    """Remove every generated artifact from a sweep directory, preserving .gitignore.

    Everything under a sweep dir (design matrix, results/, results.parquet,
    summary.yaml) is regenerable output — nothing else is tracked in git —
    so this simply empties the directory rather than tracking individual
    filenames, which would drift out of sync as summarize.py gains or
    renames outputs.
    """
    if not sweep_dir.exists():
        if not quiet:
            print(f"{sweep_dir} does not exist, nothing to clean")
        return
    removed = []
    for item in sorted(sweep_dir.iterdir()):
        if item.name == ".gitignore":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
        removed.append(item.name)
    if not quiet:
        if removed:
            print(f"Cleaned {sweep_dir}: removed {', '.join(removed)}")
        else:
            print(f"{sweep_dir} already clean")


def get_nested_value(d: dict, path: str):
    """Get value from nested dict using dot-separated path."""
    keys = path.split(".")
    for key in keys:
        d = d[key]
    return d


def set_nested_value(d: dict, path: str, value) -> None:
    """Set value in nested dict using dot-separated path."""
    keys = path.split(".")
    for key in keys[:-1]:
        d = d[key]
    d[keys[-1]] = value
