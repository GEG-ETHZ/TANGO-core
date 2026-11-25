# Tasks

## 1. Spike: definition components

- [ ] 1.1 On `NumericalInjectionWell` alone, prototype the lenient `Component.__init__` from design D8: given values validated, missing build-time fields tolerated, `from_dict` still strict, reading a missing field raises a clear error. Verify with a throwaway test covering a valid definition, a negative diameter, an unknown key, and a strict `from_dict` that still rejects a missing `common`.
- [ ] 1.2 Decide between the lenient constructor and the `define()` fallback from the spike's result, record the outcome in `design.md` D8, and tell the person before continuing.

## 2. Build-time fields and definitions

- [ ] 2.1 Move the names of the shared settings (today `_PROTECTED_COMPONENT_KEYS` in `workflow.py`) and of the linked-quantity fields into one constant in `core`, imported by `workflow.py` and `linked_quantities.py`. Verify `just check` passes with no behaviour change.
- [ ] 2.2 Add `label` (frozen, excluded from dumps) and definition construction to `Component` for all registered classes, with `DefinitionError` naming where a missing value comes from. Verify with unit tests per registered type: a definition without shared settings and linked quantities builds, invalid values fail, `model_dump` of a built component has no `label`.

## 3. Port kinds

- [ ] 3.1 Add the `PortKind` `StrEnum` and each flow class's possible kinds per port (design D4 table), with the numerical production well narrowing its outlet by `wellhead_depth` once known. Verify with unit tests for every registered type, including a lower segment with and without `wellhead_depth`.
- [ ] 3.2 Add a registry function returning the possible kinds per registry type and port as plain data. Verify with a unit test that every `COMPONENT_REGISTRY` flow type appears and that the result serializes with `json.dumps`.

## 4. Circuit graph

- [ ] 4.1 Add `workflows/circuit.py` with `Circuit`, `Connection` and `CircuitError` (a `ConfigError`): `add`, `connect` with default ports, one connection per port, unique labels, one circuit per component, and the kind-overlap check. Verify with unit tests for each spec scenario under "Connecting components" and "Connections are checked by port location" that does not need a build.
- [ ] 4.2 Add `replace`, `disconnect` and `remove`. Verify with unit tests for the "Editing a circuit" scenarios.
- [ ] 4.3 Add `validate()` returning `CircuitIssue`s in the two tiers of design D5. Verify with unit tests: incomplete circuit, complete doublet, AGS and grouped rings, two surfaces, and a split built from a test-only component with two outlet ports.
- [ ] 4.4 Add the downstream traversal and derived wiring of design D6 (entry, `component_idx`, `prev`, `next`, `bc_checkpoint_idx`). Verify with unit tests on the doublet (entry 0, surface 4), AGS and grouped rings.
- [ ] 4.5 Add `Circuit.to_dict()` (labels as keys, `exclude_unset` dumps, `type`/`variant` from the registry, wiring from the circuit, refusal for a non-ring) and `Circuit.from_dict()` (connections from `next`, checks of `prev`, missing `next` targets, `component_idx`, and a given `bc_checkpoint_idx`). Verify with unit tests for each "YAML configs load through the circuit" error scenario, and that `from_dict` then `to_dict` reproduces the `components:` block of every template.

## 5. Orchestrators take order and routing from the workflow

- [ ] 5.1 Change `SystemDirect` and `SystemBCIteration` to receive components in solve order, a label-to-label `downstream` map and the surface label (design D7), keying `_pending_inlets` and snapshots by label and naming labels in error context. Have `Workflow` compute these from the existing fields for now. Verify `just check` passes and `just test --templates` gives unchanged golden LCOEs.
- [ ] 5.2 Update `orchestrators/README.md` and the `docs/runtime/` pages that describe index-based ordering. Verify `just docs-build` passes.

## 6. YAML loading through the circuit

- [ ] 6.1 Make `Workflow.__init__` load `components:` through `Circuit.from_dict`, validate it, strip the wiring keys before construction, take order, routing and surface from the circuit, and write wiring from the circuit in `Workflow.to_dict()`. Make `sim_config.bc_checkpoint_idx` optional, checked against the derived value. Verify with unit tests for each "YAML configs load through the circuit" scenario through `Workflow`, a round-trip test over every template (`Workflow.to_dict` before and after), and `just test --templates`.
- [ ] 6.2 Update `docs/CONFIG_VALIDATION.md`, `docs/architecture/config.md`, `workflows/README.md` and the package README's "Circuit" paragraph for the new checks and the optional `bc_checkpoint_idx`; run `just docs-gen`. Verify `just docs-build` and `tools/gen_reference.py --check` pass.

## 7. Wiring leaves the components

- [ ] 7.1 Decide the well role by class (design D9) and remove `component_idx` from `Component` and `prev`/`next` from the four flow base classes, including `grouped_subsurface`'s segment keys, the economic `component_idx` default and index-based error messages. Fix the stale "surface is always at component_idx=0" docstring in `surface/base.py`. Verify `just check`, a unit test that economics costs the injection well by type, and `just test --templates`.
- [ ] 7.2 Make `phase_diagrams.py` walk the circuit instead of following `.next`. Verify with its existing test or a new unit test on one template's loop order.
- [ ] 7.3 Update unit tests that build components or configs with wiring fields (`test_serde_roundtrip.py`, `test_grouped_subsurface.py`, and others found by `just check`). Verify `just check` passes.

## 8. Building workflows from a circuit

- [ ] 8.1 Add `circuit.build(common=, layout=, sim_config=, economic=)`, which assembles the config dict and returns `Workflow(cfg)`, raising one `CircuitError` listing every issue; add `Workflow.__getitem__` by component or label. Verify with unit tests: build and run a short lumped circuit, a rebuild after `replace` leaves the first workflow's results unchanged, and building an invalid circuit lists all issues.
- [ ] 8.2 Add the build-time exact port-kind check. Verify with a unit test where a lower segment ending below ground feeds the surface.
- [ ] 8.3 Add a unit test that builds `hydro_sf_electric.yml`'s circuit in Python and compares `wf.to_dict()` with the template's. Verify it passes.
- [ ] 8.4 Export `Circuit` from the package, document the API with a worked example in `workflows/README.md`, add a page or section in `docs/architecture/`, and run `just docs-gen`. Verify `just docs-build` passes and the example runs as written.
- [ ] 8.5 Add a `CHANGELOG.md` entry under `[In Development]`: the circuit API, and under Breaking the rejection of configs with inconsistent wiring and the optional `bc_checkpoint_idx`. Verify the entry renders in `just docs-build`.

## 9. Integration

- [ ] 9.1 Run `just check` and `just test --templates`; both pass with unchanged golden values.
- [ ] 9.2 Run `uv run tango_core run templates/hydro_sf_electric.yml --save-dir <tmp>` and a Python script that builds the same circuit and runs it, and compare the LCOE; or list the change in `.agent/DEFERRED_VERIFICATION.md`. Show the person the result.

## Workflow follow-up

- Open the follow-up change that binds shared settings (`common`, `dt_years`, `well_spacing`, `well_pattern`, `target_extraction_pressure`) to components at build time instead of declaring them as fields.
- Archive this change after review and merge.
