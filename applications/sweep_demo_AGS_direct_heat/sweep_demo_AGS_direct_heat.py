"""Minimal parameter-sweep demo: dict-modify-then-reinstantiate pattern.

Demonstrates the pattern documented in ``Workflow``'s class docstring
(``src/tango/workflows/workflow.py``) — mutate a copy of
``Workflow.to_dict()``, then build a fresh ``Workflow`` from the modified
dict, rather than mutating a live object in place::

    cfg = base_wf.to_dict()
    cfg["common"]["rock_k"] = rock_k
    Workflow(cfg).run()

Sweeps ``common.rock_k`` (deliberately a ``common:`` field, not a
component-local one) across a small set of values for
``example_configs/AGS_direct_heat.yml``, and reports final-timestep
net thermal power for each. This is a minimal demo, not the full
generate/sweep/summarize/plot pipeline — see docs/tango_tasks.md
"IMMEDIATE NEXT" for the scope decision.

Run from the repo root::

    uv run python applications/sweep_demo_AGS_direct_heat/sweep_demo_AGS_direct_heat.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from tango.workflows.workflow import Workflow  # noqa: E402

# AGS_direct_heat.yml lives in example_configs/ (configs only) — not
# colocated with this script, unlike the old example_configs/ layout.
YAML_PATH = _REPO_ROOT / "example_configs" / "AGS_direct_heat.yml"

ROCK_K_SWEEP_W_PER_MK = [1.5, 2.1, 3.0, 4.0]


def main() -> None:
    """Sweep common.rock_k and report final net thermal power for each value."""
    base_wf = Workflow.from_file(YAML_PATH)

    print(f"{'rock_k (W/m/K)':>16}  {'final net_thermal_W':>22}")
    for rock_k in ROCK_K_SWEEP_W_PER_MK:
        cfg = base_wf.to_dict()
        cfg["common"]["rock_k"] = rock_k

        wf = Workflow(cfg)
        assert wf._orchestrator.components["injection_well"].common.rock_k == rock_k
        assert wf._orchestrator.components["horizontal_well"].common.rock_k == rock_k
        assert wf._orchestrator.components["production_well"].common.rock_k == rock_k

        wf.run()

        surface = wf._orchestrator.components["surface"]
        final_net_thermal_W = surface.history.net_thermal_W[-1]
        print(f"{rock_k:16.2f}  {final_net_thermal_W:22,.0f}")

    # base_wf itself was never mutated — to_dict() always returns a fresh
    # copy (see Workflow's class docstring).
    assert base_wf.to_dict()["common"]["rock_k"] == 2.1


if __name__ == "__main__":
    main()
