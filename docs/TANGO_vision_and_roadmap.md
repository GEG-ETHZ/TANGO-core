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
whenever `bc_iteration` is present in `sim_config`, including for runs that use only native
TANGO code and no external tools at all (e.g. `flexible_SF_manual.yml`). The actual split is:

- `SystemNative`: simple timestep execution, no boundary-condition iteration
- `SystemExternal`: bc_iteration convergence loop — finds the injection pressure/mass flow
  that balances the system — plus optional hooks for external simulators (CMG, MOOSE, DWSIM)

Conflating these two things under the "external" label obscures what the code actually does
and makes it harder to reason about which path a given config will take. The refactor should
rename these to reflect their actual behavior — `SystemDirect` / `SystemBCIteration` — with
external simulator support as a separate, composable concern.

Orchestrator selection in `tango_next` is automatic: if `sim_config.bc_iteration` is present,
`SystemBCIteration` is used; otherwise `SystemDirect`. No `workflow` key is needed in
a top-level key. A future implicit solver is selected via
`sim_config.bc_iteration.solver: implicit` — keeping the signal inside the part of the config
that governs solver behavior.

**This selection is a topology question, not a second encoding of `InjectionPolicy`.**
Early on, `SystemBCIteration` re-implemented the entire single-pass solve loop itself, so
`InjectionPolicy.MANUAL` (one pass per timestep, no correction) ended up functionally
identical to what `SystemDirect` already did — two code paths doing the same thing, picked by
whether a YAML key happened to be present. The fix: `SystemBCIteration` now subclasses
`SystemDirect` and reuses its single-circuit-pass `run_timestep` (one call per pass for
`MANUAL`/`MANUAL_FRACING_CHECK`, repeated calls inside a Newton loop for `AUTO_*` once Phase 2
lands) instead of duplicating it. `SystemDirect` owns the only implementation of "one circuit
pass" and "loop over timesteps"; `InjectionPolicy` is the sole authority over how many passes
a timestep takes, and never determines which orchestrator *class* is used. Orchestrator choice
remains a topology question — does this graph declare a circuit with a BC variable to solve
for at all (e.g. a bare wellbore test fixture has none and uses `SystemDirect` directly).

