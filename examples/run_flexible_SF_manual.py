"""Run flexible_SF_manual.py

This script was created for debuggging but also serves as an example of how to run Tango via script
"""

from pathlib import Path

from tango.runner import Runner

runner = Runner(input_file=str(Path(__file__).parent / "flexible_SF_manual.yml"))
runner.start()
