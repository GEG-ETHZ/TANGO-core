"""Mesh-convergence proof-of-work for ``NumericalWell``'s cell resolution.

Documents *why* ``TARGET_CELL_LENGTH_M`` (see that constant's docstring in
``src/tango/components/well/numerical.py``) is 250 m: runs
``example_configs/hydro_sf_electric.yml`` end to end with ``num_cells``
overridden uniformly across all three numerical wells (injection_well,
production_well_lower, production_well_upper), and compares the delivered
production temperature (``surface.history.T_inlet``, in Kelvin) at every
timestep against a ``num_cells=100`` baseline, on the 5000 m injection_well
(the longest of the three, so the one with the coarsest cell_length at any
given num_cells).

Result: ``num_cells=15`` is the smallest value keeping max relative error
under the 0.1% target at every timestep (0.0964% at 15 vs. 0.1569% at 10).
Rounded up to the nearest 10 -> **20** cells on the 5000 m well, i.e. a
target cell_length of ``5000 / 20 = 250`` m. ``NumericalWell`` now derives
``num_cells`` from that same target cell_length for every well (unless a
config sets ``num_cells`` explicitly, as this script does below), so a
well shorter than 5000 m automatically gets fewer cells at the same
resolution rather than inheriting a flat 20.

Run from the repo root::

    uv run python applications/demo_well_mesh_convergence/demo_well_mesh_convergence.py

Exits non-zero (and is wired into ``just apps``) if a future physics
change ever pushes num_cells=20's error back over the 0.1% target — that's
a signal this study needs re-running and TARGET_CELL_LENGTH_M's docstring
updated to match, not that this script itself needs editing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from tango.workflows.workflow import Workflow  # noqa: E402

CONFIG = _REPO_ROOT / "example_configs" / "hydro_sf_electric.yml"
WELL_COMPONENTS = ("injection_well", "production_well_lower", "production_well_upper")

BASELINE_NUM_CELLS = 100
CHOSEN_NUM_CELLS = (
    20  # must match numerical.TARGET_CELL_LENGTH_M's derivation on this well (5000 m / 250 m = 20)
)
TOL_REL = 0.001  # 0.1%


def run_with_num_cells(num_cells: int) -> list[float]:
    """Run ``hydro_sf_electric.yml`` with ``num_cells`` overridden on all three wells.

    Returns the per-timestep production temperature (K) delivered to the
    surface (``surface.history.T_inlet``).
    """
    config = yaml.safe_load(CONFIG.read_text())
    for name in WELL_COMPONENTS:
        config["components"][name]["num_cells"] = num_cells

    wf = Workflow.from_str(yaml.safe_dump(config))
    wf.run()

    surface = wf._orchestrator._find_surface()  # noqa: SLF001
    return list(surface.history.T_inlet)


def max_rel_err(candidate: list[float], baseline: list[float]) -> float:
    """Max relative error between two same-length per-timestep series."""
    return max(abs(c - b) / b for c, b in zip(candidate, baseline, strict=True))


def main() -> None:
    """Run the baseline and chosen num_cells, and fail if error exceeds the target."""
    import logging  # noqa: PLC0415

    logging.disable(logging.WARNING)

    print(f"Running baseline (num_cells={BASELINE_NUM_CELLS})...")
    baseline = run_with_num_cells(BASELINE_NUM_CELLS)

    print(f"Running chosen value (num_cells={CHOSEN_NUM_CELLS})...")
    chosen = run_with_num_cells(CHOSEN_NUM_CELLS)
    err = max_rel_err(chosen, baseline)

    print(f"max relative error @ num_cells={CHOSEN_NUM_CELLS}: {err:.6f} (tol {TOL_REL:.4f})")

    if err > TOL_REL:
        print(
            f"FAIL: num_cells={CHOSEN_NUM_CELLS} drifted past the {TOL_REL:.2%} target "
            f"(now {err:.4%}) — re-run this study's exploratory sweep and update "
            "NumericalWell.num_cells's default plus every tango example config.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("OK")


if __name__ == "__main__":
    main()
