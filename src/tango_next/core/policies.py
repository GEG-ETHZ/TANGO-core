"""Injection control policies for tango_next BC iteration."""

from __future__ import annotations

import enum


class InjectionPolicy(enum.StrEnum):
    """Governs how injection wellhead pressure and mass flow rate are determined.

    Geothermal reservoirs can be damaged by hydraulic fracturing via two
    independent mechanisms:

    1. **Flow-induced fracing** — mass flow rate high enough that the Darcy-law
       pressure drop drives the reservoir inlet above the fracing threshold:

       ``fracing_flow = 2πhk · ΔP_allowed / (μ · ln(re/rw))``

       where ``ΔP_allowed = hydrostatic_P × overpressure% / 100``.

    2. **Pressure-induced fracing** — injection wellhead pressure high enough
       that, after hydrostatic head and friction losses in the injection well,
       ``inj_well.outlet.P`` exceeds ``hydrostatic_P × (1 + overpressure%/100)``.

    Each policy variant specifies whether mass flow rate and wellhead pressure
    are user-prescribed or solver-iterated, and what happens when a fracing
    threshold would be exceeded.

    The policy is scoped to *injection control*, not just fracing prevention.
    Future variants may optimise net power, LCOE, or other operating objectives
    subject to fracing constraints, without requiring a different solver mechanism.
    For example, a ``MAX_NET_POWER`` variant could iterate mass flow rate and
    injection pressure jointly to maximise ``gross_power - pump_parasitic_load``,
    stopping at the fracing limit only if it would otherwise be exceeded.

    **YAML field:** ``schedule.bc_iteration.mode`` (kebab-case string, e.g.
    ``mode: auto-pressure``).

    **Single-pass vs. iterative:** ``MANUAL`` and ``MANUAL_FRACING_CHECK`` execute
    one circuit pass per timestep and return.  ``AUTO_*`` variants drive an outer
    Newton-step convergence loop.  See ``SystemBCIteration.run_timestep`` and the
    BC Iteration Solver diagram in ``docs/diagrams/src/``.

    **src/tango/ mapping (approximate):**

    ============================================  ======================
    src/tango/ config                             InjectionPolicy
    ============================================  ======================
    ``type: manual, check_fracing: False``        ``MANUAL``
    ``type: manual, check_fracing: True``         ``MANUAL_FRACING_CHECK``
    ``type: automatic`` (standard non-Hotmaps)    ``AUTO_BOTH``
    ============================================  ======================

    In HotmapsDispatch mode, ``type: automatic`` has more complex behaviour
    (early timesteps use a specified rate with optional fracing cap; later
    timesteps may iterate to a target thermal power output).  That is a
    distinct operating mode not yet represented in this enum.
    """

    def __new__(cls, value: str, doc: str = "") -> InjectionPolicy:
        """Construct an enum member with an optional per-member docstring."""
        member = str.__new__(cls, value)
        member._value_ = value
        if doc:
            member.__doc__ = doc
        return member

    MANUAL = (
        "manual",
        "Both mass flow rate and injection wellhead pressure are user-specified. "
        "No fracing check is performed. Single solver pass per timestep.",
    )
    MANUAL_FRACING_CHECK = (
        "manual-fracing-check",
        "Both user-specified. Both fracing directions checked; any violation raises "
        "an error. Pressure reduced if initial value causes pressure-induced fracing; "
        "rate capped if it causes flow-induced fracing. Single solver pass per timestep.",
    )
    AUTO_PRESSURE = (
        "auto-pressure",
        "Mass flow rate user-specified. Injection wellhead pressure iterated via "
        "Newton step (test_p += target_reservoir_P - inj_well.outlet.P) until "
        "reservoir inlet converges to the fracing threshold. "
        "Flow-induced fracing raises an error.",
    )
    AUTO_FLOW = (
        "auto-flow",
        "Injection wellhead pressure user-specified. Mass flow rate iterated to "
        "fracing_flow() each pass; co-evolves with pressure until both stabilize. "
        "Pressure-induced fracing raises an error.",
    )
    AUTO_BOTH = (
        "auto-both",
        "Both iterated simultaneously. If no feasible injection pressure exists at "
        "the target flow rate, the flow rate is reduced until a feasible pressure "
        "can be achieved. Most robust mode for high-flow or low-permeability reservoirs.",
    )
