"""Orchestrators for tango_next.

Auto-selection rule (applied by Workflow):
  schedule.bc_iteration present  →  SystemBCIteration
  schedule.bc_iteration absent   →  SystemDirect
"""

from tango_next.orchestrators.system_bc_iteration import SystemBCIteration
from tango_next.orchestrators.system_direct import SystemDirect

__all__ = ["SystemBCIteration", "SystemDirect"]
