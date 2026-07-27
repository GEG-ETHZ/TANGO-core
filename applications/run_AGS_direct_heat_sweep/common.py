"""Shared constants and utilities for the Triemli direct-heat sweep pipeline."""

from pathlib import Path

import yaml

# Confirmed 2026-07-27: the district-heating return water IS cooled to 50 °C
# before re-injection. `DH_RETURN_TEMP_C` below matches `DH.T_out: 50` in
# triemli_dh_base.yml exactly (both are the district-heating heat exchanger's
# fixed outlet-temperature target) — see also the DH_RETURN_TEMP_K fallback
# discussion in sweep.py.
# TODO: ask for review from Aline

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

# Grid sweep axes — 13 × 11 × 15 × 6 = 12,870 designs.
# Depths chosen so that the geothermal gradient (35 °C/km) yields
# useful wellhead temperatures for district heating.
# At 35 °C/km + 11 °C surface → 105 °C outlet requires roughly 2700 m
# (accounting for heat loss along the vertical production section of the AGS loop).
# Extended 2026-07-15 from 6500 m up to 8000 m, same 500 m step.
WELL_DEPTHS_M: list[float] = [2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500, 7000, 7500, 8000]

# Mass flow rates in kg/s. Extended 2026-07-15 down to 3.5 kg/s (below the
# original 5 kg/s floor), same interval as the existing 5->10 step scaled down.
# OPEN QUESTION (not resolved 2026-07-27, needs Chad's judgment, not a code
# fix): the comment this replaces asked for "much smaller increments and a
# much lower max." Investigation didn't turn up a documented physical basis
# for the current values (they look like a round-number placeholder grid, not
# a range derived from Triemli's actual pump/piping capacity) — changing them
# requires a real-world flow-rate ceiling for this site, which isn't
# something to guess at from the code. Left unchanged pending that input.
MASS_FLOW_RATES_KG_S: list[float] = [3.5, 5, 7.5, 10, 12.5, 15, 20, 25, 30, 35, 40]

# Horizontal loop length in m. Previously held fixed at 2500 m with no
# justification beyond "keep the sweep 2-D"; swept instead so a range of
# plausible lengths is covered by data rather than a single fixed assumption.
# Extended 2026-07-15 from 2500 m up to 3500 m, same 500 m step.
# Extended again 2026-07-27 from 3500 m up to 8000 m (8 km), same 500 m step,
# matching WELL_DEPTHS_M's max — re-run the sweep with --regenerate to pick
# up the new grid. Also dropped 707 m (Chad's call, 2026-07-27: poor
# provenance as a "legacy value" — see the note above this constant for why
# it was originally included); 1000 m is now the floor.
# TODO: ask for review from Aline
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

# Horizontal loop diameter in m. Same story as loop length: previously fixed
# at 0.311 m (~12-inch casing) with no reconciliation against the web app's
# validated AGS_H2O reference (0.41 m — see
# examples/AGS_new/AGS_H2O_webapp_native.yml). Both are real anchor points,
# so both are included rather than picking one; 0.2 m and 0.5 m bracket the
# range below/above them.
# Extended 2026-07-15 from 0.5 m up to 0.75 m, same ~0.1 m step.
LOOP_DIAMETERS_M: list[float] = [0.2, 0.311, 0.41, 0.5, 0.6, 0.75]


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
