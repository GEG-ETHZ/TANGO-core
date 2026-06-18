"""Orchestrators for tango_next.

Auto-selection rule (applied by Workflow) — a topology question, not a
duplicate of InjectionPolicy:
  sim_config.bc_iteration present  →  SystemBCIteration (subclasses SystemDirect)
  sim_config.bc_iteration absent   →  SystemDirect

InjectionPolicy (manual / manual-fracing-check / auto-pressure / auto-flow /
auto-both) governs how many circuit passes SystemBCIteration runs per
timestep — it does not affect which orchestrator class is chosen.
"""

from tango_next.orchestrators.system_bc_iteration import SystemBCIteration
from tango_next.orchestrators.system_direct import SystemDirect

__all__ = ["SystemBCIteration", "SystemDirect"]