The top-level YAML config is split by concern: `common` holds shared physical *parameters*
(fluid, rock properties — not physical constants like Planck's constant), `layout` holds
well-field geometry (`well_spacing`, `well_pattern`), and `sim_config` holds time stepping
and solver/injection control (`time`, `bc_iteration`, `mass_rate`). This replaced an earlier
single `schedule` block that mixed all three concerns under a name that only really fit the
time-stepping piece.

The native reservoir model assumes mass conservation: injection rate equals production rate
at every timestep (1D Darcy flow, incompressible fluid). Full reservoir simulators (CMG,
MOOSE) do not make this assumption — they model pressure transients and compressibility,
so inlet and outlet flow rates can differ during transients. This may require a different
solver strategy when a transient reservoir component is used, and is another reason to
resolve the external-tool socket question (see below) before that integration work begins.

#### BC iteration mode — `InjectionPolicy` (replaces `check_fracing` / `manual` / `automatic`)

The current `src/tango/` code controls BC iteration behavior through three separate,
poorly documented fields:

- `mass_rate.type: "manual"` — mass flow rate is user-prescribed
- `mass_rate.type: "automatic"` — mass flow rate is computed from the Darcy fracing limit
- `bc_iteration.check_fracing` — a boolean flag with undocumented scope
- `bc_iteration.max_mass_rate` — a global cap applied after all other rate logic

These fields interact in ways that are not documented anywhere and that are easy to
misread. Worse, they conflate two physically distinct fracing mechanisms.

**Two distinct fracing mechanisms**

1. **Flow-induced fracing** — mass flow rate is high enough that, by Darcy's law, the
   reservoir inlet pressure exceeds the fracing threshold. The `fracing_flow()` function
   computes the maximum sustainable mass rate at which the threshold is exactly reached:

   ```
   fracing_flow = 2πhk × (overpressure% / 100 × hydrostatic_P) / (μ × ln(re / rw))
   ```

   Because µ and ρ depend on injection-side fluid conditions, `fracing_flow()` changes
   as `test_p` changes — making mass rate and injection pressure coupled variables when
   this mechanism is active.

2. **Pressure-induced fracing** — injection wellhead pressure (`test_p`) is set high
   enough that, after hydrostatic head and friction losses in the injection well, the
   reservoir inlet pressure `inj_well.outlet.P` exceeds
   `hydrostatic_P × (1 + overpressure% / 100)`.

These two mechanisms are checked via separate code paths in `src/tango/` but neither is
clearly labeled. `check_fracing` guards only the flow-rate cap; the injection pressure
adjustment (`test_p` update) runs regardless of the flag.

**`InjectionPolicy` — the clean replacement**

In `tango_next`, both concerns are unified into a single enum that makes every operating
mode self-documenting. The YAML field is `sim_config.bc_iteration.mode`. Note that
`mass_rate` is only meaningful for policies where flow rate is user-prescribed (`MANUAL`,
`MANUAL_FRACING_CHECK`, `AUTO_PRESSURE`); for `AUTO_FLOW` and `AUTO_BOTH` it is computed
from `fracing_flow()` each pass, so the YAML field may be omitted entirely under those modes.

```python
class InjectionPolicy(enum.StrEnum):  # tango_next.core.policies
    """Controls how mass flow rate and injection wellhead pressure are determined."""

    MANUAL = "manual"
    """Both mass flow rate and injection wellhead pressure are user-specified.
    No fracing check is performed. Single solver pass per timestep."""

    MANUAL_FRACING_CHECK = "manual-fracing-check"
    """Both user-specified. Both fracing directions are checked; any violation
    raises an error. Injection pressure is reduced if the initial value would
    cause pressure-induced fracing; rate is capped if it would cause
    flow-induced fracing. Single solver pass per timestep."""

    AUTO_PRESSURE = "auto-pressure"
    """Mass flow rate is user-specified. Injection wellhead pressure is iterated
    until the reservoir inlet pressure converges to the fracing threshold
    (Newton step: test_p += target_reservoir_P - inj_well.outlet.P).
    If the converged state would also cause flow-induced fracing, an error
    is raised."""

    AUTO_FLOW = "auto-flow"
    """Injection wellhead pressure is user-specified. Mass flow rate is iterated
    to the Darcy-law fracing limit (fracing_flow()) each pass. Because fracing_flow()
    depends on injection-side fluid properties, the rate co-evolves with pressure
    until both stabilize. If the converged state would cause pressure-induced fracing,
    an error is raised."""

    AUTO_BOTH = "auto-both"
    """Both are iterated simultaneously. If no feasible injection pressure exists
    at the target flow rate, the flow rate is reduced until a feasible pressure
    can be achieved. This is the most robust mode for high-flow or
    low-permeability reservoirs."""
```

`max_mass_rate` is preserved as a separate optional hard cap that applies after
mode-based rate computation, regardless of mode. It is meaningful for `AUTO_FLOW` and
`AUTO_BOTH` (to bound runaway rate growth) but has no effect in `MANUAL` or
`MANUAL_FRACING_CHECK` if the specified rate is already below the cap.

**Current implementation status (confirmed 2026-06-16):** only `MANUAL` is implemented in
`tango_next` today — a single circuit pass, no correction of any kind. `MANUAL_FRACING_CHECK`,
`AUTO_PRESSURE`, `AUTO_FLOW`, and `AUTO_BOTH` all raise `NotImplementedError` from
`SystemBCIteration.run_timestep` (Phase 2 work). In particular, `AUTO_BOTH` — which jointly
manipulates both mass flow rate and injection pressure — is confirmed to raise
`NotImplementedError` rather than silently doing something wrong; this should hold until the
joint Newton update rule described above is actually implemented.

**Future direction — whole-horizon optimization (`MIN_LCOE` and friends):** `AUTO_PRESSURE` /
`AUTO_FLOW` / `AUTO_BOTH` solve a *per-timestep* physical constraint (find the BC variable(s)
that keep the system at the fracing threshold *this timestep*). A `MIN_LCOE` variant is a
different kind of problem: LCOE is a whole-horizon objective — it depends on cumulative energy
output and cost across every timestep in the simulation, not on any single timestep in
isolation. Minimizing it means searching over decision variables (e.g. constant `mass_rate`
and/or `test_p` setpoints, or eventually time-varying schedules) and re-running the *entire*
multi-timestep simulation as the inner evaluation of an outer constrained optimizer — much
closer in shape to the existing `optimizerr.py` / `pymoo` machinery in `src/tango/` than to the
per-timestep Newton loop in `SystemBCIteration`. Constraints would be the same fracing limits
checked at every timestep along the way. This means `MIN_LCOE` (and any other whole-horizon
objective — e.g. `MAX_NET_POWER` over the full horizon rather than per-timestep) likely cannot
just be another `InjectionPolicy` value handled inside `SystemBCIteration.run_timestep`; it is
architecturally an outer loop wrapping `Workflow.run()` itself. `InjectionPolicy` should leave
room for this distinction — e.g. a separate enum or a flag distinguishing per-timestep BC
policies from whole-horizon optimization objectives — rather than assuming every future variant
fits the same per-timestep mechanism as `AUTO_PRESSURE`/`AUTO_FLOW`/`AUTO_BOTH`.

**Approximate mapping from `src/tango/` configurations**

| `src/tango/` configuration | `InjectionPolicy` equivalent |
|---|---|
| `type: manual, check_fracing: False` | `MANUAL` |
| `type: manual, check_fracing: True` | `MANUAL_FRACING_CHECK` |
| `type: automatic` (standard, non-Hotmaps) | `AUTO_BOTH` (test_p and mass_rate co-evolve each iteration) |

In HotmapsDispatch mode, `type: automatic` has more complex behavior: early timesteps
use a specified rate with an optional fracing cap (similar to `MANUAL_FRACING_CHECK`),
while later timesteps either use `fracing_flow()` or iterate mass flow rate to hit a
target thermal power output (`controlled_power_generation: yes` — note that `src/tango/`
checks this with a `== "yes"` string comparison, so `True` silently does nothing there).
This is a distinct operating mode not yet represented in `InjectionPolicy` and should be
designed as its own variant when the Hotmaps feature is migrated to `tango_next`.

**Planned future variants**

`InjectionPolicy` is intentionally scoped to injection control rather than just fracing
prevention, leaving room for variants that optimise operating objectives:

- `MAX_NET_POWER` — iterate mass flow rate and injection pressure to maximise
  `gross_power − pump_parasitic_load`, subject to the fracing limit as a hard constraint.
- `MIN_LCOE` — similar, but objective is levelised cost of energy over the project lifetime.
  Note: the decision-variable vector for `MIN_LCOE` isn't necessarily limited to
  `InjectionPolicy`'s own variables (`mass_rate`, `test_p`) — see "Extraction pressure as
  an independent policy axis" below, which argues `target_extraction_pressure` is a third,
  independent variable a whole-horizon optimizer may also need to search over.

These require the Phase 2 Newton-step solver infrastructure and the pump electricity
accounting fix to be in place before they can be meaningfully implemented.

*Diagram: [BC Iteration Solver](diagrams/src/phase1_bc_iteration_solver.drawio) — shows
current modes and which trigger the outer convergence loop.*

#### Extraction pressure as an independent policy axis (naming TODO: split `bc_iteration`)

`sim_config.bc_iteration` currently houses `InjectionPolicy` (`mode`) and `mass_rate` —
both about finding the injection-side BC variable(s) needed to prevent fracing. But
`SystemBCIteration`'s own module docstring already documents a second, independent
sub-problem under "Two independent sub-problems — do not conflate": the production-pump
inner loop that finds `dP_pump` needed to hit `target_extraction_pressure` at the surface
inlet. Today `target_extraction_pressure` is just a fixed value on the surface component
spec, and the pump-loop physics that would seek it isn't implemented yet
(`SingleFlashSurface.solve()` is still a Phase 1 placeholder) — but the config naming
already implies these two concerns are one thing (`bc_iteration`) when the code's own
docstring says they are not.

**Proposed split (naming TODO, not finalized):** rename `bc_iteration` to something scoped
specifically to the injection side — e.g. `injection_control` (housing `mode` /
`InjectionPolicy` / `mass_rate`) — and introduce a sibling `extraction_control` block
housing `target_extraction_pressure` and a parallel `ExtractionPolicy` enum. Both
`injection_control` and `extraction_control` are "boundary condition" concerns in the
literal sense — one BC at the injection wellhead, one BC at the surface inlet from
production — so "BC" as an umbrella term stays accurate; a single flat `bc_iteration` key
just incorrectly implies there is only one such concern.

**`ExtractionPolicy` sketch (future, not implemented):**

- `FIXED` — current/default behavior: `target_extraction_pressure` is user-specified; the
  production-pump inner loop (Phase 2) solves for `dP_pump` to hit it exactly, as already
  described in `SystemBCIteration`'s docstring.
- `MIN_LCOE` (and room for other future variants) — `target_extraction_pressure` itself
  becomes a decision variable in the same whole-horizon outer optimizer sketched above
  under `InjectionPolicy`'s "Future direction" note — not a new solver mechanism, just a
  wider decision-variable vector for the existing future mechanism.

**Independence, not isolation:** `InjectionPolicy` and `ExtractionPolicy` should be two
independently selectable enums — `InjectionPolicy.AUTO_BOTH` alongside
`ExtractionPolicy.FIXED` should be just as valid as `InjectionPolicy.MANUAL` alongside a
future `ExtractionPolicy.MIN_LCOE`. When both axes are set to whole-horizon optimization
simultaneously, the outer optimizer's decision-variable vector simply spans both (mass
rate and/or injection pressure *and* target extraction pressure) — it is still one outer
optimizer, just searching a larger space.

