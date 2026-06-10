# TANGO: Vision & Development Roadmap

## What is TANGO?

TANGO is GEG's geothermal simulation platform. This document describes where TANGO is
heading — both as a product that generates revenue for GEG, and as a software system that
can support that goal reliably.

---

## Product Vision: Four-Tier Access Model

The core idea is to serve a wide range of users — from students and researchers to major
oil and gas operators — through a tiered access model. Each tier unlocks more capability
and generates more revenue for GEG. The consulting/project tier is the **primary near-term
revenue path** and should be treated as such until TANGO's capabilities are robustly
demonstrated.

*Diagram: [Four-Tier Access Model](diagrams/four_tier_access_model.drawio) — open in [draw.io](https://app.diagrams.net) or in VS Code with the draw.io extension. When this document is ported to Confluence, the diagram file will be attached to the page and embedded inline.*

### Tier 1 — Community / Academic (free or very low cost)

**Who:** Students, universities, national labs, researchers, small companies (e.g. Ad Terra Energy)

**What:**
- Open-source Python package (PyPI, public GitHub/GitLab)
- Hosted documentation and worked examples
- Community contribution pipeline — bug reports, feature requests, pull requests

**Why:** Builds the user base, the TANGO brand, and the feedback loop that drives improvement.
Open-source contributions expand TANGO's capabilities at no direct cost to GEG.

---

### Tier 2 — GEG Consulting Projects (primary near-term revenue)

**Who:** Any client who wants TANGO-based analysis delivered by GEG experts

**What:**
- GEG runs TANGO on behalf of the client, delivers results and interpretation
- Closed-source advanced modules (proprietary physics, AI capabilities) not released
- Client pays per project; this is the primary mechanism for TANGO funding and feedback early on

**Why:** This is the defensible path before TANGO is proven at scale. Clients pay for
expertise and results, not just software. Project work generates both revenue *and* direct
feedback on what TANGO needs to do better.

---

### Tier 3 — Licensed On-Prem Binary

**Who:** Medium and large operators who want to run TANGO on their own infrastructure

**What:**
- Downloadable binary with a Python API
- Paid license (annual or perpetual)
- GPU-parallel compute capability
- AI-augmented scenario generation and uncertainty quantification modules

**Why:** Larger operators have IT/security reasons to prefer on-prem deployments. A
licensed binary protects GEG's IP while giving clients flexibility.

---

### Tier 4 — SaaS (Cloud, Web API & GUI)

**Who:** Large utilities, oil & gas majors, operators who want to run thousands of simulations

**What:**
- Web-based Python API (programmatic access, batch runs)
- Web GUI (no-code scenario builder for non-programmers)
- Massive parallelism with GPU acceleration — compute costs metered and passed through
- Full AI capabilities (surrogate models, Bayesian optimization, uncertainty quantification)

**Why:** The highest-value offering. Large operators need to run scenario sweeps at a scale
that is impractical on-prem. Compute costs are paid by the client — GEG's margin is on
the platform and the IP, not the hardware.

---

### Licensing Strategy Notes

The open/closed boundary is a key decision. One reasonable approach:

| Component | Open-source? | Notes |
|---|---|---|
| Core simulation engine | Yes (eventually) | Harness community contributions |
| Standard input/output utilities | Yes | Drives adoption |
| AI/ML augmentation modules | No | Primary commercial differentiator |
| GPU / massive-parallel backend | No | Tier 3/4 only |
| Advanced analysis workflows | No | Delivered via consulting (Tier 2) |

This mirrors models used successfully by e.g. OpenFOAM (open core) + commercial
extensions, or Ansys (open APIs, proprietary solver backends).

---

## Technical Roadmap: The TANGO Refactor

### Why TANGO Needs a Refactor

The current TANGO codebase is a product of rapid, results-driven development. It works,
but it has accumulated structural debt that will limit everything in the product vision above:

- No reliable way to test individual components in isolation
- Input file format does not match the module structure or the physical system hierarchy
- State management is implicit — hard to reason about, impossible to parallelize safely
- No serialization contract — saving and loading intermediate states is fragile
- No type safety — mypy fails, runtime errors are hard to trace

The refactor does not aim to rewrite TANGO from scratch. It aims to **make TANGO congruent**
— so that the input format, the code objects, the module layout, and the physical systems
they represent all tell the same story.

---

### Design Issues to Resolve

#### The `native` vs. `external` naming problem

The current codebase distinguishes `SystemNative` from `SystemExternal`, but this distinction
is misleading. `SystemExternal` is not primarily about external simulators — it is used
whenever `bc_iteration` is present in the schedule, including for runs that use only native
TANGO code and no external tools at all (e.g. `flexible_SF_manual.yml`). The actual split is:

- `SystemNative`: simple timestep execution, no boundary-condition iteration
- `SystemExternal`: bc_iteration convergence loop — finds the injection pressure/mass flow
  that balances the system — plus optional hooks for external simulators (CMG, MOOSE, DWSIM)

Conflating these two things under the "external" label obscures what the code actually does
and makes it harder to reason about which path a given config will take. The refactor should
rename these to reflect their actual behavior — `SystemDirect` / `SystemBCIteration` — with
external simulator support as a separate, composable concern.

Orchestrator selection in `tango_next` is automatic: if `schedule.bc_iteration` is present,
`SystemBCIteration` is used; otherwise `SystemDirect`. No `workflow` key is needed in
a top-level key. A future implicit solver is selected via
`schedule.bc_iteration.solver: implicit` — keeping the signal inside the part of the config
that governs solver behavior.

The native reservoir model assumes mass conservation: injection rate equals production rate
at every timestep (1D Darcy flow, incompressible fluid). Full reservoir simulators (CMG,
MOOSE) do not make this assumption — they model pressure transients and compressibility,
so inlet and outlet flow rates can differ during transients. This may require a different
solver strategy when a transient reservoir component is used, and is another reason to
resolve the external-tool socket question (see below) before that integration work begins.

#### Where to provision sockets for external tools (open question)

CMG, MOOSE, DWSIM and similar external simulators need to be integrated at some point. The
current code treats this as an orchestrator-level concern (`SystemExternal`). An alternative
view is that these are best modeled as **reservoir components** (or surface components, for
DWSIM) — they implement the same interface as any other component, but delegate computation
to an external process. Under this model, the orchestrator stays clean and the external
coupling is entirely encapsulated in the component adapter.

This question — whether external tools are orchestrator add-ons or component adapters (or
both) — needs careful thought before the integration work begins. The architecture decision
should drive the socket design, not the other way around. Leave this as an explicit open
question until there is a concrete use case to design against.

#### Web app config fragmentation (tango-super ecosystem)

The vibe-coded web app in the broader `tango-super` ecosystem stores geothermal system
configuration data separately from the YAML input files. Worse, the graphics annotations
(the arrows and lines connecting components in the UI) live somewhere entirely separate from
the graph network data that defines those connections in the input files. This is the same
root problem as the scattered YAML structure — data about one logical thing is split across
multiple stores.

The new input schema (Phase 1) should be treated as the single source of truth for both the
simulation configuration and the graph topology. The web app should read from and write to
that schema, not maintain its own parallel representation.

---

### Refactor Phases

*Diagram: [Refactor Phases](diagrams/refactor_phases.drawio) — open in [draw.io](https://app.diagrams.net) or in VS Code with the draw.io extension. When this document is ported to Confluence, the diagram file will be attached to the page and embedded inline.*

---

### Phase 0 — Establish Baseline (before touching any code)

**Goal:** Lock down what TANGO currently does so that refactored code can be verified against it.

- Write **characterization tests** that run current TANGO on a set of representative input
  files and save the outputs as reference fixtures
- Capture **performance baselines** (runtime, memory consumption) on those same inputs
- These baselines are the regression test suite — any future change that breaks them is
  immediately visible
- **Diagrams** -- need to build out diagrams to communicate to management how
  things are currently structured

*Diagram: [Input File Structure](diagrams/src/phase0_input_file_structure.drawio) — open in [draw.io](https://app.diagrams.net) or VS Code draw.io extension.*
*Diagram: [Runtime Code Objects](diagrams/src/phase0_code_objects.drawio)*
*Diagram: [Module Structure](diagrams/src/phase0_module_structure.drawio)*
*Diagram: [Execution Flow](diagrams/src/phase0_execution_flow.drawio)*

**Tasks:**
- [x] Diagrams
    - [x] structure of input files (use ./examples/flexible_SF_manual.yml as an initial example and this may be sufficient)
    - [x] structure of instantiated code object corresonding to the input file
    - [x] package/module/class structure, highlighting paths touched by ./examples/flexible_SF_manual.yml
- [ ] Write characterization tests that run current TANGO on representative
    input files and capture reference outputs as fixtures (NOTE: Chad thinks the
    regression tests are already good enough to serve this purpose, especially since
    we're not sure the existing baseline should be interpreted as ground truth)
- [ ] Capture performance baselines (runtime, memory) on those same inputs
    (NOTE: this could be added to existing regression tests, as long as it can be
    done without having much impact on duration of tests)

---

### Phase 1 — Restructure Input Format & Module Layout

**Goal:** Make the input files, the module structure, and the physical system hierarchy
all congruent with each other.

- **New input file schema:** Each component (e.g. `injection_wellbore`) stores
  all its own attributes, its `component_idx`, and its previous/next
  `component_idx` values. No data at root level. Indices are assigned somewhat
  arbitrarily but increment consistently from a fixed starting point (probably
  a good idea to have the orchestrator's BC checkpoint correspond to index 0). Hierarchy of data approximately matches hierarchy of physical
  systems.
- **Parallel module tree:** New code structure built alongside (not replacing) the old one
  until verified. `mypy --strict` and `ruff` pass from the first commit.
- **Format converter:** One-way migration tool from old to new input format.
- **Diagrams** -- need to build out diagrams to communicate to management
  how things should be structured and why the new structure addresses the
  shortcomings of the old structure

*Diagram: [New Input File Structure](diagrams/src/phase1_new_input_file_structure.drawio) — open in [draw.io](https://app.diagrams.net) or VS Code draw.io extension.*
*Diagram: [New Module Structure](diagrams/src/phase1_new_module_structure.drawio)*
*Diagram: [Execution Flow](diagrams/src/phase1_execution_flow.drawio)*

**Tasks:**
- [x] create temporary space for new structure
- [ ] Consolidate code object data and graph connections so that each component
    (e.g. `injection_wellbore`) stores all its own attributes, a `component_idx`,
    and previous/next `component_idx` values
- [ ] Ensure no data is stored at root level
- [ ] Make hierarchy of data approximately match hierarchy of physical systems
- [ ] Diagrams of new structure
    - [x] desired structure of input files (use new version of
        ./examples/flexible_SF_manual.yml as an initial example) and code
        objects (which are identical to input files in the new structure)
    - [x] package/module/class structure, highlighting paths touched by ./examples/flexible_SF_manual.yml
- [ ] Design and migrate `addons` (ThermaGraph, Analyzer): the old implementation was a
    stringly-typed activation flag, never cleanly realized as separate installable dependencies.
    In `tango_next`, addons should be first-class composable components with a defined ABC.
    Needs a design decision before the migration tool handles them.
- [ ] Build a one-way migration tool from old to new input format
- [x] Stand up the parallel module structure with `mypy --strict` and `ruff` passing from the first commit
- [ ] Bring in classes, methods, and functions to make the new structure functional

---

### Phase 2 — Code Objects & State Management

**Goal:** All TANGO code objects have explicit, validated structure and a clean state contract.

- **Pydantic `BaseModel` (preferred) or `dataclass`** for all classes — structure is visible
  from the code itself, not inferred from runtime behavior.
- **`state` object per component** — transient state variables stored in a component-specific
  `state` instance, not scattered across the object.
- **`LockedState`** — enforces that each state variable can be updated once and only once per
  timestep. Catches a whole class of subtle simulation bugs.
- **`history` object** — saves state at user-specified intervals; supports `None` (no temporal
  output) for performance-critical runs.
- **Serialization:** Every TANGO code object gets `to_file` / `from_file` / `to_str` /
  `from_str` methods. Format-agnostic (JSON, YAML, MessagePack, pickle).
- most of these points have examples in https://github.com/NatLabRockies/fastsim
  (~/git/nrel/fastsim as of 2026-06-08 on Chad's computer). In fastsim,
  `TrackedState` is the analog for `LockedState`, but since we're (at least
  initially) doing this in Python, we may need to account for the slower
  attribute accessing and use slots or similar.

**Tasks:**
- [ ] Convert all classes to Pydantic `BaseModel` (preferred) or `dataclass`
- [ ] Add a component-specific `state` object to each class; move all transient state variables into it
- [ ] Implement `LockedState` — enforces each state variable is updated once and only once per timestep
- [ ] Implement `history` object — saves state at user-specified intervals, with
    `None` supported for no temporal output
- [ ] Implement `iter_history` object that saves the state for each solver
    iteration at user-specified timestep intervals
- [ ] Add a `SerdeAPI` mixin to `core/` (modeled on the fastsim Rust trait at
    `fastsim-core/src/traits/serde_api.rs`). The mixin provides `to_file` /
    `from_file` / `to_str` / `from_str` with format dispatch (YAML, JSON,
    MessagePack) and calls `self.init()` after deserialization. Any class that
    inherits `SerdeAPI` and implements `Init` gets the full serialization API
    for free.
- [ ] Make sure that all parameters and state variables have comments (or doc
    strings if there's a way to do this, like in Rust) explaining what they are
    and the unit of measure (e.g. watts).  For any variables with non-standard
    SI units (e.g. MPa), the variable name should include `_<unit_type>` (e.g.
    `_megapascals`)

---

### Phase 3 — Modularity, Verification & Scale-Out

**Goal:** TANGO components are independently testable; the full system is verified against
baseline; the refactor is applied to all input configurations.

- **`solve()` method per component:** Any physical component can be instantiated and solved
  independently via a test harness, without requiring the full TANGO system to be running.
  This is the foundation for unit testing, debugging, and eventually parallelization.
- **Regression verification:** Run the refactored system on all baseline input files;
  verify results match within tolerance; flag divergences for investigation in both
  old and new code.
- **Scale-out:** Work through all TANGO input file configurations one at a time. Onboard
  Janna or additional support to accelerate this phase.

**Tasks:**
- [ ] Add `solve()` method to each physical component so it can run independently via a test harness
- [ ] Run the refactored system against all baseline input files and verify results match within tolerance
- [ ] Where results diverge, investigate bugs in both the old and new code
- [ ] Compare performance against pre-refactor baselines; investigate regressions
- [ ] Store web app lines and graphics as annotations in the TANGO run file
- [ ] Onboard Janna or additional support
- [ ] Work through all remaining TANGO input file configurations one at a time


---

### Future Direction — Geospatial Viability Analysis with LLM Augmentation

An envisioned future capability: a module that combines TANGO with large language models and
publicly available geospatial datasets to automatically identify economically viable geothermal
sites — transforming TANGO from a simulation tool for known sites into a discovery tool for
unknown ones.

**What it would do:**
- Ingest publicly available geologic and geophysical data (heat flow maps, seismic profiles,
  geologic surveys)
- Retrieve and interpret local regulatory context: drilling permits, fracking regulations,
  environmental constraints, renewable energy subsidies
- Run TANGO sweeps (or a trained surrogate model) over human-designable parameters: well
  geometry (depth, separation), power plant type (Single-Flash, Double-Flash, ORC, CPG),
  working fluid, number of wells
- Rank candidate sites by economic viability (NPV, LCOE) under local regulatory and geologic
  constraints

**Geographic scope:** Switzerland, Europe, or global — wherever public datasets are available.

**Why this is interesting:** The LLM layer handles unstructured regulatory and geologic data
ingestion; TANGO provides the rigorous thermodynamic and economic evaluation. Neither does the
full job alone.

**Prerequisite:** TANGO must be fast enough (Phase 3 optimization, GPU acceleration) and the
input/output interfaces clean enough (Phase 2 serialization) to support batch runs at the
scale required for a regional or global sweep.

**Task:** Design the data ingestion pipeline, TANGO sweep configuration, and ranking/visualization
outputs as a future project scope item. Consider how TANGO's Tier 2–4 access model intersects
with this capability — a geospatial discovery tool is a strong differentiator for Tier 3/4.

---

## The Connection: Refactor Enables the Product Vision

The refactor is not an end in itself. It is the prerequisite for everything in the product
vision above:

| Product goal | Requires from refactor |
|---|---|
| Reliable consulting deliverables | Characterization tests, regression suite |
| Licensed binary distribution | Serialization, clean module boundaries |
| GPU / massive parallel compute | `LockedState`, component-level `solve()` |
| AI augmentation (surrogate models) | Clean state interface, history objects |
| SaaS web API | Serialization, input validation (pydantic) |
| Community contributions | Type safety (mypy), readable module structure |

---

## Summary

1. **Near term:** Establish baseline tests, begin Phase 1 refactor on one representative
   input file, start taking consulting projects to validate TANGO's value and fund development.
2. **Medium term:** Complete Phases 2 and 3; TANGO is clean, testable, and extensible.
   Begin building the binary distribution and licensing infrastructure.
3. **Long term:** SaaS offering with AI augmentation for large operators; community open-source
   release to drive adoption and contributions.

The licensing model and the refactor roadmap are not separate decisions — they should be
developed together, because the architecture of the code determines what business models
are even feasible.
