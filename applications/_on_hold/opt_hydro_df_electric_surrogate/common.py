"""Shared plumbing for the hydro_df_electric surrogate pipeline scripts.

Every stage script (``generate_lhs.py``, ``sweep_lhs.py``, ``train_surrogate.py``,
``optimize_surrogate.py``, ``validate_surrogate.py``) reuses THIS system's own
decision variables, objectives, baseline, plots, and display renames from the
sibling ``opt_hydro_df_electric`` app's ``APP`` directly, rather than
redefining them here — see ``tango.surrogate_api``'s module docstring for why this whole pipeline stays generic about the system
it's optimizing (this ``common.py`` is the one place that's NOT generic; it's
this app's own glue).

``opt_hydro_df_electric`` is imported via ``sys.path`` (a real module import,
not ``importlib.util.spec_from_file_location`` registered under a synthetic
name) because ``sweep_lhs.py``'s ``multiprocessing`` ``spawn`` workers need to
unpickle this module's ``ParamSpec``/``ObjectiveSpec`` instances in a FRESH
interpreter, which requires ``import opt_hydro_df_electric`` to resolve there
too — confirmed the hard way in ``tests/unit/test_surrogate_api.py``, where a
file-loaded module stashed only under a synthetic ``sys.modules`` name hung
the spawned pool instead of raising.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from tango.pymoo_api import load_params

HERE = Path(__file__).parent
_OPT_APP_DIR = HERE.parents[1] / "opt_hydro_df_electric"
if str(_OPT_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_OPT_APP_DIR))

opt_app = importlib.import_module("opt_hydro_df_electric")

PARAMS_FILE = HERE / "params.yaml"
DEFAULT_OUTPUT_DIR = HERE / "outputs"
DEFAULT_LOG_LEVEL = "WARNING"

# The REAL opt_hydro_df_electric app's own params.yaml — optimize_surrogate.py
# defaults its NSGA2 hyperparameters (n_max_gen/pop_size/ftol/xtol/seed) from
# THIS file, not a second independently-typed copy, so a surrogate-driven run
# uses the identical GA configuration as the real-sim run it's meant to be
# timed against (the only difference left is real-sim vs. surrogate
# evaluation — see optimize_surrogate.py's own docstring).
OPT_APP_PARAMS_FILE = _OPT_APP_DIR / "params.yaml"


def opt_app_pymoo_params() -> dict:
    """The real app's own n_max_gen/pop_size/ftol/xtol/seed/etc., read fresh from its params.yaml."""
    return load_params(OPT_APP_PARAMS_FILE)


def param_specs():
    """Decision variables — see ``opt_hydro_df_electric.APP``."""
    return opt_app.APP.param_specs()


def objective_specs():
    """Objectives — see ``opt_hydro_df_electric.APP``."""
    return opt_app.APP.objective_specs


def base_config():
    """The template config dict every design starts from — see ``OptApp.base_config``."""
    return opt_app.APP.base_config()


def make_plots(df, save_dir, param_cols, objective_cols):
    """Every pareto plot — see ``OptApp.make_plots``.

    ``param_cols``/``objective_cols`` are accepted for the stage scripts'
    existing call sites; ``OptApp`` derives both from its own specs.
    """
    opt_app.APP.make_plots(df, save_dir)


DISPLAY_RENAME = opt_app.APP.display_rename
