"""Orchestrators for tango.

Auto-selection rule (applied by Workflow) — a topology question, not a
duplicate of InjectionPolicy:
  sim_config.injection_mode present  →  SystemBCIteration (subclasses SystemDirect)
  sim_config.injection_mode absent   →  SystemDirect

InjectionPolicy (manual / manual-fracking-check / auto-pressure / auto-flow /
auto-both) governs how many circuit passes SystemBCIteration runs per
timestep — it does not affect which orchestrator class is chosen.
"""

from tango.orchestrators.system_bc_iteration import SystemBCIteration
from tango.orchestrators.system_direct import SystemDirect

__all__ = ["SystemBCIteration", "SystemDirect"]
