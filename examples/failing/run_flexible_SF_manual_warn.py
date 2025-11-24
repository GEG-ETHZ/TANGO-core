"""Run flexible_SF_manual_warn.yml

This script was created for debugging but also serves as an example of how to run Tango via script
"""

from pathlib import Path

from tango.runner import Runner

runner = Runner(input_file=str(Path(__file__).parent / "flexible_SF_manual_warn.yml"))
runner.start()
