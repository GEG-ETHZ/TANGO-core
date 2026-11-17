# Design

## Context

See `proposal.md` for the motivation. The current state that shapes the approach:

- `DoubletEconomicComponent` (`components/economic/doublet.py`) is the only concrete economic class. It is a plain `Component`, built from the config's `economic` block, outside the circuit. `SystemDirect.finalize()` sets its `_components`, `Workflow` sets its `_total_years`, and it runs `solve()` once after the last step.
- What it reads:

| Cost | Read from | Sized on |
|---|---|---|
| Drilling | `well_sections()`: role, length, diameter | geometry |
| Production pump parasitic | `well_sections()` pump power history | run mean |
| Surface pipe | `surface.well_spacing`, `pipe_diameter` | geometry |
| Turbine, injection pump, cooler/condenser | `GraphSurface.power_plant["nodes"]` keys and `history.node_history` | run mean |
| Cooling parasitic power | same | run mean |
| Net electric and thermal power | `surface.history.net_power_W`, `net_thermal_W` | run mean |
| Permitting, exploration | `project_maturity` only | constant |

- Drilling: injection and horizontal sections are costed one by one; all vertical production sections are summed into one length and costed once, so a split production well pays one mobilization. The formula is quadratic in length.
- Financing: CRF on the project lifetime, O&M as a fraction of CAPEX less by-product revenue, one capacity factor, `MainProduct` choosing LCOE or LCOH. No per-year cash flow.
- No unit test covers a cost formula. All 19 templates' LCOE values are pinned at `rel=1e-6` in `tests/regtest/test_templates.py`. `EconomicState` is the declared exception to State/History parity.
- `HasWellSections` (`components/well/base.py`) is already a per-component view for the economics: the seed of this change.
- #150 makes every run mean time-weighted and gives every component a `time_history`; `finalize()` is otherwise unchanged.
- CONTRIBUTING's commandments that bind the design: no silent base methods, encapsulated mutation (today's `finalize()` and `workflow.py` break it), unit suffixes, `StrEnum` for finite variants, goldens changed only from checked runs.

## Goals / Non-Goals

**Goals:**

- A new component type is costed by implementing one method on that component, without editing the economic component.
- Costing is explicit: a component without costs says so; nothing is costed as zero because a reader did not recognise it.
- Results do not change. The refactor is proven by the existing goldens plus new unit tests per formula.

**Non-Goals:**

- See `proposal.md`.

## Decisions

### D1: One method, `cost_items(basis)`, on every flow component

`FlowComponent.cost_items(basis: SizingBasis) -> list[CostItem]`. The base raises `NotImplementedError`. A component with no costs (reservoirs) returns `[]`.

`CostItem` is a frozen dataclass:

