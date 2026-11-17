# Spec Delta

## Purpose

Lets a TANGO config use a reversible ORC / heat-pump plant, whose performance comes from an external model, as the surface component, evaluated on representative days within each step, with every value crossing the interface checked, and results that the economics read.

## ADDED Requirements

### Requirement: Selecting the reversible plant as the surface

A config SHALL select the reversible plant with `type: surface` and `variant: revorc`. The component SHALL be constructed and validated like every other registered component, and SHALL return an outlet stream with the inlet's mass rate.

#### Scenario: Valid config builds and runs

- **WHEN** a water-geofluid doublet config uses `variant: revorc` with a module count, an ambient profile and the default ORC schedule, and the `revorc` dependency group is installed
- **THEN** the workflow builds and runs, and the surface history holds net electric power and delivered heat for every step

#### Scenario: Mass rate is conserved

- **WHEN** the surface solves an inlet stream of 20 kg/s
- **THEN** the outlet stream has a mass rate of 20 kg/s and a pressure equal to the injection pressure

### Requirement: The external package is optional

The external model's package SHALL NOT be imported until a `revorc` surface is built. If it is missing, building SHALL fail with a `ConfigError` that names the install command.

#### Scenario: Package not installed

- **WHEN** a config with `variant: revorc` is built in an environment without the `revorc` dependency group
- **THEN** a `ConfigError` names `uv sync --group revorc`, and configs without a `revorc` surface are unaffected

### Requirement: Only water or brine geofluid

A `revorc` surface SHALL reject a geofluid other than water or brine.

#### Scenario: CO2 geofluid

- **WHEN** a config with a CO2 geofluid uses `variant: revorc`
- **THEN** a `ConfigError` states that the reversible plant model supports water or brine only

### Requirement: Plant of identical modules

The plant SHALL consist of `n_modules` identical modules sharing the mass rate equally. Heat and power SHALL be the per-module values times `n_modules`; temperatures SHALL be per-module values.

#### Scenario: Two modules

- **WHEN** a plant of 2 modules receives 16 kg/s
- **THEN** the backend is evaluated at 8 kg/s per module, and the recorded net power is twice the per-module net power

#### Scenario: Module count derived from flow

- **WHEN** `n_modules` is not given and the plant receives 20 kg/s with a per-module flow bound of 8 kg/s
- **THEN** the plant uses 3 modules

### Requirement: Representative days within each step

For each step, the surface SHALL evaluate the representative hours covered by that step, using the ambient profile and the mode schedule from the config, and SHALL record the time-weighted mean of net power and delivered heat. The returned outlet enthalpy SHALL correspond to the flow-weighted mean brine outlet temperature over the step.

#### Scenario: Annual step with monthly representative days

- **WHEN** a one-year step is solved with 12 representative days of 24 hours
- **THEN** the backend receives 288 operating points in one `evaluate` call, each month's hours are weighted by that month's number of days, and the recorded net power is the weighted mean

#### Scenario: Ambient temperature reaches the model

- **WHEN** the ambient profile is colder in January than in July and every other input is the same
- **THEN** the January points are evaluated with January's ambient temperatures, and the results differ by month

### Requirement: Mode schedule

Each representative hour SHALL have a mode, `orc`, `hp` or `off`, from the config; the default SHALL be `orc` for every hour. An `hp` hour SHALL carry a heating load and sink temperatures. An `off` hour SHALL contribute zero power and heat, and SHALL return the brine unchanged.

#### Scenario: Missing heat-pump load

- **WHEN** a schedule marks an hour as `hp` without a heating load
- **THEN** config validation fails, naming the hour

### Requirement: Inputs are checked before the call

Before calling the backend, every input SHALL be checked against the backend's validity bounds. With `out_of_range: error` (the default), an input outside its bound SHALL raise a `SurfaceModelDomainError` naming the input, its value and the bound. With `out_of_range: warn`, the point SHALL be evaluated and recorded as out of range.

#### Scenario: Brine too cold for the ORC

- **WHEN** the production well delivers brine at 90 °C to an ORC hour under the default policy
- **THEN** the run fails with a `SurfaceModelDomainError` naming the brine inlet temperature, 90 °C, and the lower bound of 95 °C

### Requirement: Results are checked after the call

Non-finite results, a brine outlet temperature below the minimum sent, and a heat-pump point the model reports as outside its supported regime SHALL be treated as out of range under the same `out_of_range` policy. The model's own warnings SHALL be recorded unchanged.

#### Scenario: Heat pump outside its supported regime

- **WHEN** the model returns zero heat and power for a heat-pump point and flags it as outside its supported regime
- **THEN** under `error` the run fails naming that point, and under `warn` the point is recorded as out of range; in neither case is the zero recorded silently

### Requirement: Economics read the plant

The economics SHALL read net electric power and delivered heat from the surface history, and SHALL cost the plant from a per-module CAPEX and fixed O&M given in the config, times `n_modules`.

#### Scenario: Plant CAPEX is not zero

- **WHEN** a `revorc` run finishes with 3 modules and a per-module CAPEX of C
- **THEN** the surface plant CAPEX used in the LCOE or LCOH is 3 C

### Requirement: The coupling reproduces the external model

Called through TANGO's wrapper at the authors' published example inputs, the surrogate backend SHALL return the same values as the external package's own reference outputs.

#### Scenario: Published example

- **WHEN** the wrapper evaluates the README example for the one-stage ORC off-design model
- **THEN** net electric power, rejected heat and brine outlet temperature match the package's own output to within floating-point tolerance
