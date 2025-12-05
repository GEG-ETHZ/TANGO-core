"""Run flexible_SF_manual.py

This script was created for debuggging but also serves as an example of how to run Tango via script
"""

from pathlib import Path

from tango.runner import Runner

runner_base = Runner(input_file=str(Path(__file__).parent / "flexible_SF_manual.yml"))
runner = runner_base.clone()
runner.start()
lcoe = runner.tango.workflow.economic._results["LCOE"]

runner2 = runner_base.clone()
# Modify specs directly and update parameters (regenerate run ID)
runner2.tango.specs["injection_well"]["diameter"] *= 1.1
runner2.update_parameters()
runner2.start()
lcoe2 = runner2.tango.workflow.economic._results["LCOE"]

assert lcoe != lcoe2