This is an open design question for Phase 2+, not an action item now: `InjectionPolicy.AUTO_*`
itself isn't implemented yet, so building `ExtractionPolicy` scaffolding ahead of that
would be premature.

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

#### Pump electricity accounting — known inconsistencies (needs HIL verification)

**⚠ Human-in-the-loop (HIL) verification required before relying on net power or LCOE
outputs from `src/tango/`.  The summary below is based on static code analysis and may
contain errors — the original codebase is complex enough that misreading a sign convention
or a code path is easy.**

Current best understanding of pump accounting per surface plant type:

| Pump | FlexiblePP | ORC | CPG |
|---|---|---|---|
| Injection pump(s) | ✓ tracked — TESPy `Compressor` nodes summed in `_compute_total_pump_work()` | n/a (no injection pump in cycle) | ✓ tracked — computed explicitly in `_update_pump_state()` |
| Production downhole pump | ✓ via `prod_pump_w_list` → `PowerPlantCost.compute_net_power()` at econ layer; **not** in `surface.w_net` directly | ✓ via `w_downhole_pump` at econ layer; **not** in `surface.w_net` directly | ✗ likely untracked — `prod_pump_w_list` accumulates it but CPG never uses it |
| Working fluid / ORC pump | n/a | ✓ in `w_net` directly | n/a |
| Cooling / condensing parasitic | ✓ | ✓ | ✓ |

