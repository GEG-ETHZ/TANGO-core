"""Shared constants and utilities for the Triemli direct-heat sweep pipeline."""

import shutil
from pathlib import Path

import yaml

# TODO: verify that TANGO is calculating the power as the mass flow rate times
# the specific heat times the outlet temperature minus the
# TODO: is there a heat exchanger effectiveness baked into this?
#
# TODO: figure out how OpEx is accounted
# TODO: figure out how to make sure that if power demand is lower than what's
# generated that we don't penalize ourselves by having pumping power required
# included in OpEx
# TODO: figure out how pumping power is calculated and it feeds into OpEx
# because then we can do a post hoc analysis to turn that off during summer or
# whatnot
# TODO: make sure the heat exchanger and any other surface plant components are
# included in CapEx

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

# Grid sweep axes — 10 × 10 = 100 designs.
# Depths chosen so that the geothermal gradient (35 °C/km) yields
# useful wellhead temperatures.
# At 35 °C/km + 11 °C surface → 105 °C outlet requires roughly 2700 m
# (accounting for heat loss in the 0.8× lower production segment).
WELL_DEPTHS_M: list[float] = [2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500]
# TODO: figure out how well depth in the parallel coordinates plot is calculated

# Mass flow rates in kg/s
MASS_FLOW_RATES_KG_S: list[float] = [5, 10, 15, 20, 30, 40, 50, 65, 80, 100]


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
