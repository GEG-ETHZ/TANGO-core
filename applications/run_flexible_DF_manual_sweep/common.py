"""Shared constants, paths, and utilities for the DF manual sweep pipeline."""

from pathlib import Path

import yaml

import tango

# Stage names
STAGE_GENERATE = "generate"
STAGE_SWEEP = "sweep"
STAGE_SUMMARIZE = "summarize"
STAGE_ALL = "all"

# Parameter bounds: (min_scale, max_scale) relative to base YAML values
# Bounds are derived from:
#   - Validation limits (e.g., well_length max 15km, diameter max 5m)
#   - Physics constraints (e.g., CoolProp valid ranges for pressures)
#   - Sensitivity considerations (some params can vary widely, others are sensitive)
PARAMETER_BOUNDS: dict[str, tuple[float, float]] = {
    # --- Material properties (relatively flexible) ---
    "props.brine_density": (0.9, 1.1),  # scale factor, ±10%
    "props.rock_density": (0.8, 1.2),  # scale factor, ±20%
    "props.rock_cp": (0.5, 2.0),  # scale factor, wide range ok
    "props.rock_k": (0.5, 2.0),  # scale factor, wide range ok
    "props.thermal_gradient": (0.7, 1.5),  # scale factor, ±30-50%
    # --- Surface parameters ---
    "surface.surface_temperature": (0.9, 1.1),  # scale factor, ±10% (base ~288K)
    "surface.surface_pressure": (0.9, 1.1),  # scale factor, ±10% (base 100kPa)
    "surface.pipe_diameter": (0.5, 2.0),  # scale factor, max 5m validation limit
    "surface.approach_temperature": (0.5, 2.0),  # scale factor, 3.5-14K range
    "surface.target_extraction_pressure": (
        0.7,
        1.5,
    ),  # scale factor, CoolProp sensitive
    # --- Reservoir parameters ---
    "reservoir.reservoir_depth": (0.5, 1.5),  # scale factor, 2.5-7.5km range
    "reservoir.thickness": (0.5, 2.0),  # scale factor, 150-600m range
    "reservoir.permeability": (
        0.1,
        10.0,
    ),  # scale factor, wide range (log-scale in reality)
    "reservoir.porosity": (0.5, 2.0),  # scale factor, 5-20% range
    "reservoir.hydro_static_pressure": (0.8, 1.2),  # scale factor, ±20%
    "reservoir.over_pressure_percentage": (0.5, 2.0),  # scale factor, 5-20% range
    # --- Well parameters (constrained by 15km max validation limit) ---
    # Base: inj=5km, prod=4km, pump=1km → total prod=5km
    # At 3x: 15km each → hits validation limit
    "injection_well.well_length": (
        0.5,
        2.5,
    ),  # scale factor, max ~12.5km (under 15km limit)
    "injection_well.diameter": (0.5, 2.0),  # scale factor, max ~0.8m (under 5m limit)
    "production_well.well_length": (0.5, 2.5),  # scale factor, max ~10km
    "production_well.diameter": (0.5, 2.0),  # scale factor
    "production_well_pump.well_length": (0.5, 2.5),  # scale factor, max ~2.5km
    "production_well_pump.diameter": (0.5, 2.0),  # scale factor
    # --- Schedule parameters ---
    "schedule.mass_flow_rate": (0.5, 2.0),  # scale factor, 25-100 kg/s
    "schedule.well_spacing": (0.5, 2.0),  # scale factor, 350-1400m
    "schedule.num_pp": (1.0, 3.0),  # scale factor, 1-3 patterns (integer)
    "schedule.mass_rate.value": (0.5, 2.0),  # scale factor, matches mass_flow_rate
    # --- Economic parameters (flexible) ---
    "economic.discount_rate": (0.5, 2.0),  # scale factor, 4.75-19%
    # --- Power plant components (pressure-sensitive, CoolProp constraints) ---
    "valve1.p_out": (0.5, 2.0),  # scale factor, 0.5-2 bar (base 1 bar)
    "turbine1.efficiency": (0.7, 1.0),  # scale factor, 70-100% (capped at 1.0)
    "turbine1.p_out": (0.5, 3.0),  # scale factor, 0.025-0.15 bar
    "condenser1.p_out": (0.5, 3.0),  # scale factor, 0.025-0.15 bar
    "condenser1.vapor_mass_fraction_out": (1.0, 1.0),  # fixed at 0 (no variation)
    "valve2.p_out": (0.5, 2.0),  # scale factor, 0.25-1 bar (base 0.5 bar)
    "turbine2.efficiency": (0.7, 1.0),  # scale factor, 70-100%
    "turbine2.p_out": (0.5, 3.0),  # scale factor, 0.025-0.15 bar
    "condenser2.vapor_mass_fraction_out": (1.0, 1.0),  # fixed at 0 (no variation)
    "pump1.efficiency": (0.7, 1.0),  # scale factor, 70-100%
    "pump2.efficiency": (0.7, 1.0),  # scale factor, 70-100%
}

PARAMETERS = list(PARAMETER_BOUNDS.keys())

# Defaults (overridden by params.yaml if present)
DEFAULT_N_SAMPLES = 100
DEFAULT_N_WORKERS = 8
DEFAULT_SEED = 42
DEFAULT_LOG_LEVEL = "NONE"

# Paths
DEFAULT_SWEEP_DIR = Path(__file__).parent / "outputs"
PARAMS_FILE = Path(__file__).parent / "params.yaml"
INPUT_FILE = Path(tango.__file__).parents[2] / "examples/flexible_DF_manual.yml"


def load_params() -> dict:
    """Load parameters from params.yaml if it exists alongside the script."""
    if PARAMS_FILE.exists():
        return yaml.safe_load(PARAMS_FILE.read_text()) or {}
    return {}


def get_nested_value(d: dict, path: str):
    """Get value from nested dict using dot-separated path."""
    keys = path.split(".")
    for key in keys:
        d = d[key]
    return d


def set_nested_value(d: dict, path: str, value):
    """Set value in nested dict using dot-separated path."""
    keys = path.split(".")
    for key in keys[:-1]:
        d = d[key]
    d[keys[-1]] = value