Known inconsistency: for FlexiblePP and ORC, `surface.w_net` (the physics-layer value) does
**not** include the production downhole pump — it is only added at the economic calculation
layer.  Code that reads `surface.w_net` directly (e.g. logging, plotting) will undercount
parasitic loads.

For a high-permeability reservoir injection pump loads are small (≈ 2–6% of gross power).
For a low-permeability reservoir the required injection pressure is much higher and pump load
can reach 15–20% of gross — large enough to determine whether a site is economically viable.
Getting this right matters most exactly where the resource is marginal.

In `tango_next` Phase 1, no pump electricity is wired to an `EconomicComponent` yet —
placeholders with `TODO (Phase 2)` notes throughout.

Phase 2 should:
- Verify the table above with HIL testing on representative configs
- Fix the CPG production downhole pump gap in `src/tango/`
- Reconcile `surface.w_net` with the economic-layer value so there is one authoritative
  net-power number per timestep (see cascading calculation principle below in Phase 2)
- Wire `pump_power_watts` from all tango_next wellbore components into the economic component

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

#### Grouped subsystems (composite components)

The `surface` component in `tango_next` already has a nested `power_plant:` block with
its own local `prev`/`next` graph — it is a grouped subsystem in everything but name.
The goal is to make this a first-class, general mechanism rather than a hardcoded special
case.

