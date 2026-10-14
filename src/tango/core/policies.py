"""Injection control policies for tango BC iteration."""

from __future__ import annotations

import enum


class InjectionPolicy(enum.StrEnum):
    """Whether each timestep is checked against the reservoir's fracking limit.

    The reservoir has one fracking limit: its pressure must stay below
    ``hydrostatic_P × (1 + overpressure%/100)``, i.e. at most
    ``ΔP_allowed = hydrostatic_P × overpressure% / 100`` above hydrostatic.
    ``MANUAL_FRACKING_CHECK`` tests that limit two ways, since either can
    exceed it:

    1. **Pressure** — the injection well's outlet pressure (wellhead pressure
       plus hydrostatic head minus friction) is above the limit.
    2. **Flow** — the mass rate is above the rate whose Darcy pressure rise
       across the reservoir equals ``ΔP_allowed``:

       ``fracking_flow = 2πhk · ΔP_allowed / (μ · ln(re/rw))``

    Mass flow rate and injection wellhead pressure are always taken from
    the config; the policy only decides whether the result is checked.

    **No automatic modes.** Earlier versions also had ``auto-pressure``,
    ``auto-flow`` and ``auto-both``, which iterated the injection pressure
    and/or flow rate toward a fracking threshold inside each timestep. They
    were removed in October 2026: a fracking-limited operating point is only
    one point of the real question (which pressure and flow give the best
    LCOE/power trade-off), the iteration proved brittle (``auto-pressure``
    could cycle without converging), and ``auto-both`` was never
    implemented. To find good operating points, run the multi-objective
    searches in ``applications/opt_*/``, which use ``manual-fracking-check``
    and treat a fracking violation as an infeasible design.

    **YAML field:** ``sim_config.injection_mode`` (kebab-case string, e.g.
    ``injection_mode: manual-fracking-check``).
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
        "Single solver pass per timestep, same as MANUAL — then the solved result is "
        "checked against the fracking limit, by pressure and by flow. A violation raises "
        "FrackingViolationError; neither the pressure nor the rate is "
        "pre-emptively corrected or re-solved.",
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
