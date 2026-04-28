"""Run flexible_SF_manual.py

This script was created for debuggging but also serves as an example of how to run Tango via script
"""

from pathlib import Path

from tango.runner import Runner

input_file = Path(__file__).parent / "flexible_SF_manual.yml"
runner_base = Runner(
    input_file=input_file,
    # save_dir=Path(__file__).parent / input_file.stem,
    no_save=True,
    log_level="NONE",
)
runner = runner_base.clone()
runner.start()
lcoe = runner.tango.workflow.economic._results["LCOE"]

runner2 = runner_base.clone()
# Modify specs directly and update parameters (regenerate run ID)
# 1.1 multiplier is an arbitrary choice for the purpose of demonstrating
# sensitivity
runner2.tango.specs["injection_well"]["diameter"] *= 1.1
runner2.update_parameters()
runner2.start()
lcoe2 = runner2.tango.workflow.economic._results["LCOE"]

assert lcoe != lcoe2