**The design:** Any component whose spec contains a nested `components:` block is a
`GroupedComponent`. Internally it owns a full inner graph (nodes linked by `prev`/`next`),
and the framework selects the inner orchestrator by the same DAG-vs-loop detection used for
the outer graph — no special-casing needed. The outer orchestrator treats a `GroupedComponent`
as a black box with a defined inlet stream and outlet stream, identical to any other
component.

**How boundary conditions are expressed:** `Source` and `Sink` terminal nodes already encode
this naturally. A `Source` node in the inner graph — a node with no `prev` — signals "I need
a boundary condition from outside." A `Sink` node — no `next` — signals "I produce an output
for the outer graph." When the inner graph is open on both ends (Source on one side, Sink on
the other), it cannot self-close; the outer loop must provide the inlet BC. This is exactly
the same topology check that determines whether the outer system needs BC iteration or can run
as a direct-solve DAG.

**Why this matters:** It allows arbitrary grouping — an injection well + reservoir +
production well stack could become a `SubsurfaceGroup`; a multi-stage surface plant could be
a `SurfacePlantGroup` — without requiring the orchestrator to know anything about the
internals. The sub-system can be developed, tested, and solved independently (since it can
be given synthetic BCs at its Source nodes), and then dropped into any outer graph as a
single node.

**Recursive traversal:** A `GroupedComponent`'s inner graph can itself contain another
`GroupedComponent` — the same Source/Sink-driven DAG-vs-loop detection and orchestrator
selection applies at every level. The solver should not assume a fixed nesting depth of one
(outer graph → power plant sub-graph); it should walk the component tree recursively,
instantiating an `Orchestrator` for each level that contains a nested `components:` block,
however deep that goes.

**Current gap:** `component_idx: 0` is currently treated as a special "BC checkpoint" by
`SystemBCIteration` — it happens to be the surface in `flexible_SF_manual.yml`, but there is
nothing inherently BC-related about the surface component itself. That label is a hardcoded
artifact of the current single-level implementation, not a real property of any component.
Once the `GroupedComponent` mechanism above is in place, the entry point into a circuit is
just "wherever component_idx 0 happens to land" — the actual BC behavior comes from the
Source/Sink topology, not from a magic index tied to a specific component type. The power
plant sub-graph parsing is also bespoke rather than going through a generalized
`GroupedComponent` path. Closing both gaps is a Phase 3 task.

---

#### Miscellaneous

