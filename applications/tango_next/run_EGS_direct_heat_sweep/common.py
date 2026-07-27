"""Shared constants and utilities for the tango_next Triemli EGS direct-heat sweep pipeline.

This is the tango_next port of ``applications/run_EGS_direct_heat_sweep/common.py``.
Sweep-axis constants (``WELL_DEPTHS_M``, ``MASS_FLOW_RATES_KG_S``) are copied
verbatim from that file so the two sweeps explore the exact same design
space; only the paths differ, since this sweep targets
``examples/tango_next/EGS_direct_heat.yml`` instead of a local
``triemli_dh_base.yml`` copy. Unlike the AGS direct-heat sweep (which has
four axes: depth, mass-flow, loop-length, loop-diameter), EGS has no
horizontal loop, so this is a 2-axis (depth x mass-flow) grid — see
``generate.py``.
"""

from pathlib import Path

import yaml

# Paths
SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = SCRIPT_DIR.parents[2]
BASE_YAML = _REPO_ROOT / "examples" / "tango_next" / "EGS_direct_heat.yml"
DEFAULT_SWEEP_DIR = SCRIPT_DIR / "outputs"
PARAMS_FILE = SCRIPT_DIR / "params.yaml"

# Defaults
DEFAULT_N_WORKERS = 8
DEFAULT_LOG_LEVEL = "NONE"

# District-heating return temperature (°C) — fluid cools to this in the DH
# heat exchanger before being re-injected. Matches EGS_direct_heat.yml's
# power_plant.nodes.dh_hx.T_out: 323.15 K exactly.
DH_RETURN_TEMP_C: float = 50.0
DH_RETURN_TEMP_K: float = DH_RETURN_TEMP_C + 273.15

# Grid sweep axes — 10 x 10 = 100 designs. Copied verbatim from
# applications/run_EGS_direct_heat_sweep/common.py.
# Depths chosen so that the geothermal gradient (35 °C/km) yields
# useful wellhead temperatures for district heating.
WELL_DEPTHS_M: list[float] = [2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500]

# Mass flow rates in kg/s
MASS_FLOW_RATES_KG_S: list[float] = [5, 10, 15, 20, 30, 40, 50, 65, 80, 100]


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
