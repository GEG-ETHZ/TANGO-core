"""Shared constants and utilities for the tango Triemli direct-heat sweep pipeline.

Targets ``templates/AGS_direct_heat.yml``.
"""

import shutil
from pathlib import Path

import yaml

# Paths
SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = SCRIPT_DIR.parents[1]
BASE_YAML = _REPO_ROOT / "templates" / "AGS_direct_heat.yml"
DEFAULT_SWEEP_DIR = SCRIPT_DIR / "outputs"
PARAMS_FILE = SCRIPT_DIR / "params.yaml"

# Defaults
DEFAULT_N_WORKERS = 8
DEFAULT_LOG_LEVEL = "NONE"

# District-heating return temperature (°C) — fluid cools to this in the DH
# heat exchanger before being re-injected. Matches AGS_direct_heat.yml's
# power_plant.nodes.district_heating_hx.T_out: 323.15 K exactly.
DH_RETURN_TEMP_C: float = 50.0
DH_RETURN_TEMP_K: float = DH_RETURN_TEMP_C + 273.15

# Grid sweep axes — 13 × 11 × 15 × 6 = 12,870 designs.
# Depths chosen so that the geothermal gradient (35 °C/km) yields
# useful wellhead temperatures for district heating.
WELL_DEPTHS_M: list[float] = [2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500, 7000, 7500, 8000]

MASS_FLOW_RATES_KG_S: list[float] = [3.5, 5, 7.5, 10, 12.5, 15, 20, 25, 30, 35, 40]

# Horizontal loop length in m. 1000 m is the floor, up to 8000 m,
# matching WELL_DEPTHS_M's max.
LOOP_LENGTHS_M: list[float] = [
    1000,
    1500,
    2000,
    2500,
    3000,
    3500,
    4000,
    4500,
    5000,
    5500,
    6000,
    6500,
    7000,
    7500,
    8000,
]

# Horizontal loop diameter in m.
LOOP_DIAMETERS_M: list[float] = [0.2, 0.311, 0.41, 0.5, 0.6, 0.75]


def load_params() -> dict:
    """Load optional params.yaml override file."""
    if PARAMS_FILE.exists():
        return yaml.safe_load(PARAMS_FILE.read_text()) or {}
    return {}


def clean_sweep_dir(sweep_dir: Path, quiet: bool = False) -> None:
    """Remove every generated artifact from a sweep directory, preserving .gitignore.

    Everything under a sweep dir (design matrix, results/, results.parquet,
    plots) is regenerable output — nothing else is tracked in git (see
    outputs/.gitignore) — so this simply empties the directory rather than
    tracking individual filenames, which would drift out of sync as
    summarize.py/plot.py gain or rename outputs.
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