All unit conversions should be handled via constants imported from a
module defining unit conversion constants and physical constansts, e.g.
`p_out_kilopascals = p_out_megapascals * 1_000` should be
`p_out_kilopascals = pascals * MEGA_TO_KILO`

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
- [ ] When comparing `tango_next` against original `src/tango/`, first wire
    `tango_next` to use the **same formulas as the original** (Haaland friction
    factor, radial Dupuit-Thiem reservoir flow, full TESPy surface cycle) and
    verify that results match — or identify and explain any discrepancies.
    Only after that baseline is confirmed should the alternative formulas
    already implemented in `tango_next` (Swamee-Jain, linear 1-D Darcy,
    lumped-efficiency surface) be run, to evaluate where they land relative
    to the verified baseline.  Both sets of formulas should remain as
    selectable variants — do not replace the originals.

    **Status (2026-06-16) — injection well done, rest still open:**
    `NumericalInjectionWell` (`src/tango_next/components/well/numerical.py`,
    registered as `unit: numerical`) now replicates
    `src/tango/units/native/well/base.py::WellUnitNative.process_stream()`
    exactly: 100-cell axial discretization, Haaland friction factor
    (`core/fluid_utils.py::friction_factor_haaland`), Adams et al. (2015)
    transient conductive heat loss, and real CoolProp property lookups via a
    new thin wrapper (`core/fluid_state.py::FluidState`, parity with
    `src/tango/core/fluidstate.py`). `LumpedInjectionWell` (`unit: native`) is
    kept as the permanent fast/simple variant per its module docstring — not
    replaced.

    Validated against `src/tango/` on `examples/flexible_SF_manual.yml` /
    `examples/tango_next/flexible_SF_manual.yml`: feeding the *same* inlet
    conditions and running the same 20 sequential timesteps, dimensionless
    time (`t_d`) matches **bit-for-bit** (11893.298014434364 both sides),
    outlet temperature matches to ~5 significant figures (354.5490 K vs.
    354.5498 K), outlet pressure to ~3-4 (49.7357 MPa vs. 49.7522 MPa, ~0.03%
    relative). The residual ~0.03% pressure difference is not yet root-caused
    — likely floating-point order-of-operations across 100 cells × 20
    timesteps rather than a formula error, but not confirmed. **A true
    end-to-end run-the-whole-example comparison still does not match**,
    because the upstream `SingleFlashSurface` is still a Phase 1 placeholder
    (`outlet.P = self._injection_pressure`, no real TESPy cycle) — so the
    injection well's *inlet* conditions differ between the two full runs even
    though the well's own integration is now correct in isolation.

    **Remaining gaps for whoever picks this up next** (intended hand-off
    point — Chad's plan is to get this set of two example files into good
    shape, then hand continuation to an intern):
    - Root-cause the residual ~0.03% pressure discrepancy in the isolated
      well-only comparison above.
    - `LumpedProductionWell` / `LumpedProductionWellPump` still use the
      simplified closed-form model (no discretization, no heat loss at all —
      `T_outlet = T_inlet`). A `NumericalProductionWell` following the same
      pattern as `NumericalInjectionWell` is the natural next step — note
      `src/tango/`'s `ProductionWellUnitNative` shares the *same*
      `WellUnitNative.process_stream()` base class, just with `_f_dir = 1.0`
      (upward flow) instead of `-1.0`.
    - `LumpedReservoir` is still linear 1-D Darcy vs. the original's radial
      Dupuit-Thiem model (`BC_calculator.py`).
    - `SingleFlashSurface` is still a Phase 1 placeholder, not a real TESPy
      power cycle — this is also what blocks a true end-to-end comparison
      (see above).
    - Dimensionless-time tracking in `NumericalInjectionWell` only advances
      correctly because exactly one `solve()` call happens per timestep today
      (`InjectionPolicy.MANUAL`). Once `AUTO_*` policies add a multi-pass
      outer convergence loop (Phase 2), this needs the old-tango split between
      a per-pass `t_d` recompute and a once-per-timestep `t_d_old` advance —
      flagged in detail in the component's module docstring.
    - No automated test pins any of these numbers down yet (ties into the
      "zero test coverage for `tango_next`" gap noted under Phase 1 tasks
      below) — the comparison above was done by hand in a throwaway script,
      not as a regression test.

