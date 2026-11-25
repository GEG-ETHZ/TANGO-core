# Tasks

## 1. Pin today's behavior

- [ ] 1.1 Add unit tests that call each cost function in `doublet.py` with fixed inputs and pin its output: drilling per role, permitting, exploration, surface pipe, turbine, pump, cooler/condenser grouping, cooling parasitic power, production pump parasitic power, CRF, LCOE, specific investment cost, OPEX. Verify they pass on unchanged code.
- [ ] 1.2 Confirm every template records node detail, so D7's `ConfigError` changes no golden. Verify with a test over `templates/`.
- [ ] 1.3 Record the gaps listed in design D7 in `.agent/FINDINGS.md`, linking #99 and other issues where they exist; open issues for the rest after asking the person.

## 2. Interface

- [ ] 2.1 Add `CostItem`, `CostCategory`, `SizingBasis` and `DrillingQuantity` in `core/`, and `FlowComponent.cost_items` raising `NotImplementedError`. Verify with unit tests, including the registry test that every flow type implements it (expected to fail until task 3 is done; mark it `xfail` with a reason and remove the mark in 3.4).
- [ ] 2.2 Change `EconomicComponent.solve` to take the components and the lifetime (D5); update `finalize()` and `workflow.py`. Verify `just check` and the template goldens.

## 3. Move each formula into its owner

One commit per step; after each, `just check`, the task-1 tests and the template goldens pass.

- [ ] 3.1 Reservoirs: return `[]`.
- [ ] 3.2 Wells and grouped subsurface: `drilling_quantities()` with default asset groups (D2) and production pump parasitic power as cost items; the economic component prices drilling per group. Verify the split-well scenario.
- [ ] 3.3 `GraphSurface`: turbine, pump, cooler/condenser cost items and cooling parasitic power, moving the BAC coefficients with them; surface pipe item; `ConfigError` without node detail. Verify the plant CAPEX scenario on every ORC and flash template.
- [ ] 3.4 Economic component: sum items by category into `EconomicState`; delete the moved code; remove the `xfail` from 2.1. Verify the "unchanged results" scenario with `just test --all`.

## 4. Docs and release

- [ ] 4.1 Update `docs/components/economics.md`, `docs/architecture/components.md`, `src/tango_core/README.md`, `src/tango_core/components/README.md` and `components/AGENTS.md` (how to cost a new component), and the roadmap note that recorded keeping the central component. Run `just docs-gen` and `just docs-build`.
- [ ] 4.2 Add a `CHANGELOG.md` entry under `[In Development]` (internal change, no change in results).
- [ ] 4.3 Run one template for real and compare `.econ.csv` with a run on `main`.
