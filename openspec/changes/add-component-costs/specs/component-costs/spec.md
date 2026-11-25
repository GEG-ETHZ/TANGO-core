# Spec Delta

## Purpose

Lets each TANGO component report its own costs, and the economic component combine them with project-level costs into CAPEX, O&M and levelized cost, so that a new kind of component is costed without changing the economic component.

## ADDED Requirements

### Requirement: Every flow component reports its costs

Every registered flow component SHALL implement `cost_items(basis)`, returning a list of cost items. The base class SHALL raise `NotImplementedError`. A component without costs SHALL return an empty list.

#### Scenario: Component without an implementation

- **WHEN** a flow component class that does not implement `cost_items` is costed
- **THEN** `NotImplementedError` is raised naming the class, instead of a cost of 0

#### Scenario: Reservoir has no costs

- **WHEN** a reservoir component is asked for its cost items
- **THEN** it returns an empty list

#### Scenario: Every registered type implements it

- **WHEN** the test suite iterates over every flow type in the component registry
- **THEN** each class implements `cost_items`, or the test fails naming it

### Requirement: Surface plant costs come from the surface

`GraphSurface` SHALL report a cost item for every turbine, injection pump and cooler or condenser group that the economic component costs today, and the cooling parasitic power, computed with today's formulas.

#### Scenario: Same plant CAPEX as before

- **WHEN** a template with a TESPy ORC plant is run
- **THEN** the sum of the surface's surface-plant cost items equals today's `CAPEX_surface_plant` to within `rel=1e-12`

#### Scenario: Missing node detail is an error

- **WHEN** a `GraphSurface` with `record_node_detail` off is asked for its cost items
- **THEN** a `ConfigError` states that plant costing needs node detail, instead of returning a plant CAPEX of 0

### Requirement: Drilling is priced per asset group

Wells and the grouped subsurface SHALL report drilling quantities with an asset group. The economic component SHALL price each asset group once, with lengths in the group summed before the cost formula is applied. By default, all vertical production sections SHALL form one group and each injection and horizontal section its own.

#### Scenario: Split production well pays one mobilization

- **WHEN** a doublet has `production_well_lower` and `production_well_upper` of the same diameter
- **THEN** their lengths are summed and priced once, and the drilling CAPEX equals today's

### Requirement: Project-level costs and financing stay central

The economic component SHALL compute permitting, exploration, drilling prices, CRF, O&M, capacity factor and levelized cost, and SHALL fill every existing `EconomicState` field by summing the reported items by category.

#### Scenario: Unchanged results

- **WHEN** the template regression suite runs after this change
- **THEN** every template's LCOE matches its golden value at `rel=1e-6` without any golden being changed, and every `EconomicState` field and `.econ.csv` column is present with the same meaning

### Requirement: The economic component gets its inputs as arguments

The economic component SHALL receive the components and the project lifetime as arguments to `solve`. No other object SHALL set its private attributes.

#### Scenario: Solving without a workflow

- **WHEN** a test builds the economic component and calls `solve` with a list of components and a lifetime
- **THEN** it computes the same results as a full workflow run with those components

### Requirement: Cost formulas are pinned by unit tests

Each cost formula SHALL have a unit test with fixed inputs and a pinned output, added before the formula moves.

#### Scenario: A formula changes by accident

- **WHEN** a moved formula returns a different value for the pinned inputs
- **THEN** its unit test fails, naming the formula