| Field | Meaning |
|---|---|
| `name` | e.g. `"turbine:T1"`, unique within the component |
| `category` | `CostCategory`: `DRILLING`, `SURFACE_PLANT`, `SURFACE_PIPE`, ... (maps to today's `EconomicState` CAPEX fields) |
| `capex_usd` | installed capital cost |
| `fixed_om_usd_per_year` | 0 today; for items with their own O&M later (#62) |
| `parasitic_power_W` | electric power the item draws (cooling fans, production pumps), subtracted from net power |

Costs are computed after the run from the component's own history, so `cost_items` is a read-only method, not part of the solve. It is not stored in `state`.

Alternative considered: a cost component per equipment item in the circuit. Rejected: equipment inside a TESPy network is not a TANGO component, and the circuit graph is for flow.

### D2: Drilling is reported as quantities and priced per asset group

Wells and the grouped subsurface report `DrillingQuantity(role, length_m, diameter_m, asset_group)` through a second method, `drilling_quantities()`, instead of a cost. The economic component prices them with the existing formula, one call per asset group, so lengths in one group are summed before the quadratic is applied.

`asset_group` defaults to today's rule (all vertical production sections in one group; each injection and horizontal section on its own), so results do not change. A config can name groups explicitly later; this change does not add that.

Alternative considered: each well costs itself. Rejected for now: a split production well would pay two mobilizations, which changes every split-well template's LCOE. This is the roadmap's "asset group" question; quantities plus groups answer it without a new component type.

### D3: The economic component keeps what belongs to the project

Permitting, exploration, the drilling price model (D2), CRF, the O&M fraction, the capacity factor, `MainProduct` and the levelized costs stay in the economic component. It sums `capex_usd` by category into today's `EconomicState` fields, and sums `parasitic_power_W` into net power as today.

### D4: Sizing basis is passed in, average only

`SizingBasis` is a `StrEnum` with one member, `AVERAGE` (time-weighted with #150, today's behaviour). The economic component passes it to every `cost_items` call. #78 and #55 add members and decide where the choice is configured; components then size from their own history for the requested basis.

### D5: The economic component gets its inputs as arguments

`EconomicComponent.solve(components, lifetime_s)`, called by `finalize()`. The private `_components` and `_total_years` and their assignment from outside go away.

### D6: Pin the formulas before moving them

Before any code moves, add unit tests that call each current cost function with fixed inputs and pin its output (drilling per role, permitting, exploration, pipe, turbine, pump, cooler/condenser grouping, parasitic power, CRF and LCOE). They must pass unchanged after every step, together with the template goldens.

### D7: Gaps are recorded, not fixed

The gaps found while mapping the code (uncosted `PumpOrValve` and ORC heat exchangers, the uncounted injection pump, the water-only turbine factor, the CO2 open-tower `KeyError`, means over sub-sampled records when `save_interval > 1`, a silent plant CAPEX of 0 when `record_node_detail` is off) go to `.agent/FINDINGS.md` and their issues. Each moved formula keeps its current behaviour. The one exception is the silent zero: a `GraphSurface` asked for cost items with `record_node_detail` off raises a `ConfigError`, because the new interface must not hide a missing input. That changes no golden (every template records node detail); confirm in task 1.2.

### D8: Each cost is discounted in its own year

Decided 2026-11-17. A cost that falls at a given time (a periodic re-stimulation, #93; a replacement) is discounted at that time, not converted to an equivalent annual cost. `CostItem` gets a schedule of dated costs when the first periodic item is added; this change adds no periodic items, so it adds no schedule field yet.

Discounting each year's cost consistently means discounting each year's energy too: LCOE becomes the discounted sum of costs over the discounted sum of energy, year by year. For a constant yearly energy and O&M this equals today's annuity formula, `CAPEX (CRF + f_om) / E`; with energy that changes from year to year (every TANGO run) it does not, so it changes every template's LCOE. That year-by-year cash flow is therefore its own change, with its own regression update, before or together with #93. This change keeps today's annuity.

### D9: No separate cost export

Decided 2026-11-17. Per-item costs are not exported as a new table. `.econ.csv` exists only for legacy reasons; the YAML output (`Workflow.to_dict()`) is the complete record of a run.

## Risks / Trade-offs

- **A large diff for no change in numbers.** Mitigation: D6's pinned tests, then one commit per moved formula, each with both test sets green.
- **Two interfaces for wells** (`cost_items` and `drilling_quantities`). Accepted: drilling is the one cost that is nonlinear across components.
- **Conflict with #150**, which edits the same averaging code. Mitigation: land after #150, or rebase onto it before task 2.

## Open Questions

1. Land after #150? Recommended, since both edit the averaging code.
2. Resolved: each cost is discounted in its own year (D8).
3. Replace `well_sections()`? Each well component, `NumericalGroupedSubsurface` and `RaftGroupedSubsurface` implement `well_sections()` (the `HasWellSections` protocol in `components/well/base.py`). It returns one `WellSection` per drilled section: its role (injection, horizontal or production, today decided by `component_idx == 0` and the inclination), length, inner diameter, and the history of downhole pump power. Its only users are the economic component and one unit test (`test_grouped_subsurface.py:189`). After this change both of its jobs have new homes: geometry in `drilling_quantities()` (D2) and pump power as a parasitic-power cost item (D1). Recommendation: remove `well_sections()`, `WellSection` and `HasWellSections` in task 3.2, and rewrite that test against `drilling_quantities()`.
4. Is the RevORC plant cost (`add-revorc-coupling` D8) the first user, landing together, or does it wait for this change? Not decided yet.
5. Resolved: no separate cost export (D9).