---

### Phase 1 — Restructure Input Format & Module Layout

**Goal:** Make the input files, the module structure, and the physical system hierarchy
all congruent with each other.

- **New input file schema:** Each component (e.g. `injection_wellbore`) stores
  all its own attributes, its `component_idx`, and its previous/next
  `component_idx` values. No data at root level. Indices are assigned somewhat
  arbitrarily but increment consistently from a fixed starting point — `component_idx: 0`
  is just the first component solved each pass; it carries no special BC semantics (see
  "Grouped subsystems (composite components)" below for why the BC role belongs to graph
  topology, not a hardcoded index). Hierarchy of data approximately matches hierarchy of
  physical systems.
- **Parallel module tree:** New code structure built alongside (not replacing) the old one
  until verified. `mypy --strict` and `ruff` pass from the first commit.
- **Format converter:** One-way migration tool from old to new input format.
- **Diagrams** -- need to build out diagrams to communicate to management
  how things should be structured and why the new structure addresses the
  shortcomings of the old structure

*Diagram: [New Input File Structure](diagrams/src/phase1_new_input_file_structure.drawio) — open in [draw.io](https://app.diagrams.net) or VS Code draw.io extension.*
*Diagram: [New Module Structure](diagrams/src/phase1_new_module_structure.drawio)*
*Diagram: [Execution Flow](diagrams/src/phase1_execution_flow.drawio)*
*Diagram: [BC Iteration Solver](diagrams/src/phase1_bc_iteration_solver.drawio) — outer BC convergence loop for `flexible_SF_manual.yml`, with power-plant sub-graph inset.*

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
- [ ] Add test coverage for `tango_next` (currently zero — confirmed no `tests/` files reference
    `tango_next` at all). The CLI, orchestrators, and components are functional enough to run
    `flexible_SF_manual.yml` end-to-end under `InjectionPolicy.MANUAL`, but none of it has unit
    tests yet; this should land before more Phase 1/2 functionality is layered on top.

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
  output) for performance-critical runs.  A spatially-distributed state variable (e.g.
  temperature profile along a wellbore axis) is still **one** state variable — its spatial
  dimension is part of the variable itself, not a separate variable per cell.  History therefore
  has shape `[timestep][spatial_cell]` (in Rust terms: `Vec<Vec<f64>>`).  For a lumped
  (0-D) component the inner vec has length 1, so lumped and numerical models share the same
  history structure with no special-casing.
- **Cascading calculations** — computations should propagate down the component hierarchy,
  not be assembled piecemeal at higher levels.  The model is fastsim's
  `SimDrive::solve_step` → `Vehicle::solve_powertrain` → `PowertrainType::solve` → …
  where each level owns its own state and delegates to children; the parent only reads
  child state after the child has solved.  In TANGO terms: `Orchestrator.run_timestep`
  calls `component.solve()`; `SurfacePlant.solve()` calls `PowerPlant.solve()`, which
  calls `Turbine.solve()`, `Pump.solve()`, etc.  Net power is then read upward from
  the fully-solved hierarchy — not assembled by passing lists (`prod_pump_w_list`) or
  adding corrections at a separate economic layer.  This is the fix for the
  `surface.w_net` ≠ economic-layer inconsistency described above.
- **Serialization:** Every TANGO code object gets `to_file` / `from_file` / `to_str` /
  `from_str` methods. Format-agnostic (JSON, YAML, MessagePack, pickle).
- **Round-trip verification (TODO):** `SerdeAPI` is currently a Phase 1 stub
  (`src/tango_next/core/serde.py` — all four methods raise `NotImplementedError`). Once
  it has a real implementation, verify lossless round-trip serialization across every
  supported format pair: deserialize a representative YAML input to an object, serialize
  to each other format (JSON, MessagePack), deserialize back, and assert equality against
  the original parsed object at *every* hop — not just start-to-end, so a lossy
  intermediate format can't hide behind a lucky cancellation. No existing test covers
  this (confirmed: no `round_trip` / `roundtrip` / `serde` references anywhere under
  `tests/`) — needs new test coverage once `SerdeAPI` is implemented.
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

