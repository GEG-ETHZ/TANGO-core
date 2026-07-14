"""
Currently the .yaml input file can take ``surface_temperature`` and ``surface_pressure`` as a parameter in the ``common:`` section and in the ``components: surface: `` section.

When the two sets of parameters differ
e.g.:
``
common:
    surface_temp = 300 K
    surface_pressure = 110_000 Pa
    ...

components:
    surface:
        surface_temp = 288K
        surface_pressure = 100_000 Pa
        ...
``

The surface component will use the surface temp and pressure defined for the surface but all other components will use the surface temp and pressure defined in common.

"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest

import pprint

# ---------------------------------------------------------------------------
# Path setup — allow running from anywhere in the repo
# ---------------------------------------------------------------------------


from tango_next.workflows.workflow import Workflow  # noqa: E402

YAML_PATH = Path(__file__).parent.parent / "examples" / "SF_manual_differing_stp.yml"
SAVE_DIR = Path(__file__).parent.parent

def run_simulation() -> Workflow:
    """Load and run the flexible Single-Flash YAML config; return the completed Workflow."""
    wf = Workflow.from_file(YAML_PATH)
    wf.run()
    print("Simulation complete.")
    return wf

def extract_stp_data(wf: Workflow) -> dict:
    """Pull per-timestep state from all components after a completed run.

    Returns a flat dict of numpy arrays ready for plotting.
    """
    # _orchestrator.components is a dict keyed by the component names defined
    # in the YAML.  We unpack into locals here so the plotting code below reads
    # as plain names rather than repeated dict lookups.
    c = wf._orchestrator.components

    surface_components = {"surface", "injection_well", "production_well_upper", "production_well"}

    stp = dict()

    for component in surface_components:
        if component in c:
            print(component)
            stp[component]['surface_temperature'] = c[component].surface_temperature
            stp[component]['surface_pressure'] = c[component].surface_pressure

    return stp
        

def test_stp():
    """Run the simluation on the given file and assert that surface temp is equal accross all components"""

    wf = run_simulation()

    c = wf._orchestrator.components

    print(f"Surface surface temp: {c['surface'].surface_temperature} \n Production well surface temp: {c['production_well_upper'].surface_temperature}")
    print(f"\n\n Surface surface pressure: {c['surface'].surface_pressure}")

    assert c['surface'].surface_temperature == c['production_well_upper'].surface_temperature

if __name__ == "__main__":
    test_stp() 

