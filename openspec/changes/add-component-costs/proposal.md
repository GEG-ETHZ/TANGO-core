# Proposal

## Why

All costing happens in one place, `DoubletEconomicComponent` (`components/economic/doublet.py`), which runs once after the last step and reads other components' internals: `GraphSurface`'s TESPy node configs (`type`, `Subtype`, `set_number`, `design`, `cooling_tower_mode`) and node history, and the wells through `well_sections()`. Every new kind of component, or new cost, has to be taught to that one class (#17):

- A surface that is not a TESPy network gets a plant CAPEX of 0 with no error. The reversible ORC / heat-pump coupling (`add-revorc-coupling`) is the first such surface, and it needs its plant costed per module.
- Costs waiting on this structure: stimulation and re-stimulation (#93, which needs a periodic cost), startup pumps (#84), makeup working fluid (#62), every turbine with its fluid factor (#99), multi-segment well CAPEX (`docs/tango_tasks.md`).
- Sizing equipment on something other than the run average (#78, #55), and costing two products (#96), are questions about how each component's costs are sized and combined, which the current single reader makes hard to answer per component.

The roadmap (`docs/TANGO_vision_and_roadmap/README.md`, "Object-oriented per-component economics") recorded the decision to keep the central component for now, while narrower fixes landed. The RevORC coupling for FlexGEO MS4.2 (January 2027) is the case that now needs a second surface type costed, so this change revisits that decision for the part that is needed: components report their own costs; financing stays central.

## What Changes

- Every flow component reports its own cost items through one method, `cost_items(basis)`, returning a list of `CostItem`s (name, category, CAPEX, fixed annual O&M, parasitic power). A component with no costs returns an empty list explicitly; the base class raises `NotImplementedError`, so no component is costed as zero by omission.
- Move each existing cost formula, unchanged, into the component that owns the equipment: drilling quantities into the wells and grouped subsurface; turbine, pump, cooler and condenser costs and the cooling parasitic power into `GraphSurface`; the surface pipe into the surface.
- Drilling is reported as quantities (length, diameter, role, asset group) and priced per asset group by one drilling cost model, because the cost is nonlinear in total length and split wells (`production_well_lower`/`upper`) are drilled as one.
- The economic component keeps project-level costs (permitting, exploration), financing (CRF, O&M fraction, capacity factor), `MainProduct` and the levelized costs, and sums what the components report.
- The economic component receives the components and the project lifetime as arguments to `solve`, instead of the orchestrator and `Workflow` setting its private attributes.
- Add unit tests that pin every cost formula before it moves.
- **No change in results**: every template's LCOE golden, every `EconomicState` field and the `.econ.csv` output stay the same.

### Non-goals

- Fixing the cost gaps found while mapping the code (uncosted `PumpOrValve` nodes and ORC heat exchangers, the uncounted injection pump, the water-only turbine factor, the CO2 open-tower `KeyError`). They are recorded in `.agent/FINDINGS.md` and their issues (#99 and others); fixing them changes results and belongs in their own changes.
- Sizing on anything other than the run average (#78, #55). The interface takes a sizing basis so those changes have one place to add it.
- Periodic or scheduled costs and a year-by-year cash flow (#93). Each cost will be discounted in its own year (design D8); because that also changes how energy is discounted, and so every LCOE, it is its own change.
- Costing two products (#96).
- New cost items (#62, #84, #93).

## Capabilities

### New Capabilities

- `component-costs`: each component reporting its own cost items, and the economic component combining them with project-level costs into CAPEX, O&M and levelized cost.

### Modified Capabilities

None. No specs exist yet in `openspec/specs/`.

## Impact

- `core/`: `CostItem`, `CostCategory` (`StrEnum`), `SizingBasis` (`StrEnum`, `AVERAGE` only for now), `DrillingQuantity`; `FlowComponent.cost_items` raising `NotImplementedError`.
- `components/well/`, `grouped_subsurface.py`: drilling quantities, replacing `well_sections()` as the economics' view (`HasWellSections` stays for its other uses, or is folded in; see `design.md`).
- `components/surface/graph.py`: plant cost items and cooling parasitic power, taking over `_compute_surface_plant_capex`, the cooler and condenser code and the BAC coefficients from `doublet.py`.
- `components/reservoir/`: explicit empty cost list.
- `components/economic/`: `doublet.py` reduced to project-level costs, drilling pricing, financing and levelized cost; `base.py` `solve(components, lifetime)`.
- `orchestrators/system_direct.py` `finalize()`, `workflows/workflow.py`: pass components and lifetime instead of setting private attributes.
- New unit tests per cost formula; `tests/regtest/test_templates.py` goldens unchanged.
- `docs/components/economics.md`, `docs/architecture/components.md`, `src/tango_core/README.md` ("costing each component inside the component itself is not implemented"), `src/tango_core/components/README.md`, the roadmap note, `CHANGELOG.md`.
- Builds on #149 (circuit API) and #150 (time-weighted means, `time_history`). Whichever lands first, this change follows its interface.
