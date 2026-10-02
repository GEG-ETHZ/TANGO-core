"""Injection control policies for tango BC iteration."""

from __future__ import annotations

import enum


class InjectionPolicy(enum.StrEnum):
    """Governs how injection wellhead pressure and mass flow rate are determined.

    Geothermal reservoirs can be damaged by hydraulic fracturing via two
    independent mechanisms:

    1. **Flow-induced fracking** — mass flow rate high enough that the Darcy-law
       pressure drop drives the reservoir inlet above the fracking threshold:

       ``fracking_flow = 2πhk · ΔP_allowed / (μ · ln(re/rw))``

       where ``ΔP_allowed = hydrostatic_P × overpressure% / 100``.

    2. **Pressure-induced fracking** — injection wellhead pressure high enough
       that, after hydrostatic head and friction losses in the injection well,
       ``inj_well.outlet.P`` exceeds ``hydrostatic_P × (1 + overpressure%/100)``.

    Each policy variant specifies whether mass flow rate and wellhead pressure
    are user-prescribed or solver-iterated, and what happens when a fracking
    threshold would be exceeded.

    The policy is scoped to *injection control*, not just fracking prevention.
    A per-timestep ``MAX_NET_POWER`` variant fits the same per-timestep Newton-step
    mechanism as ``AUTO_*`` above: iterate mass flow rate and injection pressure
    jointly to maximise ``gross_power - pump_parasitic_load`` *at this timestep*,
    stopping at the fracking limit only if it would otherwise be exceeded.

    A whole-horizon objective like ``MIN_LCOE`` is a different shape of problem and
    likely needs a different solver mechanism: LCOE depends on cumulative energy
    output and cost across every timestep, not on any single timestep in isolation,
    so minimising it means wrapping the *entire* multi-timestep run in an outer
    constrained optimizer (closer to the whole-run ``pymoo``-based search the
    ``opt_*`` applications already use — see ``applications/opt_hydro_sf_electric/``
    — than to this enum's per-timestep Newton loop) — see vision doc §BC iteration mode
    for the "Future direction — whole-horizon optimization" note. Do not assume every
    future variant fits inside ``SystemBCIteration.run_timestep`` the way ``AUTO_*``
    does; per-timestep and whole-horizon objectives should be distinguished, not
    folded into one enum that implies a single solver shape.

    **YAML field:** ``sim_config.injection_mode`` (kebab-case string, e.g.
    ``injection_mode: auto-pressure``).

    **Single-pass vs. iterative:** ``MANUAL`` and ``MANUAL_FRACKING_CHECK`` execute
    one circuit pass per timestep and return.  ``AUTO_*`` variants drive an outer
    Newton-step convergence loop.  See ``SystemBCIteration.run_timestep`` and the
    BC Iteration Solver diagram in ``dev_docs/diagrams/src/``.
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
        "No fracking check is performed. Single solver pass per timestep.",
    )
    MANUAL_FRACKING_CHECK = (
        "manual-fracking-check",
        "Both mass flow rate and injection wellhead pressure are user-specified. "
        "Single solver pass per timestep, same as MANUAL — then both fracking "
        "directions are checked against the solved result. Any violation raises "
        "FrackingViolationError; neither the pressure nor the rate is "
        "pre-emptively corrected or re-solved.",
    )
    AUTO_PRESSURE = (
        "auto-pressure",
        "Mass flow rate user-specified. Injection wellhead pressure "
        "(p_inj_wellhead_no_frack) iterated via Newton step "
        "(p_inj_wellhead_no_frack += target_reservoir_P - inj_well.outlet.P) "
        "until reservoir inlet converges to the fracking threshold. "
        "Flow-induced fracking raises an error.",
    )
    AUTO_FLOW = (
        "auto-flow",
        "Injection wellhead pressure user-specified. Mass flow rate iterated to "
        "fracking_flow() each pass; co-evolves with pressure until both stabilize. "
        "Pressure-induced fracking raises an error.",
    )
    AUTO_BOTH = (
        "auto-both",
        "Placeholder for iterating both flow rate and pressure simultaneously. "
        "Because this is currently not implemented, raises NotImplementedError "
        "from SystemBCIteration.run_timestep — see examples in applications/ "
        "demonstrating how to find a good (mass_rate, injection_pressure) "
        "operating point via pymoo instead (applications/"
        "opt_hydro_df_electric/, applications/opt_hydro_sf_electric/), "
        "with fracking-avoidance enforced as a search constraint rather than an "
        "in-simulation auto-adjustment loop (dev_docs/tango_tasks.md's backlog "
        "entry has the full writeup on why this was punted).",
    )


class MainProduct(enum.StrEnum):
    r"""Which output an ``EconomicComponent`` treats as the plant's primary product.

    Determines the denominator in the levelized-cost calculation: net
    electric power for ``ELECTRICITY`` (LCOE), net thermal power for
    ``HEAT`` (LCOH). Both use the same formula —
    ``CAPEX * (CRF + F_OM) / (product_power * W_TO_KW * CF * YEAR_TO_HOUR)``
    — only the power term differs, so this does not need a second enum
    per formula, just a branch on which surface-component output to sum.

    **YAML field:** ``economic.main_product`` (e.g. ``main_product: heat``).

    A real enum rather than a raw string comparison, to avoid the
    silent-failure modes a stringly-typed field invites — see
    ``dev_docs/bugs-fixed-in-tango.md``'s "``== \"yes\"`` string-comparison
    trap" section for an example of that failure mode.
    """

    ELECTRICITY = "electricity"
    HEAT = "heat"


class ProjectMaturity(enum.StrEnum):
    """Whether a geothermal project's wells already exist (``BROWN_FIELD``)
    or must still be drilled/permitted/explored (``GREEN_FIELD``).

    ``GREEN_FIELD`` includes injection-well, permitting, and exploration
    CAPEX; ``BROWN_FIELD`` zeroes all three (existing infrastructure reused,
    only production wells/surface plant/pipes are new spend) — a real
    ~30%+ swing on total CAPEX, not a cosmetic distinction.

    **YAML field:** ``economic.project_maturity``.

    A real enum for the same reason as ``MainProduct``, above.
    """

    GREEN_FIELD = "green_field"
    BROWN_FIELD = "brown_field"


class ComponentRole(enum.StrEnum):
    """Tags a graph-surface TESPy node's output for aggregation into plant totals.

    Deliberately explicit per-node rather than inferred from TESPy component
    type: a ``SimpleHeatExchanger`` might be a condenser you reject heat
    through (not a product) or a district-heating exchanger whose output
    *is* the product — inferring from type alone would silently misclassify
    one of them. A node with no role is still solved as part of the network,
    just not summed into either total.

    ``solve()`` sums ``-P.val`` (uniformly negated, no per-type branch) over
    ``NET_ELECTRIC`` nodes and ``-Q.val`` over ``NET_THERMAL`` nodes, writing
    ``state.net_power_W``/``state.net_thermal_W``. The uniform negation
    happens to land on the physically correct sign for every node type
    without a branch, because TESPy's own raw sign convention already
    differs by type — confirmed empirically (``hydro_df_electric.yml``'s
    topology): ``Turbine.P.val`` is negative (generates/removes energy),
    ``Compressor.P.val`` is positive (consumes/adds energy) — so negating
    both makes a turbine add to net power and a pump subtract from it, with
    no ``isinstance`` check needed. Do not assume this sign is a stable
    physical constant if porting a cost or power formula from elsewhere
    that reads raw ``P.val`` directly — it's a wiring-convention artifact
    of how each TESPy network happens to be built, not a TESPy-wide
    guarantee; verify the sign for the specific network being ported
    rather than assuming it matches. ``EconomicComponent.main_product``
    (see ``MainProduct`` above) picks which of the two totals feeds LCOE/LCOH.

    **YAML field:** ``power_plant.nodes.<name>.role`` (optional; omit for
    internal-only components like valves, separators, condensers).
    """

    NET_ELECTRIC = "net_electric"
    NET_THERMAL = "net_thermal"
