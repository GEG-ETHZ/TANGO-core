from __future__ import annotations

import argparse
import cProfile
import pstats
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — allow running from anywhere in the repo
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from tango_core.workflows.workflow import Workflow  # noqa: E402

# Configs live in templates/ (YAML only — shared with the regtests
# and `just apps`), not alongside application scripts.
DEFAULT_CONFIG = _REPO_ROOT / "templates" / "hydro_sf_electric_5spot.yml"
_RESULTS_DIR = _REPO_ROOT / "results"


parser = argparse.ArgumentParser(prog="run_tango_profile")
parser.add_argument("--profile", action="store_true", help="Enable cProfile")
args = parser.parse_args()

if args.profile:
    print("Running and Profiling ...")
    profiler = cProfile.Profile()

    # create a results folder for saving profiling data for visualization/analysis
    Path(_RESULTS_DIR).mkdir(exist_ok=True)

    profiler.enable()
else:
    print("Running ...")

print(DEFAULT_CONFIG)

wf = Workflow.from_file(DEFAULT_CONFIG)
wf.run()

if args.profile:
    profiler.disable()
    stats = pstats.Stats(profiler).sort_stats("cumtime")
    stats.print_stats()

    results_path = _RESULTS_DIR / "profile_results.prof"

    stats.dump_stats(results_path)
