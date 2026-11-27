# Spec Delta

## Purpose

Lets users build, check, edit and traverse a TANGO circuit in Python as a graph of labeled components and typed connections, run it as a workflow, and save it as the same YAML config that TANGO already loads.

## ADDED Requirements

### Requirement: Components are defined without wiring

A component SHALL be constructible from its own parameters and a label, without circuit index, upstream or downstream fields. Every value given SHALL be validated at construction. Only values filled in when the circuit is built (shared settings and linked quantities) MAY be missing.

#### Scenario: Definition without shared settings

- **WHEN** a user constructs a numerical injection well with a label, diameter and pipe roughness, but no shared settings and no well length
- **THEN** construction succeeds and the object is a definition

#### Scenario: Invalid parameter fails at construction

- **WHEN** a user constructs a component with a negative diameter or an unknown parameter name
- **THEN** construction fails with an error naming that parameter

#### Scenario: Reading a value that the build fills in

- **WHEN** a user reads a shared setting or a result history from a definition
- **THEN** an error states that the value is set when the circuit is built and how to read it from the built workflow

### Requirement: Connecting components

A circuit SHALL connect an outlet port of one component to an inlet port of another and return a connection object. Ports SHALL default to the first outlet and the first inlet. A port SHALL carry at most one connection, labels SHALL be unique within a circuit, and a component SHALL belong to at most one circuit.

#### Scenario: Connecting with default ports

- **WHEN** a user connects an injection well to a reservoir without naming ports
- **THEN** the circuit holds a connection from the well's outlet to the reservoir's inlet and returns it

#### Scenario: Port already connected

- **WHEN** a user connects a second connection to an outlet that already has one
- **THEN** the connection is rejected with an error naming the component and port

#### Scenario: Duplicate label

- **WHEN** a user adds a component whose label is already used in the circuit
- **THEN** it is rejected with an error naming the label

#### Scenario: Component already in another circuit

- **WHEN** a user connects a component that belongs to a different circuit
- **THEN** it is rejected with an error

### Requirement: Connections are checked by port location

Every port SHALL have a set of possible location kinds, wellhead or downhole. Connecting SHALL fail when the outlet's possible kinds and the inlet's possible kinds do not overlap. Building SHALL fail when the exact kinds of the built components differ.

#### Scenario: Injection well into surface plant

- **WHEN** a user connects an injection well's outlet to a surface plant's inlet
- **THEN** the connection is rejected immediately, naming both ports and their location kinds

#### Scenario: Surface plant into injection well

- **WHEN** a user connects a surface plant's outlet to an injection well's inlet
- **THEN** the connection is accepted

#### Scenario: Lower production segment before its depth is known

- **WHEN** a user connects a lower production well segment, whose start depth is left to be derived, to an upper production well segment
- **THEN** the connection is accepted, and building succeeds once the derived depth puts the outlet below ground

#### Scenario: Segment ending below ground feeds the surface

- **WHEN** a circuit connects a production well segment whose outlet is below ground directly to the surface plant and is built
- **THEN** the build fails naming that connection and the mismatched location kinds

### Requirement: Port kinds are available as data

The system SHALL provide, for every registered component type, the possible location kinds of each of its ports as plain data, without building a circuit.

#### Scenario: Listing port kinds

- **WHEN** a frontend requests the port kinds of all registered component types
- **THEN** it receives, per type and port, the set of possible location kinds

### Requirement: Whole-circuit validation reports every issue

A circuit SHALL report all problems with the whole graph as a list without raising, in two tiers: structural problems, and problems that make the circuit impossible to run today (not exactly one surface plant, a component without exactly one connected inlet and outlet, or connections that do not form one closed ring).

#### Scenario: Incomplete circuit

- **WHEN** a circuit has an injection well, a reservoir and a surface plant, and the surface plant's outlet is not connected
- **THEN** validation returns a list of issues including the open outlet, and raises nothing

#### Scenario: Complete doublet

- **WHEN** a circuit forms the ring injection well, reservoir, lower and upper production well, surface plant, back to the injection well
- **THEN** validation returns an empty list

