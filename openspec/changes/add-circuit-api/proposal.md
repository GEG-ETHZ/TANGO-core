# Proposal

## Why

The webapp will let users build and edit their own circuits interactively, which needs a graph that can be built, inspected and checked in Python, not a YAML file assembled first. Today the wiring is spread over `component_idx`, `prev`, `next` and `sim_config.bc_checkpoint_idx` on the components themselves, and it fails silently: `prev` is never read, a `next` that names no component drops the outlet without an error, a wrong `bc_checkpoint_idx` makes `_find_surface()` return `None`, and `component_idx == 0` also decides which well the economics treats as the injection well.

## What Changes

- Add a `Circuit` that holds labelled components and the connections between them, in the style of TESPy (`label`, `Connection`, named ports defaulting to `out1`/`in1`). `circuit.connect(a, b)` returns a `Connection`.
- Check each connection when it is made: every inlet and outlet port has a location kind (`wellhead` or `downhole`), and an outlet may only feed an inlet of the same kind. `injection_well -> surface` fails, `surface -> injection_well` closes the loop.
- Add `circuit.validate()`, which returns every problem with the whole graph as a list, in two tiers: structural problems, and problems that make the circuit impossible to run with today's orchestrators (exactly one surface, one closed ring, one inlet and one outlet per component). The data structure itself allows splits and merges.
- Add `circuit.build(common=, layout=, sim_config=, economic=)`, which creates a fresh `Workflow` through the existing config path on every call. Results are read from the workflow, `wf[component]`.
- Derive `component_idx`, `prev`, `next` and `bc_checkpoint_idx` from the circuit. Components no longer hold their wiring; the keys stay in the YAML and are handled like `type` and `variant`.
- Decide a well's injection role from its class, not from `component_idx == 0`.
- Let a component be constructed as a definition: every value given is validated, and only fields that the build fills in (shared settings and linked quantities) may be missing.
- Load every YAML config through `Circuit.from_dict`, so hand-written configs get the same checks, and serialize with `Circuit.to_dict` to the same YAML as today.
- Expose the port kinds of every registered component as data, so a frontend can colour and restrict handles.
- **BREAKING** (for inconsistent configs only): a config whose `prev` disagrees with the `next` pointing at it, whose `next` names no component, or whose `bc_checkpoint_idx` is not the surface's index, is now rejected with a `ConfigError` instead of loading. No shipped template or regression fixture is affected (all were checked).

### Non-goals

- New physics, and fluid state stored on connections instead of component outlets.
- Running circuits with splits or merges; only the data structure allows them.
- Changes to the YAML schema.
- Binding shared settings (`common`, `dt_years`, `well_spacing`, `well_pattern`, `target_extraction_pressure`) to components at build time instead of declaring them as component fields. That is the planned follow-up change; this change keeps them as fields and leaves the follow-up a local change.

## Capabilities

### New Capabilities

- `circuit-api`: building, checking, traversing and serializing a TANGO circuit as a graph of labelled components and typed connections, and building a runnable workflow from it.

### Modified Capabilities

None. No specs exist yet in `openspec/specs/`.

## Impact

- New module `src/tango_core/workflows/circuit.py`, exported from `tango_core`.
- `core/component.py`: definition construction; `component_idx` removed as a field.
- Component base classes in `components/well/`, `components/reservoir/`, `components/surface/`: `prev` and `next` removed, port kinds added; `well/base.py` role decided by class.
- `components/well/grouped_subsurface.py`: stops passing wiring keys to its segments.
- `workflows/workflow.py`: loads through `Circuit.from_dict`; `to_dict` writes the wiring from the circuit; `wf[component]` lookup.
- `orchestrators/system_direct.py`, `system_bc_iteration.py`: take solve order, downstream map and surface from the circuit instead of reading component fields. Solve logic unchanged.
- `phase_diagrams.py`: walks the circuit instead of following `.next`.
- Tests in `tests/unit/` that build components or configs by hand, `src/tango_core/README.md`, `workflows/README.md`, `docs/architecture/`, generated reference docs, `CHANGELOG.md`.
