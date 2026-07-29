"""Shared constants and utilities for the tango_next double-flash LHS sweep pipeline.

This is the tango_next port of
``applications/run_flexible_DF_manual_sweep/common.py``. Unlike the AGS/EGS
direct-heat ports (full-factorial grids over 2-4 named axes), old tango's DF
manual sweep is a Latin Hypercube Sample (LHS) over ~23 continuous
parameters, each varied by a random scale factor within per-parameter
bounds — see ``generate.py``/``sweep.py`` for the sampling and mutation
mechanics, which are otherwise unchanged from old tango.

``PARAMETER_BOUNDS`` below is old tango's dict translated key-by-key from
flat ``specs`` dot-paths to tango_next's nested
``common.*``/``layout.*``/``sim_config.*``/``components.<name>.*`` config-dict
paths, targeting ``examples/tango_next/hydro_double_flash_electric.yml``
instead of ``examples/flexible_DF_manual.yml``. Two parameters from old
tango's dict are dropped entirely (documented inline below) because the
corresponding tango_next schema field doesn't exist:

- ``props.brine_density`` — ``Common``'s schema (``core/specs.py``,
  ``extra="forbid"``) has no ``brine_density`` field; confirmed dead/removed
  from every ``examples/tango_next/*.yml`` file already.
- ``schedule.num_pp`` — ``Layout``'s schema has no ``num_pp`` field at all;
  not a tango_next concept yet.

``injection_well.well_length`` is also dropped from the sweep bounds (its
sampled scale factor was thrown away in old tango too — see ``sweep.py``'s
sync step, which overwrites it with
``production_well.well_length + production_well_pump.well_length`` after all
other scale factors are applied). The old-tango ``_seq`` sync step
(``well_length_seq``/``well_diameter_seq``) has no tango_next equivalent —
``NumericalWell``'s schema has no ``_seq`` fields (an old-tango
multi-segment-well artifact) — so it is not replicated at all.

Bounds themselves are copied verbatim from old tango's ``PARAMETER_BOUNDS``
(same rationale comments: validation limits, physics/CoolProp constraints,
sensitivity considerations) since the underlying physical quantities and
their sensible ranges haven't changed — only the config-dict path to reach
each one has.
"""

import shutil
from pathlib import Path

import yaml

# Paths
SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = SCRIPT_DIR.parents[2]
BASE_YAML = _REPO_ROOT / "examples" / "tango_next" / "hydro_double_flash_electric.yml"
DEFAULT_SWEEP_DIR = SCRIPT_DIR / "outputs"
PARAMS_FILE = SCRIPT_DIR / "params.yaml"

# Parameter bounds: (min_scale, max_scale) relative to base YAML values.
# See module docstring for the old-tango -> tango_next path translation
# table (also documented in full in the porting task notes).
PARAMETER_BOUNDS: dict[str, tuple[float, float]] = {
    # --- Material properties (relatively flexible) ---
    # props.brine_density dropped — no tango_next Common field (see docstring).
    "common.rock_density": (0.8, 1.2),  # scale factor, ±20%
    "common.rock_cp": (0.5, 2.0),  # scale factor, wide range ok
    "common.rock_k": (0.5, 2.0),  # scale factor, wide range ok
    "common.thermal_gradient": (0.7, 1.5),  # scale factor, ±30-50%
    # --- Surface parameters ---
    "common.surface_temperature": (0.9, 1.1),  # scale factor, ±10% (base ~288K)
    "common.surface_pressure": (0.9, 1.1),  # scale factor, ±10% (base 100kPa)
    "components.surface.pipe_diameter": (0.5, 2.0),  # scale factor, max 5m validation limit
    "components.surface.approach_temperature": (0.5, 2.0),  # scale factor, 3.5-14K range
    "components.surface.target_extraction_pressure": (
        0.7,
        1.5,
    ),  # scale factor, CoolProp sensitive
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
    "components.production_well_lower.diameter": (0.5, 2.0),  # scale factor
    "components.production_well_upper.well_length": (0.5, 2.5),  # scale factor, max ~2.5km
    "components.production_well_upper.diameter": (0.5, 2.0),  # scale factor
    # --- Schedule parameters ---
    "sim_config.mass_rate": (0.5, 2.0),  # scale factor, 25-100 kg/s
    "layout.well_spacing": (0.5, 2.0),  # scale factor, 350-1400m — kept in
    # sync with components.surface.well_spacing, see sweep.py
    # schedule.num_pp dropped — no tango_next Layout field (see docstring).
    # --- Economic parameters (flexible) ---
    # Harmless to keep even though nothing reads economic.* yet — same as
    # the raw economic: block already retained verbatim in Workflow.to_dict().
    "economic.discount_rate": (0.5, 2.0),  # scale factor, 4.75-19%
    # --- Power plant components (pressure-sensitive, CoolProp constraints) ---
    # valve1/turbine1/condenser1/valve2/turbine2/condenser2/pump1/pump2's
    # p_out fields are stored in MPa in tango_next (vs. bar in old tango);
    # since this is a scale-factor sweep, the unit doesn't matter — the
    # scale factor applies directly to whatever unit is already there.
    "components.surface.power_plant.nodes.valve1.p_out_megapascals": (0.5, 2.0),  # 0.5-2 bar equiv
    "components.surface.power_plant.nodes.turbine1.efficiency": (0.7, 1.0),  # 70-100% (capped at 1.0)
    "components.surface.power_plant.nodes.turbine1.p_out_megapascals": (0.5, 3.0),
    "components.surface.power_plant.nodes.condenser1.p_out_megapascals": (0.5, 3.0),
    "components.surface.power_plant.nodes.condenser1.vapor_mass_fraction_out": (
        1.0,
        1.0,
    ),  # fixed (no variation)
    "components.surface.power_plant.nodes.valve2.p_out_megapascals": (0.5, 2.0),
    "components.surface.power_plant.nodes.turbine2.efficiency": (0.7, 1.0),
    "components.surface.power_plant.nodes.turbine2.p_out_megapascals": (0.5, 3.0),
    # condenser2 has no p_out field at all (pinned via merge1's equal-pressure
    # constraint with condenser1 — see hydro_double_flash_electric.yml's
    # comment); old tango has no condenser2.p_out parameter either, so
    # there's nothing to translate here.
    "components.surface.power_plant.nodes.condenser2.vapor_mass_fraction_out": (
        1.0,
        1.0,
    ),  # fixed (no variation)
    "components.surface.power_plant.nodes.pump1.efficiency": (0.7, 1.0),
    "components.surface.power_plant.nodes.pump2.efficiency": (0.7, 1.0),
}

PARAMETERS = list(PARAMETER_BOUNDS.keys())

# Defaults (overridden by params.yaml if present)
DEFAULT_N_SAMPLES = 100
DEFAULT_N_WORKERS = 8
DEFAULT_SEED = 42
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