#### Scenario: Split is structurally valid but not runnable

- **WHEN** a circuit contains a component whose outlet feeds two components through two outlet ports
- **THEN** validation reports no structural issue and reports that the circuit is not a single ring

### Requirement: Building a workflow from a circuit

Building SHALL take the circuit and the shared settings (common, layout, simulation and economic settings) and return a new runnable workflow on every call, built through the same path as a YAML config. Building SHALL fail with one error listing every validation issue when the circuit has any.

#### Scenario: Build and run

- **WHEN** a user builds a valid circuit with shared settings and runs the workflow
- **THEN** the run completes and each component's results are available from the workflow by component or by label

#### Scenario: Rebuild after an edit

- **WHEN** a user replaces a component with a changed parameter and builds again
- **THEN** a new workflow is returned and the previous workflow's results are unchanged

#### Scenario: Building an invalid circuit

- **WHEN** a user builds a circuit with an open outlet and two surface plants
- **THEN** the build fails with one error that lists both issues

### Requirement: Wiring is derived from the circuit

The circuit index, upstream and downstream index of every component, and the boundary-condition checkpoint index, SHALL be derived from the connections. The component the surface plant feeds SHALL be index 0, the surface plant SHALL be last, and the checkpoint SHALL be the surface plant's index.

#### Scenario: Derived indices of a doublet

- **WHEN** the doublet ring is built
- **THEN** the injection well has index 0, the surface plant index 4, and the checkpoint index is 4

#### Scenario: Injection role without an index

- **WHEN** economics costs the wells of a built circuit
- **THEN** the injection well is costed as an injection well because of its type, not its index

### Requirement: Editing a circuit

A circuit SHALL support replacing a component by one with the same label while keeping its connections, removing a connection, and removing a component together with its connections.

#### Scenario: Replace keeps connections

- **WHEN** a user replaces the injection well with a copy that has a larger diameter
- **THEN** the circuit's connections are unchanged and the circuit holds the new component

#### Scenario: Remove a component

- **WHEN** a user removes the reservoir
- **THEN** the reservoir and both of its connections are gone, and validation reports the open ports

### Requirement: YAML configs load through the circuit

Loading a YAML config SHALL build its circuit from each component's downstream index and apply the same checks as the API. A config SHALL be rejected when an upstream index disagrees with the connection, a downstream index names no component, a circuit index differs from the derived one, or a given checkpoint index is not the surface plant's. The checkpoint index MAY be omitted.

#### Scenario: Shipped templates load

- **WHEN** any template in `templates/` is loaded
- **THEN** it loads without error and runs as before

#### Scenario: Downstream index names no component

- **WHEN** a config sets a component's downstream index to an index no component has
- **THEN** loading fails with a configuration error naming that component

#### Scenario: Upstream index disagrees

- **WHEN** a config's upstream index for the reservoir differs from the injection well that feeds it
- **THEN** loading fails with a configuration error naming the reservoir

#### Scenario: Wrong checkpoint index

- **WHEN** a config sets the checkpoint index to the reservoir's index
- **THEN** loading fails with a configuration error stating the surface plant's index

#### Scenario: Checkpoint index omitted

- **WHEN** a config with an injection mode leaves out the checkpoint index
- **THEN** it loads, and the saved config contains the derived checkpoint index

### Requirement: Circuits serialize to the existing YAML

A circuit that is runnable today SHALL serialize to a config in the existing YAML schema, with each component keyed by its label and its index, upstream and downstream index written from the circuit. A circuit that is not a single ring SHALL be refused with an error.

#### Scenario: Round trip of every template

- **WHEN** any template is loaded into a circuit, serialized, and loaded and serialized again as a workflow
- **THEN** the result equals the workflow serialization of the original template

#### Scenario: Built in Python, equal to the template

- **WHEN** a user builds the circuit of `hydro_sf_electric.yml` in Python with the same parameters and settings
- **THEN** the workflow's serialization equals that of the template

#### Scenario: Serializing a split

- **WHEN** a user serializes a circuit that contains a split
- **THEN** serialization fails with an error stating that the config format holds one ring only
