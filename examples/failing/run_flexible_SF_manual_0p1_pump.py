"""Run flexible_SF_manual_narrow_pump.yml

This script was created for debugging but also serves as an example of how to run Tango via script
"""

from pathlib import Path

from tango.runner import Runner

runner = Runner(input_file=str(Path(__file__).parent / "flexible_SF_manual_0p1_pump.yml"))
runner.start()