### Future Direction — AI-Assisted Error Interpretation

Simulation errors in TANGO are often opaque: a CoolProp lookup fails because the
requested state is in a two-phase region, a `ConvergenceError` fires after 200 BC
iterations with no explanation of why, a negative outlet pressure appears mid-run
with no pointer to which component produced it. End users — especially those without
a deep background in thermodynamics or numerical methods — are left staring at a
Python traceback with no actionable guidance.

The idea: wrap `tango_next_cli run` in a top-level exception handler that, on any
unhandled error, packages the context and sends it to an LLM agent for interpretation.

**What the agent receives:**
- The full input YAML (the system configuration the user submitted)
- The Python traceback and exception message
- The last-known component states (serialized via SerdeAPI) — what each component
  computed before the failure

**What the agent returns:**
- A plain-English explanation of what went wrong and why
- A concrete suggestion for how to fix it (e.g. "your injection pressure of 45 MPa
  exceeds the fracing threshold of 38 MPa for this reservoir depth — try reducing
  `injection_pressure` in the surface spec, or switch to `mode: auto-pressure` to
  let the solver find a safe value automatically")
- If appropriate, a corrected or adjusted input snippet the user can paste in

**Why this is particularly well-suited to LLM assistance:** The error messages TANGO
produces (and the ones CoolProp and TESPy produce underneath it) are correct but
written for developers, not operators. The mapping from "what the physics failed on"
to "what the user should do about it" is well-defined enough to be reliably produced
by an LLM that has been given the component context — but tedious and error-prone to
hard-code as static error messages.

**Implementation sketch:**

```python
# tango_next_cli.py — outer try/except in the `run` subcommand
try:
    Workflow.from_file(path).run()
except Exception as exc:
    if ai_interpretation_enabled():
        agent_explain(exc, config=raw_yaml, component_states=last_states)
    else:
        raise
```

The `agent_explain` function can be a thin wrapper around the Claude API (or any
capable model) with a system prompt that describes the TANGO component model and
the most common failure modes. It should be opt-in (controlled by a CLI flag or
config setting) so that users who prefer raw tracebacks or who are working offline
are not affected.

**Error taxonomy prerequisite:** For the agent to produce useful output — and for
human debugging — TANGO needs a stable, identifiable set of exception types. The
design follows the same philosophy as Rust's `thiserror` + `anyhow` crates:
typed, catchable errors at library boundaries (`thiserror`-style), with rich
context chained in as they propagate up (`anyhow`-style via Python's
`raise TangoError(...) from exc`).

Concretely: every CoolProp call must be wrapped so that low-level property-lookup
failures surface as a `CoolPropError` (a TANGO-owned subclass of `TangoError`),
not as a raw `ValueError` or `CoolProp.CoolProp.CoolPropError` buried three frames
deep. The same applies to TESPy, which throws its own mix of solver-convergence and
bad-state-point errors: these become `TESPyError` at the TANGO boundary. With this
in place, callers at any layer of the stack can `except CoolPropError` or
`except TESPyError` (or the broader `TangoError`) and know immediately what kind of
failure they are handling — without parsing traceback strings or catching overly
broad base types like `ValueError`.

**Prerequisites:** Phase 2 SerdeAPI (so component states can be serialized at the
point of failure) and a stable set of error types (`ConvergenceError`,
`FracingError`, `SaturationError`, `CoolPropError`, `TESPyError`, etc.) with enough
context attached to be useful.

*Diagram: [Execution Flow](diagrams/src/phase1_execution_flow.drawio) — shows the
AI error agent as a future hook on the right side of the simulation loop.*

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
