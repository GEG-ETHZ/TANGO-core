"""Run flexible_SF_manual_playground.yml

This script was created for debugging but also serves as an example of how to run Tango via script
"""

from pathlib import Path
from copy import copy
import logging

from tango.runner import Runner

runner = Runner(
    input_file=str(Path(__file__).parent / "flexible_SF_manual_playground.yml"),
)
runner.start()

console = logging.StreamHandler()
console.setLevel(logging.WARNING)

print("Baseline LCOE: 0.7740618821215702")
print(f"LCOE: {runner.tango.workflow.economic.get_results()['LCOE']}")
