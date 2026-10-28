"""Orchestrators for tango.

Auto-selection rule (applied by Workflow) — a topology question, not a
duplicate of InjectionPolicy:
  sim_config.injection_mode present  →  SystemBCIteration (subclasses SystemDirect)
  sim_config.injection_mode absent   →  SystemDirect

InjectionPolicy (manual / manual-fracking-check) decides whether
SystemBCIteration checks each timestep against the fracking limit — it
does not affect which orchestrator class is chosen.
"""

from tango_core.orchestrators.system_bc_iteration import SystemBCIteration
from tango_core.orchestrators.system_direct import SystemDirect

__all__ = ["SystemBCIteration", "SystemDirect"]
