"""Shared constants and utilities for the Triemli direct-heat sweep pipeline."""

from pathlib import Path

import yaml

# Paths
SCRIPT_DIR = Path(__file__).parent
BASE_YAML = SCRIPT_DIR / "triemli_dh_base.yml"
DEFAULT_SWEEP_DIR = SCRIPT_DIR / "outputs"
PARAMS_FILE = SCRIPT_DIR / "params.yaml"

# Defaults
DEFAULT_N_WORKERS = 8
DEFAULT_LOG_LEVEL = "NONE"

# District-heating return temperature (°C) — fluid cools to this in the DH
# heat exchanger before being re-injected.  Matches DH.T_out in the YAML.
DH_RETURN_TEMP_C: float = 50.0
DH_RETURN_TEMP_K: float = DH_RETURN_TEMP_C + 273.15

# Grid sweep axes — 10 × 10 × 5 = 500 designs.
# Depths chosen so that the geothermal gradient (35 °C/km) yields
# useful wellhead temperatures for district heating.
# At 35 °C/km + 11 °C surface → 105 °C outlet requires roughly 2700 m
# (accounting for heat loss along the vertical production section of the AGS loop).
WELL_DEPTHS_M: list[float] = [2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500]

# Mass flow rates in kg/s
MASS_FLOW_RATES_KG_S: list[float] = [5, 10, 15, 20, 30, 40, 50, 65, 80, 100]

# Horizontal loop length in m. Previously held fixed at 2500 m with no
# justification beyond "keep the sweep 2-D"; that value was never reconciled
# against the web app's validated AGS_H2O reference (707 m — see
# examples/AGS_new/AGS_H2O_webapp_native.yml). Rather than pick one "correct"
# value, sweep it: 707 m is the exact validated reference point, the rest
# bracket the range up to the old fixed assumption so both prior values are
# covered by data instead of debate.
LOOP_LENGTHS_M: list[float] = [707, 1000, 1500, 2000, 2500]


def load_params() -> dict:
    """Load optional params.yaml override file."""
    if PARAMS_FILE.exists():
        return yaml.safe_load(PARAMS_FILE.read_text()) or {}
    return {}


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
