# TANGO: Vision & Development Roadmap

## What is TANGO?

TANGO is GEG's geothermal simulation platform. This document describes where TANGO is
heading — both as a product that generates revenue for GEG, and as a software system that
can support that goal reliably.

## Table of Contents

- [Product Vision: Four-Tier Access Model](#product-vision-four-tier-access-model)
  - [Tier 1 — Community / Academic](#tier-1--community--academic-free-or-very-low-cost)
  - [Tier 2 — GEG Consulting Projects](#tier-2--geg-consulting-projects-primary-near-term-revenue)
  - [Tier 3 — Licensed On-Prem Binary](#tier-3--licensed-on-prem-binary)
  - [Tier 4 — SaaS](#tier-4--saas-cloud-web-api--gui)
  - [Licensing Strategy Notes](#licensing-strategy-notes)
- [Technical Roadmap: The TANGO Refactor](#technical-roadmap-the-tango-refactor)
  - [Why TANGO Needs a Refactor](#why-tango-needs-a-refactor)
  - [Resolved Design Decisions](#resolved-design-decisions)
  - [Open Design Questions](#open-design-questions)
  - [Tooling & Process Housekeeping](#tooling--process-housekeeping)
  - [Refactor Phases](#refactor-phases)
    - [Phase 0 — Establish Baseline](#phase-0--establish-baseline-before-touching-any-code)
    - [Phase 1 — Restructure Input Format & Module Layout](#phase-1--restructure-input-format--module-layout)
    - [Phase 2 — Code Objects & State Management](#phase-2--code-objects--state-management)
    - [Phase 3 — Modularity, Verification & Scale-Out](#phase-3--modularity-verification--scale-out)
- [Future Direction — Geospatial Viability Analysis with LLM Augmentation](#future-direction--geospatial-viability-analysis-with-llm-augmentation)
- [Future Direction — AI-Assisted Error Interpretation](#future-direction--ai-assisted-error-interpretation)
- [Future Direction — Performance & Scalability](#future-direction--performance--scalability)
- [The Connection: Refactor Enables the Product Vision](#the-connection-refactor-enables-the-product-vision)
- [Summary](#summary)
- [Appendix A: TESPy Dependency Assessment](#appendix-a-tespy-dependency-assessment)

---

## Product Vision: Four-Tier Access Model

The core idea is to serve a wide range of users — from students and researchers to major
oil and gas operators — through a tiered access model. Each tier unlocks more capability
and generates more revenue for GEG. The consulting/project tier is the **primary near-term
revenue path** and should be treated as such until TANGO's capabilities are robustly
demonstrated.

*Diagram: [Four-Tier Access Model](../archive/diagrams/four_tier_access_model.drawio) — open in [draw.io](https://app.diagrams.net) or in VS Code with the draw.io extension. When this document is ported to Confluence, the diagram file will be attached to the page and embedded inline.*

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

#### Third-party dependency license policy (needs OSS-license-expert review)

Quick, non-legal-advice observations for whoever on the team owns this — not
a decision, just context to speed up that conversation (see also
`tools/check_licenses.py`, which currently flags ~43 dependencies as
"non-compliant," mostly because their license is unrecognized rather than
because they're actually copyleft):

- Standard copyleft (GPL/LGPL) obligations trigger on **distribution**, not
  on internal/SaaS use. For Tier 4 (SaaS), running GPL-licensed dependencies
  server-side without distributing the codebase generally doesn't trigger
  copyleft — **AGPL is the one exception to watch for**, since it explicitly
  extends copyleft to network-accessible use.
- Tier 3 (Licensed On-Prem Binary) is the tier where this actually matters:
  shipping a binary/installer that bundles GPL-licensed dependencies likely
  does count as distribution and can trigger obligations, even though no
  TANGO source is being shared. LGPL is generally lower-risk here (dynamic
  linking/separate-module use typically doesn't require releasing your own
  code, only modifications to the LGPL component itself).
- Permissive licenses (MIT/BSD/Apache-2.0) aren't obligation-free just
  because they're permissive — they require preserving attribution/license
  notices in anything distributed (Tier 3 binaries, Tier 4 doesn't apply).
  Worth having a NOTICE-file process regardless of the copyleft question.
- The biggest immediate risk isn't copyleft — it's the "Unknown" bucket
  (packages whose license `check_licenses.py` can't determine at all). Those
  need to be resolved to *something* before "we're liberal about licenses"
  can be a defensible policy, since an unknown license could be anything.

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

### Resolved Design Decisions

Design questions that have already been settled and (mostly) implemented — kept here as
the record of *why*, not as open items.

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

Orchestrator selection in `tango` is automatic: if `sim_config.injection_mode` is present,
`SystemBCIteration` is used; otherwise `SystemDirect`. No `workflow` key is needed at the
top level.

**This selection is a topology question, not a second encoding of `InjectionPolicy`.**
Early on, `SystemBCIteration` re-implemented the entire single-pass solve loop itself, so
`InjectionPolicy.MANUAL` (one pass per timestep, no correction) ended up functionally
identical to what `SystemDirect` already did — two code paths doing the same thing, picked by
whether a YAML key happened to be present. The fix: `SystemBCIteration` now subclasses
`SystemDirect` and reuses its single-circuit-pass `run_timestep` (one call per pass for
`MANUAL`/`MANUAL_FRACKING_CHECK`, repeated calls inside a Newton loop for `AUTO_*` once Phase 2
lands) instead of duplicating it. `SystemDirect` owns the only implementation of "one circuit
pass" and "loop over timesteps"; `InjectionPolicy` is the sole authority over how many passes
a timestep takes, and never determines which orchestrator *class* is used. Orchestrator choice
remains a topology question — does this graph declare a circuit with a BC variable to solve
for at all (e.g. a bare wellbore test fixture has none and uses `SystemDirect` directly).

The top-level YAML config is split by concern: `common` holds shared physical *parameters*
(fluid, rock properties — not physical constants like Planck's constant), `layout` holds
well-field geometry (`well_spacing`, `well_pattern`), and `sim_config` holds time stepping
and solver/injection control (`num_tsteps`, `dt_years`, `injection_mode`, `mass_rate`). This replaced an earlier
single `schedule` block that mixed all three concerns under a name that only really fit the
time-stepping piece.

The native reservoir model assumes mass conservation: injection rate equals production rate
at every timestep (1D Darcy flow, incompressible fluid). Full reservoir simulators (CMG,
MOOSE) do not make this assumption — they model pressure transients and compressibility,
so inlet and outlet flow rates can differ during transients. This may require a different
solver strategy when a transient reservoir component is used, and is another reason to
resolve the external-tool socket question (see below) before that integration work begins.

#### BC iteration mode — `InjectionPolicy` (replaces `check_fracking` / `manual` / `automatic`)

The current `src/tango/` code controls BC iteration behavior through three separate,
poorly documented fields:

- `mass_rate.type: "manual"` — mass flow rate is user-prescribed
- `mass_rate.type: "automatic"` — mass flow rate is computed from the Darcy fracking limit
- `bc_iteration.check_fracking` — a boolean flag with undocumented scope
- `bc_iteration.max_mass_rate` — a global cap applied after all other rate logic

These fields interact in ways that are not documented anywhere and that are easy to
misread. Worse, they conflate two physically distinct fracking mechanisms.

**Two distinct fracking mechanisms**

1. **Flow-induced fracking** — mass flow rate is high enough that, by Darcy's law, the
   reservoir inlet pressure exceeds the fracking threshold. The `fracking_flow()` function
   computes the maximum sustainable mass rate at which the threshold is exactly reached:

   ```
   fracking_flow = 2πhk × (overpressure% / 100 × hydrostatic_P) / (μ × ln(re / rw))
   ```

   Because µ and ρ depend on injection-side fluid conditions, `fracking_flow()` changes
   as `test_p` changes — making mass rate and injection pressure coupled variables when
   this mechanism is active.

2. **Pressure-induced fracking** — injection wellhead pressure (`test_p`) is set high
   enough that, after hydrostatic head and friction losses in the injection well, the
   reservoir inlet pressure `inj_well.outlet.P` exceeds
   `hydrostatic_P × (1 + overpressure% / 100)`.

These two mechanisms are checked via separate code paths in `src/tango/` but neither is
clearly labeled. `check_fracking` guards only the flow-rate cap; the injection pressure
adjustment (`test_p` update) runs regardless of the flag.

**Why two separate checks at all, rather than one combined constraint?** Both mechanisms
ultimately bound the same physical quantity — reservoir inlet pressure — so it's fair to
ask why `InjectionPolicy` (and `src/tango/` before it) doesn't just treat "reservoir inlet
pressure exceeds the fracking threshold" as a single check. The answer is architectural, not
physical: TANGO uses an **explicit** solver that marches through the well/reservoir/surface
loop component by component, one pressure/temperature calculation at a time, each step
consuming the previous step's output as its input (`test_p` → injection well friction/head
loss → reservoir inlet pressure → …). Mass rate and injection pressure are two separate
inputs to that march, entering the loop at different points and via different physical
relationships (Darcy flow vs. wellbore hydraulics) — so from the solver's point of view they
are two distinct things that each need their own check, applied wherever they enter the
calculation. An **implicit** solver — one that solves the well/reservoir system as a single
coupled set of equations simultaneously, rather than marching step by step — would have no
such distinction to make: reservoir inlet pressure would just be one term in that combined
system, bounded by one constraint, regardless of whether flow rate or wellhead pressure (or
both) happened to be pushing it there. The two-mechanism split in `InjectionPolicy` is a
direct consequence of TANGO's explicit, stepwise architecture, not a fact about the
underlying physics — worth keeping in mind if TANGO ever moves toward an implicit
formulation (see Phase 2's Newton-step BC iteration, which is a step in that direction for
the outer loop, though the inner per-component march remains explicit). See
[`docs/implicit_solver_exploration.md`](../implicit_solver_exploration.md) for an exploration
of what adopting a residual/Jacobian-based implicit solve (in the style of tespy's Newton
network solver) would take, and why the fracking switch itself is the hard part rather than
the solver mechanics. See also
["Future Direction — Subsurface as TESPy Components"](#future-direction--subsurface-as-tespy-components-fully-implicit-solve)
below for the longer-horizon version of this idea (subsurface joining the same TESPy
network as the surface plant).

**`InjectionPolicy` — the clean replacement**

In `tango`, both concerns are unified into a single enum that makes every operating
mode self-documenting. The YAML field is `sim_config.injection_mode`. Note that
`sim_config.mass_rate` is only meaningful for policies where flow rate is user-prescribed
(`MANUAL`, `MANUAL_FRACKING_CHECK`, `AUTO_PRESSURE`); for `AUTO_FLOW` and `AUTO_BOTH` it is
computed from `fracking_flow()` each pass, so the field may be omitted entirely under those modes.

```python
class InjectionPolicy(enum.StrEnum):  # tango.core.policies
    """Controls how mass flow rate and injection wellhead pressure are determined."""

    MANUAL = "manual"
    """Both mass flow rate and injection wellhead pressure are user-specified.
    No fracking check is performed. Single solver pass per timestep."""

    MANUAL_FRACKING_CHECK = "manual-fracking-check"
    """Both user-specified. Both fracking directions are checked; any violation
    raises an error. Injection pressure is reduced if the initial value would
    cause pressure-induced fracking; rate is capped if it would cause
    flow-induced fracking. Single solver pass per timestep."""

    AUTO_PRESSURE = "auto-pressure"
    """Mass flow rate is user-specified. Injection wellhead pressure is iterated
    until the reservoir inlet pressure converges to the fracking threshold
    (Newton step: test_p += target_reservoir_P - inj_well.outlet.P).
    If the converged state would also cause flow-induced fracking, an error
    is raised."""

    AUTO_FLOW = "auto-flow"
    """Injection wellhead pressure is user-specified. Mass flow rate is iterated
    to the Darcy-law fracking limit (fracking_flow()) each pass. Because fracking_flow()
    depends on injection-side fluid properties, the rate co-evolves with pressure
    until both stabilize. If the converged state would cause pressure-induced fracking,
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
`MANUAL_FRACKING_CHECK` if the specified rate is already below the cap.

**Current implementation status (confirmed 2026-06-16):** only `MANUAL` is implemented in
`tango` today — a single circuit pass, no correction of any kind. `MANUAL_FRACKING_CHECK`,
`AUTO_PRESSURE`, `AUTO_FLOW`, and `AUTO_BOTH` all raise `NotImplementedError` from
`SystemBCIteration.run_timestep` (Phase 2 work). In particular, `AUTO_BOTH` — which jointly
manipulates both mass flow rate and injection pressure — is confirmed to raise
`NotImplementedError` rather than silently doing something wrong; this should hold until the
joint Newton update rule described above is actually implemented.

**Future direction — whole-horizon optimization (`MIN_LCOE` and friends):** `AUTO_PRESSURE` /
`AUTO_FLOW` / `AUTO_BOTH` solve a *per-timestep* physical constraint (find the BC variable(s)
that keep the system at the fracking threshold *this timestep*). A `MIN_LCOE` variant is a
different kind of problem: LCOE is a whole-horizon objective — it depends on cumulative energy
output and cost across every timestep in the simulation, not on any single timestep in
isolation. Minimizing it means searching over decision variables (e.g. constant `mass_rate`
and/or `test_p` setpoints, or eventually time-varying schedules) and re-running the *entire*
multi-timestep simulation as the inner evaluation of an outer constrained optimizer — much
closer in shape to the existing `optimizerr.py` / `pymoo` machinery in `src/tango/` than to the
per-timestep Newton loop in `SystemBCIteration`. Constraints would be the same fracking limits
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
| `type: manual, check_fracking: False` | `MANUAL` |
| `type: manual, check_fracking: True` | `MANUAL_FRACKING_CHECK` |
| `type: automatic` (standard, non-Hotmaps) | `AUTO_BOTH` (test_p and mass_rate co-evolve each iteration) |

In HotmapsDispatch mode, `type: automatic` has more complex behavior: early timesteps
use a specified rate with an optional fracking cap (similar to `MANUAL_FRACKING_CHECK`),
while later timesteps either use `fracking_flow()` or iterate mass flow rate to hit a
target thermal power output (`controlled_power_generation: yes` — note that `src/tango/`
checks this with a `== "yes"` string comparison, so `True` silently does nothing there).
This is a distinct operating mode not yet represented in `InjectionPolicy` and should be
designed as its own variant when the Hotmaps feature is migrated to `tango`.

**Planned future variants**

`InjectionPolicy` is intentionally scoped to injection control rather than just fracking
prevention, leaving room for variants that optimise operating objectives:

- `MAX_NET_POWER` — iterate mass flow rate and injection pressure to maximise
  `gross_power − pump_parasitic_load`, subject to the fracking limit as a hard constraint.
- `MIN_LCOE` — similar, but objective is levelised cost of energy over the project lifetime.
  Note: the decision-variable vector for `MIN_LCOE` isn't necessarily limited to
  `InjectionPolicy`'s own variables (`mass_rate`, `test_p`) — see "Extraction pressure as
  an independent policy axis" below, which argues `target_extraction_pressure` is a third,
  independent variable a whole-horizon optimizer may also need to search over.

These require the Phase 2 Newton-step solver infrastructure and the pump electricity
accounting fix to be in place before they can be meaningfully implemented.

*Diagram: [BC Iteration Solver](../archive/diagrams/phase1_bc_iteration_solver.drawio) — shows
current modes and which trigger the outer convergence loop.*

### Open Design Questions

Design questions not yet settled — flagged here so the reasoning behind them doesn't
have to be re-derived each time they come up.

#### Extraction pressure as an independent policy axis

`sim_config.injection_mode` and `sim_config.mass_rate` govern the injection-side BC:
finding the flow rate and/or injection wellhead pressure needed to prevent fracking.
But `SystemBCIteration`'s own module docstring documents a second, independent
sub-problem: the production-pump inner loop that finds `dP_pump` needed to hit
`target_extraction_pressure` at the surface inlet. As of 2026-08-10,
`target_extraction_pressure` is a single fixed value on `sim_config` — threaded by
reference to both the surface component and any pump-bearing production well via
`_build_components`'s `layout_extras` mechanism (fixing a real bug where it used to
be two independently-set, unvalidated copies — see `docs/bugs-fixed-in-tango.md`) — but the
pump-loop physics itself (the real Newton-Raphson solve old tango does, finding
`dP_pump` such that the whole circuit is pressure-consistent — see below) is not yet
implemented; tango's pump-bearing wells currently apply this value directly as
a fixed target rather than solving for it. These two concerns (injection control,
extraction control) should also be independently configurable rather than folded
into a single key — that part of this section's proposal still stands.

**Proposed design (Phase 2+):** introduce a sibling `extraction_control` block in
`sim_config` housing `target_extraction_pressure` and a parallel `ExtractionPolicy` enum.
Both `injection_mode`/`mass_rate` and `extraction_control` are boundary-condition concerns
— one at the injection wellhead, one at the surface inlet from production — and should be
independently selectable.

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

CMG, MOOSE, DWSIM, Bruce's RAFT, and similar external simulators need to be integrated at some point. The
current code treats this as an orchestrator-level concern (`SystemExternal`). An alternative
view is that these are best modeled as **reservoir components** (or surface components, for
DWSIM) — they implement the same interface as any other component, but delegate computation
to an external process. Under this model, the orchestrator stays clean and the external
coupling is entirely encapsulated in the component adapter.

This question — whether external tools are orchestrator add-ons or component adapters (or
both) — needs careful thought before the integration work begins. The architecture decision
should drive the socket design, not the other way around. Leave this as an explicit open
question until there is a concrete use case to design against.

Whichever shape wins, the goal is the same: `tango` should define a stable interface
template (an ABC any component — reservoir, well, or surface — can implement) so that
outside simulation tools can be plugged in as drop-in components rather than requiring
bespoke orchestrator changes each time. Composability, not a growing list of one-off
integrations, is the intended long-term pattern for CMG/MOOSE/DWSIM/RAFT and whatever comes
after — see "Connect other simulation tools" (roadmap tracker) for the concrete initial
list. **Bruce's RAFT is confirmed in scope.** The rest of the list is still TBD as of
2026-07-26 — currently named candidates are RAFT (confirmed), MOOSE, METRO, CMG, and DWSIM,
but the final set hasn't been decided.

Speculative, longer-horizon thinking on whether TESPy's causal-solve architecture is even the
right foundation for this kind of external-simulator composition lives in
`docs/long_term_architecture_exploration.md` (Modelica-family tooling) — parked, not planned.
A follow-up implementation spike (Rumoca + MSL) is in `docs/modelica-investigation.md`.

#### AGS needs a bespoke depth concept, not a borrowed "reservoir depth" (Phase 2+)

`src/tango/units/native/surface/flexible_pp.py`'s `validate_custom()` estimated the
temperature the working fluid reaches before entering the surface plant as
`surface_temperature + reservoir["reservoir_depth"] * thermal_gradient`. This is a
correct estimate for EGS/CPG (reservoir-based) topologies, but it hardcoded a lookup
into a `reservoir` block that doesn't exist for AGS — a sealed closed loop with no
reservoir node at all. The result: the direct-heat (`native_flexible`) surface unit
could not run on any AGS topology in `src/tango/` (`KeyError: 'reservoir'` at unit
construction — see `applications/run_AGS_direct_heat_sweep/run_AGS_direct_heat_sweep.py`
NOTES for the full incident writeup and the pragmatic patch applied there).

The underlying physical quantity — "depth at which the fluid reaches its hottest
point before returning to surface" — is real and meaningful for AGS too; it's just
the depth of the horizontal loop, i.e. `horizontal_well.wellhead_depth`. Despite the
name, this is *not* the depth of a literal surface wellhead (0 m) — in this
codebase's convention it's the depth below surface at which the horizontal segment
begins, used identically to `reservoir_depth` (`T0 + h * thermal_gradient`) in
`horizontal_well.py`. So the substitution is physically sound, but the name
`wellhead_depth` is itself confusing independent of the reservoir/no-reservoir
question — a second, smaller naming bug layered on top of the first. The
`src/tango/` issue is that "depth of the subsurface heat-pickup point" was only
ever named/looked-up as `reservoir_depth`, so the code silently assumed every
topology has a reservoir.

For `tango`, this argues for an AGS-bespoke depth/temperature-estimate concept
(e.g. a `heat_pickup_depth` property computed per-topology, or resolved generically
by asking whichever component sits between injection and production for "the depth
its outlet temperature estimate should use") rather than a single hardcoded
`specs["reservoir"]["reservoir_depth"]` lookup shared across all surface units.
`tango`'s component-based design (each component owns its own state/specs
dataclass — see `LockedState`, `NumericalProductionWell`/`NumericalInjectionWell`,
`LumpedReservoir`) makes this easy to get right: the surface unit should ask the
upstream subsurface component(s) for this estimate rather than reaching into a
specific node name that may not exist.

#### `tango` example coverage matrix — one system type needs both a heat and a power example

As of 2026-09-23, `example_configs/` covers five cells of a larger matrix:
Single-Flash hydrothermal (power, `hydro_sf_electric.yml`), AGS direct-heat
(heat, `AGS_direct_heat.yml`, ported from `applications/run_AGS_direct_heat_sweep/`),
EGS direct-heat and power (heat, `EGS_direct_heat.yml`; power,
`EGS_electric.yml`; both ported from `applications/run_EGS_direct_heat_sweep/`),
and CPG power (`CPG_electric.yml`, ported from old tango's
`examples/CPG_num_pp.yml` — preserved at git tag
`pre-tango-core-rename-2026-09-18` — simplified from its 6-pattern
INVERTED_5SPOT field to a single doublet, same as the AGS/EGS ports). CPG's
surface plant is a genuinely new topology, not just a fluid-name swap:
`FluidState`/`fluid_utils.py`/`GraphSurface` were already fluid-agnostic
(`common.fluid_name` threaded everywhere already, no hardcoded water found).
CPG's real work was matching old tango's actual physics: CO2 stays
supercritical/dense-phase through the subsurface and turbine, then
condenses afterward at an ambient-driven condensing pressure (same
phase-change-anchored mechanism the water cycle's own condenser uses) —
an earlier version of this file held CO2 supercritical the *entire* way
through, which had no physical anchor for the turbine/condenser outlet
pressure and masked a real thermosiphon-related bug. Depth, injection
pressure, pump efficiency, and economic `project_maturity` were all
matched directly against old tango's converged/actual values (confirmed
by running `CPG_num_pp.yml` itself), not re-derived from scratch. The
full matrix TANGO needs to demonstrate, one worked example per cell:

|                  | Heat extraction         | Power extraction           |
|------------------|-------------------------|----------------------------|
| AGS              | ✓ `AGS_direct_heat.yml` | ☐                          |
| CO2-AGS          | ☐                       | ☐                          |
| EGS              | ✓ `EGS_direct_heat.yml` | ✓ `EGS_electric.yml`       |
| CO2-EGS          | ☐                       | ☐                          |
| CPG              | ☐                       | ✓ `CPG_electric.yml`       |
| Hydrothermal     | ☐                       | ✓ `hydro_sf_electric.yml`  |

Each cell should be a real, runnable `tango` YAML — not just a config that
happens to parse, but one whose output has been sanity-checked (as
`AGS_direct_heat.yml` and `hydro_sf_electric.yml` were) against expected physical
behavior. `GraphSurface`'s YAML-graph-driven design (see
`components/surface/graph.py`) should make most of these a matter of composing a
new `power_plant.nodes`/`edges` topology and tagging the right nodes
`role: net_electric` / `role: net_thermal`, rather than new Python — EGS and
hydrothermal share `LumpedReservoir`. **Correction, 2026-09-21**: this
section previously claimed CPG needed a CO2 `FluidState` path that didn't
exist yet (H2O-only) as "likely the largest gap in this matrix" — checked
while building `CPG_electric.yml` and found that's stale: `FluidState`,
`fluid_utils.py`, and every component that touches fluid properties
already thread `common.fluid_name` generically (no hardcoded water
anywhere), and CoolProp's CO2 support works out of the box. Whatever made
this claim true earlier was apparently resolved as a side effect of other
generic refactoring, without this doc being updated. The remaining CO2
cells (CO2-AGS, CO2-EGS) are likely comparably tractable YAML-authoring
work, same shape as AGS/EGS/CPG above, not a physics gap.

**`GraphSurface`'s fixed `p_out` values — why this is a legitimate modeling choice, not a
shortcut.** Raised 2026-07-22 while tracing where `hydro_sf_electric.yml`'s TESPy plant
states are solved versus imposed (see `docs/archive/diagrams/graph_surface_state_provenance.drawio`
for the full node-by-node breakdown). `GraphSurface` fixes two independent pressures per
plant — flash pressure (the valve ahead of the droplet separator) and condensing pressure
(shared by the turbine's and condenser's outlets, i.e. zero ΔP assumed across the condenser)
— as YAML constants rather than deriving them from a resistance/flow relationship. This is
not a `tango`-introduced simplification: `src/tango/`'s `flexible_pp.py` does the exact
same thing (`p_out` as a bare fixed constant, same units convention). The justification: both
are genuine real-plant control targets, not passively-emergent quantities. Flash pressure is
routinely chosen by plant designers/operators to maximize power extraction for the delivered
brine enthalpy (that choice *is* the single-flash design problem); condensing pressure is set
primarily by the cooling system (ambient temperature via the cooling tower, `approach_temperature`
— see the diagram for why that field is currently a no-op in `GraphSurface`'s condenser, only
feeding a not-yet-ported parasitic-power calc), which changes on daily/seasonal timescales far
slower than turbine/pump power modulation.

Concretely, today, a condenser's fixed `p_out_megapascals`/`T_out` YAML values are NOT derived
automatically from `approach_temperature` at solve time — nothing in `GraphSurface` reads that
field to compute them. Instead, whoever authors the config computes the target condensing
temperature by hand (`<ambient/surface temperature> + <approach temperature difference>`),
converts that to a saturation pressure for the working fluid, and hardcodes the result directly
into the node's `p_out_megapascals`/`T_out` fields. `approach_temperature` itself is only read
later, by the economic component's cost/parasitic-power regressions — nothing enforces that a
config's hardcoded condenser values actually stay consistent with its own
`common.surface_temperature`/`approach_temperature` fields if either one is edited afterward.

So treating these two pressures as externally-imposed
setpoints is defensible as a first-order approximation — but only self-consistently if the
chosen values are actually calibrated to the site's assumed ambient/well conditions, and nothing
currently checks that (see the diagram's risk callout). A rigorous *quantified* error estimate
for "how wrong is this relative to treating pump power as the real state variable" would need
either a resistance-closed alternative formulation to diff against, or real plant operating data
— neither exists yet; this paragraph documents the qualitative justification only, not a
validated bound.

Two known, tracked-but-not-yet-addressed gaps in this area (see `docs/tango_tasks.md`):
old tango's `src/tango/units/native/surface/flexible_pp.py::validate_pressure_monotonicity()`
(walks the power-plant graph upstream from each `p_out`, stopping at `Pump`/`Compressor`
boundaries, raises on non-monotonic pressure) has no `tango` equivalent yet — **correction,
2026-09-22:** this file no longer exists in the working tree; old tango's `src/tango/` was
deleted in the 2026-09-18 internal-release cleanup and is only recoverable via
`git show pre-tango-core-rename-2026-09-18:src/tango/units/native/surface/flexible_pp.py`,
same as the other old-tango references already flagged stale elsewhere in this doc; and
`AGS_direct_heat.yml`'s `dh_hx` node is a sharper version of the same risk with no `p_out`
field to even inspect (its pressure is implicitly whatever gap exists between two unrelated
boundary conditions — see the diagram).

**Beyond the matrix — port the broader set of old-tango examples that actually run.**

> **Moot as of 2026-09-18:** old tango's `examples/` directory and
> `REPO_CLEANUP_AUDIT.md` (the categorization this whole subsection relies
> on) were both deleted in the internal-release cleanup — there's nothing
> left to port *from*. Both are preserved at git tag
> `pre-tango-core-rename-2026-09-18` if this ever needs revisiting. The
> rest of this subsection is left as historical reasoning, not pruned —
> revisit/trim at your discretion.

The 8-cell matrix above is the minimum canonical set, not the target. `src/tango/`'s
`examples/` directory has many more real variants that don't map cleanly onto one
matrix cell — different well layouts (`doublet`, `inverted`), file-driven schedules
(`file_reader_*`, `*_reader.yml`), cost-reporting modes
(`flexible_pp_cost_entire.yml`/`_breakdown.yml`), multi-objective optimization sweeps
(`MO1-4.yml`, `SO1-4.yml`), and more. These are real coverage, and Phase 3's existing
"work through all remaining TANGO input file configurations" task already calls for
this — the addition here is a concrete scope: port *as many as are reasonable*, meaning
work from `REPO_CLEANUP_AUDIT.md`'s categorization of what's actually running in old
tango, not every file that happens to exist under `examples/`. As of the 2026-07-20
sweep (`tools/examples_sweep_output/sweep_20260720_101252.md`) that's **58 confirmed
`PASS`**, plus **~10 more confirmed fine and just slow** (see
`REPO_CLEANUP_AUDIT.md`'s `TIMEOUT` backlog section — genuinely completes, just needs
a longer budget than the sweep's default 300 s). Explicitly exclude, without spending
more effort re-litigating them here, the two backlog buckets `REPO_CLEANUP_AUDIT.md`
already documents as blocked or broken: `EXPECTED_FAIL` configs blocked on external
dependencies (MOOSE, PyQt5, the deprecated `BatchSimulation` feature, a hardcoded
Hotmaps dispatch path) and the ~14 `flexible_DF_*`/optimization configs that still
time out even at a 900 s budget (worth investigating as a possible real solver bug in
`src/tango/`, but that's a `src/tango/` question, not a porting-priority one).

**Combined heat-and-power (cogeneration) — separate, harder problem, needs design
discussion before examples:** `src/tango/` *does* have precedent —
old tango's `flexible_SF_cogeneration_e.yml` / `flexible_SF_cogeneration_h.yml`
(removed along with old tango; preserved at git tag
`pre-tango-core-rename-2026-09-18`) split
the droplet separator's liquid branch to a district-heating `SimpleHeatExchanger`
while the vapor branch still drives the turbine, extracting both products from one
plant simultaneously. So this isn't undesigned territory in old tango, and
`GraphSurface`'s `role: net_electric` / `role: net_thermal` tags already support
tagging both kinds of node in the same topology with zero new code — the open
question is entirely on the economic side: `MainProduct` (`core/policies.py`) is
currently a single either/or LCOE-or-LCOH switch on `EconomicComponent`, and
combined heat-and-power needs a real answer for how a *combined* levelized cost
(or two separate ones reported side by side) should be computed and compared
against old tango's cogeneration examples — that discussion should happen before
building a `tango` cogeneration example, not as a side effect of building one.

**Seasonal heat-demand variation — a real gap, not just a cogeneration concern:**
every direct-heat example checked (`src/tango/`'s `flexible_heat.yml`, both
cogeneration examples above, and `tango`'s new `AGS_direct_heat.yml`) runs
with a constant mass flow rate for every timestep (`mass_rate: {type: manual}`,
`ConstantDT` time stepping) — production, and therefore heat delivered, never
varies with a demand curve. District heating demand is strongly seasonal in
reality (dominated by outdoor temperature), so a plant sized against a flat annual
average will be badly oversized for summer and possibly undersized for winter
peak — a real result-invalidating gap for any heat-focused example, not only the
combined heat-and-power case above.

`src/tango/` does have *a* precedent elsewhere in the codebase, but it's not used by
`applications/run_AGS_direct_heat_sweep/` (confirmed by grep — that app never
references "Hotmaps"; `sweep.py`'s only touch on mass rate is
`set_nested_value(specs, "schedule.mass_rate.value", mdot)`, a constant per sweep
design point, not a per-timestep demand curve) and it's heavier than a simple
seasonal profile: `time_type: HotmapsDispatchDT` (`orchestrators/BC_calculator.py`,
`orchestrators/HotmapsDispatch_runner.py`) reads an external, pre-processed demand
time series (`self.processor.averaged_df`) from the EU Hotmaps district-heating
tool and iterates mass rate each timestep to follow it via
`controlled_power_generation`. This is tightly coupled to the Hotmaps desktop app
integration (Excel generation, a Windows-path trigger file) — already flagged as
one of the fragile, externally-dependent pieces in the repo cleanup backlog (see
`REPO_CLEANUP_AUDIT.md`), not something to port as-is.

`tango` has no equivalent yet — `sim_config.mass_rate` is a single scalar for
the whole run. Before either pure-heat or cogeneration examples can be considered
representative rather than illustrative, this needs a design discussion: at
minimum, a much lighter-weight generic demand-profile mechanism (e.g. a per-timestep
mass-rate *or* target-thermal-power schedule read from a plain CSV/array, decoupled
from any specific external tool) that both the pure-heat and cogeneration cases can
share, distinct from the InjectionPolicy machinery (which governs the injection
*pressure* BC, not the production-side demand target).

This gap is now flagged directly in `applications/run_AGS_direct_heat_sweep/
run_AGS_direct_heat_sweep.py`'s module docstring (item 5), rather than only
here, so it isn't missed by someone reading that app in isolation. It applies
equally to `applications/run_AGS_sweep/` — the power-generation counterpart of
that app, covering the same (depth, mass-flow, loop-length, loop-diameter)
design space via old tango's `AGS_new/AGS_H2O_webapp_native.yml`'s
(removed along with old tango; preserved at git tag
`pre-tango-core-rename-2026-09-18`) validated ORC
surface plant instead of the direct-heat DH exchanger — for any variant of it
that targets a thermal or cogeneration product rather than pure electricity.

#### Pump electricity accounting — known inconsistencies (needs HIL verification)

**⚠ Human-in-the-loop (HIL) verification required before relying on net power or LCOE
outputs from `src/tango/`.  The summary below is based on static code analysis and may
contain errors — the original codebase is complex enough that misreading a sign convention
or a code path is easy.**

Concrete evidence this matters, found while running the Triemli AGS direct-heat sweep
(`applications/run_AGS_direct_heat_sweep/`, see that script's NOTES): 53/500 swept
designs — all clustered right at the district-heating return temperature (~50-51°C,
i.e. barely-functional loops) — reported `Net_thermal_power_Generated_kWe` as negative,
which the native LCOE formula (`CAPEX / net_power`) then turns into a deeply negative
"cost" (as low as -180 $/kWh_th). Whether the underlying negative net power is itself
correct (parasitic pumping genuinely exceeding delivered heat is physically plausible
for a barely-functional loop) or a sign/accounting bug is unresolved and should be
checked together with the table below, not in isolation.

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

In `tango` Phase 1, no pump electricity is wired to an `EconomicComponent` yet —
placeholders with `TODO (Phase 2)` notes throughout.

Phase 2 should:
- Verify the table above with HIL testing on representative configs
- Fix the CPG production downhole pump gap in `src/tango/`
- Reconcile `surface.w_net` with the economic-layer value so there is one authoritative
  net-power number per timestep (see cascading calculation principle below in Phase 2)
- Wire `pump_power_watts` from all tango wellbore components into the economic component

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

**Planned new GUI/web tool, built on the example scripts as a template.** Using the
fleshed-out `tango` example scripts (see Phase 3 tasks) as its foundation, the new
tool should:
- Store graphical annotations (component positions, connection lines) directly in the
  `tango` config files, so all config — simulation and graphics — lives in one place
  (this generalizes the "store web app lines and graphics as annotations" Phase 3 task
  below into the tool's actual design basis, not just a data-format fix)
- Let users build custom models and configure component connections graphically, not just
  view existing ones
- Save run configuration and, for simulations that have already been run, their
  corresponding results
- Perform batch simulations (sweeps) from the GUI, not just single runs
- Export a model/simulation configuration to an equivalent script, so a GUI-built model can
  be handed off as ordinary `tango` Python/YAML rather than staying GUI-locked

This is a superset of the Tier 4 "no-code scenario builder" concept above — the near-term
goal is a general modeling/scripting-bridge tool, not only a SaaS-tier feature.

#### Grouped subsystems (composite components)

*Mostly implemented already — kept under "Open" because two concrete gaps remain
(flagged below), not because the core design is undecided.*

The `surface` component in `tango` already has a nested `power_plant:` block with
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

**Partially closed, one gap remains:** an earlier version of this doc described
`component_idx: 0` as a hardcoded stand-in for "the BC checkpoint," tied to the surface
happening to sit at index 0. That's no longer true: `sim_config.bc_checkpoint_idx` is now
an explicit, independent config field (`Workflow` → `SystemBCIteration.bc_checkpoint_idx`
→ `_find_surface()`), decoupled from `component_idx`. In fact `component_idx: 0` is now the
*injection well* in `hydro_sf_electric.yml`/`AGS_direct_heat.yml` (the circuit-entry point,
matching old tango's solve order), with the surface deliberately solved *last* each pass so
it sees the current-timestep production well output rather than the previous timestep's
stale value (see Phase 0's reservoir-depletion walkthrough below for the full 1-step-lag
fix), while `bc_checkpoint_idx: 4` (or `3` for the AGS example) points at the surface
separately. So the BC-checkpoint identity is already a real, named property rather than a
magic index — that part of the original gap is closed.

What's still open: the power plant sub-graph parsing (`GraphSurface`'s `power_plant.nodes`/
`edges`) is still bespoke rather than going through a generalized `GroupedComponent` path,
and the *outer* graph's own topology detection (DAG vs. loop, i.e. whether a graph needs
`SystemDirect` or `SystemBCIteration` at all) is still driven by whether
`sim_config.injection_mode` is present, not yet by walking the actual Source/Sink structure
of the component graph the way the `GroupedComponent` design above describes. Closing this
remaining gap is a Phase 3 task.

**Open consideration, not decided: `next`/`prev` sugar for binary split/merge.** Raised
2026-07-22 discussing `GraphSurface`'s `power_plant.nodes`/`edges` schema versus the outer
graph's per-node `component_idx`/`prev`/`next` fields. The outer graph is a strict chain (one
`prev`, one `next` per node, doubling as the orchestrator's sequential solve order), so a
scalar field suffices; the TESPy plant graph branches and merges (`DropletSeparator`'s
liquid/vapor split, `Merge`'s two inlets), so `GraphSurface` uses an explicit `edges:` list
with named `source_port`/`target_port` instead. For every topology in the repo today, the
branching is binary, so a `next`/`next_alt` (defaulting to `out1`/`out2`) and `prev`/`prev_alt`
(defaulting to `in1`/`in2`) convention on each node could plausibly give the same
self-contained-per-node readability the outer graph has, without a separate `edges:` block.
The real limitation: TESPy's two-stream `HeatExchanger` (registered in `_COMPONENT_TYPES`,
unused so far) needs two independent in/out pairs, not one primary + one fallback — that case
would need `next_1`/`next_2` generalization, which re-derives explicit port identification
piecemeal rather than the single `source_port`/`target_port` string `edges:` already provides
generically. A hybrid (sugar for the common binary case, `edges:` as an explicit fallback for
anything that doesn't fit) is the leading idea, not yet built. Relatedly, the same argument
for generality is prompting a reconsideration of whether the *outer* subsurface graph should
also move to an explicit `edges:` block instead of per-node `prev`/`next` — parked, not started,
but flagged here as in play for future robustness against topologies not yet anticipated.

#### Object-oriented per-component economics — capex/opex/periodic cost tiers (alternative to a centralized economic component) — parked, needs careful thought

Raised 2026-08-17 while fixing `DoubletEconomicComponent`'s (`components/economic/
doublet.py`) well-costing logic (it was crashing on `opt_AGS_direct_heat`'s
independently-swept horizontal-loop diameter — see `docs/tango_tasks.md`'s
PAUSED entry for that specific bug). The proposal: instead of one centralized
economic component that reaches into `WellComponent`/`SurfaceComponent` internals
and re-derives assumptions about which fields mean what, give each component its
own `capex()`/`opex()` method (own economic assumptions living next to its own
physics), and have a top-level recursive function walk the component tree
collecting from every component that implements this interface/trait — the same
shape as `save_state`'s mixin pattern.

**Refinement, 2026-09-21: the per-component interface should be three cost
tiers, not two.** `capex()`/`opex()` alone can't express a real cost that
recurs on a multi-year cadence rather than every year — e.g. a workover, a
major equipment refurbishment/replacement, a well re-stimulation. Today's
centralized `DoubletEconomicComponent` can't express this either: `OPEX`
(`_compute_opex`) is a single flat `f_om * CAPEX_total` scalar, uniform for
every year of the project — there is no periodic-cost concept anywhere in
tango's economic model today, independent of whether the object-oriented
refactor happens. So the per-component interface this section proposes
should be three methods, not two:

- `capex()` — one-time startup cost (unchanged from above).
- `opex()` — cost incurred every year (unchanged from above).
- a periodic-cost method — cost incurred every *N* years (the period being
  a per-component/per-cost-item parameter, e.g. "$X every 7 years" for a
  workover) — new, doesn't exist in any form today.

The aggregator (whichever shape it ends up taking — the tree-walk sketched
below, or the centralized component) needs a notion of *which year* it's
computing for to evaluate the periodic term (`year % N == 0`), which neither
`capex()` nor `opex()` need — `_total_project_years` already exists
(`DoubletEconomicComponent._total_project_years`) but is only ever used as a
single scalar (the CRF/discounting term over the whole horizon), never
walked year-by-year. Whether periodic costs get discounted-and-summed
analytically (closed form, like CRF) or need an actual per-year loop is
itself an open question the eventual design needs to answer, not something
this note resolves.

**Chad's call for now: keep the current centralized-component structure** — it's
a reasonable way to represent the economic data as it exists today, and the
concrete, narrower fixes already in flight (the gengeo formula's three
coefficients as overridable config fields, splitting horizontal-loop costing out
of the vertical-production-well combination) don't need to wait on this larger
question. This is filed here as a genuine future variant worth reconsidering
later, not a rejected idea.

**Where the object-oriented framing clearly wins:** the well-costing bug above
exists *because* the economic component has to inspect `WellComponent` internals
(e.g. `angle_from_vert_deg`) from the outside to decide how to cost each one. If
`NumericalWell` instead owned its own `capex()`, it could cost itself correctly
using its own fields directly — no external dispatcher guessing at geometry.

**Where it doesn't fully dissolve, and needs real design before it's adopted:**
the gengeo formula's fixed mobilization cost is charged once per physical
wellbore, but a single wellbore is sometimes split across multiple `Component`
instances (e.g. `production_well_lower` + `production_well_upper`) for physics/
solve-order reasons unrelated to economics. A flat "sum every component's own
`capex()`" doesn't know these two components represent one economic asset, so
something still has to prevent double-charging mobilization — that knowledge
doesn't vanish by moving the formula onto the component, it just needs a new
home (e.g. components declaring which economic "asset group" they belong to, an
aggregator that groups before invoking a per-group formula). **This may compose
well with the "Grouped subsystems (composite components)" design directly above**
— a `GroupedComponent` wrapping `production_well_lower`/`production_well_upper`
as one nested black box could plausibly expose ONE `capex()` for the whole group,
which would resolve the double-counting problem for free rather than needing a
separate asset-grouping mechanism. Worth designing together, not independently,
whenever this is picked up. The same double-charging risk applies to the
periodic-cost tier above — a workover charged per physical wellbore would
double-count across `production_well_lower`/`production_well_upper` exactly
the way mobilization cost does, for the same reason; whatever asset-grouping
mechanism resolves it for `capex()` should cover the periodic tier too, not
be designed against `capex()` alone.

Also unresolved: the surface-plant cost path is computed from averaged TESPy
**node** history (turbine/pump/cooler power/heat duty), not from tango
`Component` attributes at all — it's not obvious this joins a per-component
`capex()` interface cleanly regardless of which design wins. Permitting/
exploration costs are pure project-level constants with no component to attach
to either. So even under the object-oriented design, some central economic logic
almost certainly survives — this becomes a smaller aggregator plus a real
per-component interface for wells, not a total replacement.

---

### Tooling & Process Housekeeping

Process/tooling gaps — not design questions about TANGO's physics or architecture,
but real items that need a decision eventually.

#### Unit conversion constants module

All unit conversions should be handled via constants imported from a
module defining unit conversion constants and physical constansts, e.g.
`p_out_kilopascals = p_out_megapascals * 1_000` should be
`p_out_kilopascals = pascals * MEGA_TO_KILO`

#### API documentation toolchain (currently dormant)

A 2026-07-16 repo cleanup audit found the Sphinx API-doc toolchain
(`source/`, `.readthedocs.yml`, `make.bat`, `tox.ini`'s `docs` env) dormant
and broken — `.readthedocs.yml` pointed at a `docs/conf.py` that didn't
exist — and removed it rather than fix it. We still need a real process for
generating API docs from `src/tango`/`src/tango` (whether that's a
revived Sphinx setup, mkdocs, or something else) rather than leaving it
undecided.

---

#### CI test subset — `tests/regtest/` doesn't fit in the GitLab runner timeout

As of 2026-07-16, the GitLab CI `test` job ran the full `pytest` suite and was
killed after exceeding the 1h runner timeout partway through
`tests/regtest/test_tango_next.py` (job #1857142, this test file's name at
the time — since renamed to `test_lcoe_regression.py`) — `tests/regtest/` alone
(old-vs-new parity, CMG/native comparisons, full simulation runs) takes 1h+.
CI now runs only `tests/unit/` (36 tests, <1s), so a green pipeline means
"unit tests pass," not "full suite passes." The full suite (`tests/unit/` +
`tests/regtest/`) still runs locally on every `git push` via the `prek`
pre-push hook, so regressions are still caught before merge — just not by
the server-side pipeline. See `tests/README.md` for the day-to-day version
of this note.

Future task: either (a) speed up `tests/regtest/` until the full suite runs
comfortably in CI, or (b) make the fast/slow split permanent — `tests/unit/`
runs automatically (CI + pre-push), `tests/regtest/` runs locally via
pre-push plus an optional, manually-triggered CI job for deliberate
full-suite runs, but never automatically on every push.

---

#### Research-software quality assessment (EVERSE `resqui`) — revisit later

Flagged 2026-08-31 from a Swiss RSE conference: EVERSE's
[QualityPipelines](https://github.com/EVERSE-ResearchSoftware/QualityPipelines)
project (`resqui`) is a CLI + GitHub Action that runs a configurable,
plugin-based set of quality indicators against a repo (GitHub URL, Zenodo
DOI, or local path) and emits a report against an EVERSE research-software
quality schema. It ties into a broader ecosystem (RSQKit for best-practice
guidance, TechRadar for tool discovery, DashVERSE for dashboarding results).

Not a near-term priority — it's early-stage community tooling with thin
docs, and TANGO's current quality gaps (physics parity, typed error
handling, test coverage) are already being worked directly rather than
needing a badge/report tool to surface them. Worth a proper look once the
refactor settles down, particularly if there's ever a need to demonstrate
research-software quality externally (e.g. for a grant or an ETH
software-sustainability review).

---

### Refactor Phases

*Diagram: [Refactor Phases](../archive/diagrams/refactor_phases.drawio) — open in [draw.io](https://app.diagrams.net) or in VS Code with the draw.io extension. When this document is ported to Confluence, the diagram file will be attached to the page and embedded inline.*

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

*Diagram: [Input File Structure](../archive/diagrams/phase0_input_file_structure.drawio) — open in [draw.io](https://app.diagrams.net) or VS Code draw.io extension.*
*Diagram: [Runtime Code Objects](../archive/diagrams/phase0_code_objects.drawio)*
*Diagram: [Module Structure](../archive/diagrams/phase0_module_structure.drawio)*
*Diagram: [Execution Flow](../archive/diagrams/phase0_execution_flow.drawio)*

**Tasks:**
- [x] Diagrams
    - [x] structure of input files (used old tango's flexible_SF_manual.yml as an initial example; removed along with old tango, preserved at git tag pre-tango-core-rename-2026-09-18)
    - [x] structure of instantiated code object corresonding to the input file
    - [x] package/module/class structure, highlighting paths touched by that file
- [ ] Write characterization tests that run current TANGO on representative
    input files and capture reference outputs as fixtures (NOTE: Chad thinks the
    regression tests are already good enough to serve this purpose, especially since
    we're not sure the existing baseline should be interpreted as ground truth)
- [ ] Capture performance baselines (runtime, memory) on those same inputs
    (NOTE: this could be added to existing regression tests, as long as it can be
    done without having much impact on duration of tests)
- [ ] When comparing `tango` against original `src/tango/`, first wire
    `tango` to use the **same formulas as the original** (Haaland friction
    factor, radial Dupuit-Thiem reservoir flow, full TESPy surface cycle) and
    verify that results match — or identify and explain any discrepancies.
    Only after that baseline is confirmed should the alternative formulas
    already implemented in `tango` (Swamee-Jain, linear 1-D Darcy,
    lumped-efficiency surface) be run, to evaluate where they land relative
    to the verified baseline.  Both sets of formulas should remain as
    selectable variants — do not replace the originals.

    **Status (2026-06-22) — end-to-end parity achieved within deliberate bounds:**
    `NumericalInjectionWell` (`src/tango/components/well/numerical.py`,
    registered as `variant: numerical`) now replicates
    `src/tango/units/native/well/base.py::WellUnitNative.process_stream()`
    exactly: 100-cell axial discretization, Haaland friction factor
    (`core/fluid_utils.py::friction_factor_haaland`), Zhang et al. (2011)
    transient conductive heat loss, and real CoolProp property lookups via a
    new thin wrapper (`core/fluid_state.py::FluidState`, parity with
    `src/tango/core/fluidstate.py`). `LumpedInjectionWell` (`variant: lumped`) is
    kept as the permanent fast/simple variant per its module docstring — not
    replaced.

    A true end-to-end comparison of old tango's `flexible_SF_manual.yml`
    (removed along with old tango, preserved at git tag
    `pre-tango-core-rename-2026-09-18`) vs. `example_configs/hydro_sf_electric.yml`
    (tango) has now been completed across all 20 timesteps. The residual deltas are:

    - Reservoir outlet temperature: ≲ 0.04% (≲ 0.20 K, concentrated at the
      steepest part of the depletion transition, t≈5-7 for this case —
      settles to < 0.01 K agreement before and after that transition)
    - Gross / net power: ≲ 0.34%
    - Injection well outlet (isolated, 20-step fixed inlet): < 0.001 K (effectively zero)

    These are the final measured figures — the old-vs-new parity test
    suite that tracked them has since been removed (2026-09-18, as part
    of the internal-release cleanup once old tango itself was deleted),
    so this section is now the historical record of that comparison
    rather than a live-tracked number.

    These deltas are **deliberate, not bugs** — see the next section for the
    root cause and the rationale for not closing them.

    **Why tango intentionally diverges from old tango on energy extraction**

    Old tango conflates timestep state advancement with solver convergence in a
    way that produces a slightly incorrect reservoir energy extraction at every
    timestep. The mechanics (at commit `6496f82`, the last production HEAD
    before the tango refactor began):

    1. `FlowRateCalculator.iterator()` in
       `src/tango/orchestrators/BC_calculator.py:129` is the per-timestep
       convergence loop. It runs up to 200 outer iterations; in practice it
       converges in **2–3 iterations** (3 at t=0, 2 at t=1–19, confirmed by
       instrumentation).

    2. Each outer iteration calls `self.reservoir.stream_interface()`
       (`BC_calculator.py:406`), which internally calls
       `self.update_energy_extracted(del_=m_dot * (h_prod - h_inj) * dt)`
       (`src/tango/units/native/reservoir.py:186`). This mutates
       `_energy_extracted` — a temporal state variable — inside a convergence
       loop.

    3. `update_energy_extracted` uses a **SET pattern**, not accumulate:
       `self._energy_extracted = self._energy_extracted_old + del_`
       (`reservoir.py:214–221`). Each intra-timestep call overwrites the
       previous value rather than adding to it.

    4. `_energy_extracted_old` is only committed once per timestep, in
       `update_time_dependent_vars()` (`src/tango/orchestrators/external.py:148`).

    The consequence: when the outer loop converges and breaks on iteration N
    (`BC_calculator.py:551`),
    `_energy_extracted` has been set using the injection temperature from the
    start of iteration N — which was taken from the surface outlet at the end
    of iteration N-1. This is one outer iteration stale. Since convergence
    happens quickly (2 iterations), the injection temperature used for the
    final energy delta is not the fully converged value — it is the value from
    the previous outer iteration.

    This is exactly the class of bug that `LockedState` (Phase 2) is designed
    to prevent: temporal state (`_energy_extracted`) is mutated inside a
    convergence loop, violating the contract that state should only advance
    once the solver has converged on a self-consistent solution for that
    timestep.

    tango avoids this by design: `SystemBCIteration._converge_injection_T()`
    (`system_bc_iteration.py`) snapshots every component's cross-timestep
    state once per timestep, then restores and fully re-solves the *entire*
    circuit — reservoir included, no exceptions — on every inner iteration,
    checking convergence only after each complete pass (see
    `docs/tango_t_convergence.md` for the full mechanism). Because the
    reservoir is genuinely re-solved using *this* iteration's own injection
    temperature every time, by the iteration where convergence is declared,
    `energy_extracted` was already computed from a fully self-consistent,
    same-iteration injection temperature — never a stale one-iteration-behind
    value the way old tango's does.

    **`LumpedReservoir`'s initial-pressure bootstrap now matches old
    tango's, closing a real gap.** `LumpedReservoir` computes a proper
    `P_initial = brine_density × g × reservoir_depth` (a `brine_density`
    field, defaulting to 1000 kg/m³, was added to `ReservoirComponent`),
    matching old tango's `ReservoirUnitNative._compute_initial_pressure()`
    exactly — used for the reservoir's own initial/undepleted state
    (`P_out_prev` before it has ever been solved), separate from the
    fracking-safety-ceiling calculation (`hydro_static_pressure × (1 +
    over_pressure_percentage/100)`), which is a different physical
    quantity old tango never conflates the two with. Verified with an
    isolated, fixed-input reservoir comparison (both reservoirs given
    identical T/P/mass-rate): old tango's and tango's outputs now
    agree to sub-microkelvin precision across the first several
    timesteps, versus a compounding, multi-hundredths-of-a-Kelvin drift
    beforehand.

    What remains after this fix is concentrated at the single steepest
    part of the Adams-2015 depletion curve's transition (t≈5-7 for this
    case) — both codebases implement that curve identically (same
    coefficients, same erfc/exp branches), but it's steep enough there
    that the same already-documented, already-accepted floating-point-
    level differences elsewhere (independent CoolProp call sequences,
    the 1-step-lag fix above) get momentarily amplified before both
    systems settle back onto the same long-run behavior. This isn't
    something further code changes can eliminate without literally
    reproducing old tango's arithmetic instruction-for-instruction, which
    isn't a goal — see the residual-delta figures above (measured against
    the now-removed old-vs-new parity test suite; see that section's note
    on its removal).

    **Remaining gaps for whoever picks this up next** (intended hand-off
    point — Chad's plan is to get this set of two example files into good
    shape, then hand continuation to an intern):
    - ~~`LumpedProductionWell` / `LumpedProductionWellPump` still use the
      simplified closed-form model~~ — **done.** `NumericalProductionWell`
      (`components/well/numerical.py`) now exists alongside
      `NumericalInjectionWell`, both thin subclasses of a single
      `NumericalWell` base class sharing the same marching/Zhang-2011
      heat-loss scheme, distinguished only by `angle_from_vert_deg` (2026-07-21:
      replaced an earlier `ClassVar F_DIR = ±1.0` split with this — the same
      unified class now also covers horizontal/deviated wells, e.g.
      `example_configs/AGS_direct_heat.yml`'s `horizontal_well`, not just
      the two vertical cases `src/tango/`'s `WellUnitNative._f_dir` split covered).
    - ~~`LumpedReservoir` is still linear 1-D Darcy~~ — **done**, though not
      literally Dupuit-Thiem: `components/reservoir/lumped.py` now implements
      the doublet radial-flow impedance formula (Birdsell et al. 2024) plus
      Adams 2015 thermal-depletion tracking, matching
      `src/tango/units/native/reservoir.py`'s doublet well pattern.
    - ~~`SingleFlashSurface` is still a Phase 1 placeholder~~ — **done, then
      superseded.** The original hardcoded `SingleFlashSurface` (`components/
      surface/single_flash.py`) built and solved a real TESPy `Network` each
      timestep, targeting parity with `src/tango/units/native/surface/
      flexible_pp.py`. As of 2026-07-20 it has been **deleted** and replaced
      by `GraphSurface` (`components/surface/graph.py`), which builds the
      same kind of TESPy network but from a generic `power_plant.nodes`/
      `edges` YAML block instead of hardcoded Python — see the `tango`
      example coverage matrix above for what topologies are and aren't
      covered yet.
    - Dimensionless-time tracking in `NumericalInjectionWell`/
      `NumericalProductionWell` still only advances correctly because
      exactly one `solve()` call happens per timestep. `InjectionPolicy`
      (`core/policies.py`) now defines `MANUAL_FRACKING_CHECK`, `AUTO_PRESSURE`,
      `AUTO_FLOW`, and `AUTO_BOTH` in addition to `MANUAL`, and
      `SystemBCIteration` already saves/restores a `t_d_old` around its inner
      T-convergence loop — but `run_timestep` still raises
      `NotImplementedError` for every mode except `MANUAL`. The outer
      multi-pass convergence loop for `AUTO_*` (Phase 2) is the remaining
      work; the per-pass vs. per-timestep `t_d` split is flagged in detail in
      the component's module docstring.
    - ~~No automated test pins any of these numbers down yet~~ — **done,
      then removed.** `tests/regtest/test_old_new_parity.py` was a
      parametrized regression test asserting `numpy.testing.assert_allclose`
      on reservoir T, production T, and gross power histories between old
      tango and tango for `flexible_SF_manual.yml`. The root-level
      `diag_*.py` scripts were the original throwaway comparison scripts,
      superseded by this test at the time. Once old tango itself was
      deleted (2026-09-18, internal-release cleanup), the comparison this
      test existed to make was no longer possible, so it was removed too
      — `tests/regtest/test_lcoe_regression.py` (formerly
      `test_tango_next.py`) is what's left pinning down the numbers that
      survive: a fixed historical LCOE reference value, not a live
      old-vs-new comparison.

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

*Diagram: [New Input File Structure](../archive/diagrams/phase1_new_input_file_structure.drawio) — open in [draw.io](https://app.diagrams.net) or VS Code draw.io extension.*
*Diagram: [New Module Structure](../archive/diagrams/phase1_new_module_structure.drawio)*
*Diagram: [Execution Flow](../archive/diagrams/phase1_execution_flow.drawio)*
*Diagram: [BC Iteration Solver](../archive/diagrams/phase1_bc_iteration_solver.drawio) — outer BC convergence loop for `flexible_SF_manual.yml`, with power-plant sub-graph inset.*

**Tasks:**
- [x] create temporary space for new structure
- [ ] Consolidate code object data and graph connections so that each component
    (e.g. `injection_wellbore`) stores all its own attributes, a `component_idx`,
    and previous/next `component_idx` values
- [ ] Ensure no data is stored at root level
- [ ] Make hierarchy of data approximately match hierarchy of physical systems
- [ ] Diagrams of new structure
    - [x] desired structure of input files (used a new version of old
        tango's flexible_SF_manual.yml as an initial example; removed along
        with old tango, preserved at git tag pre-tango-core-rename-2026-09-18)
        and code objects (which are identical to input files in the new structure)
    - [x] package/module/class structure, highlighting paths touched by that file
- [ ] Design and migrate `addons` (ThermaGraph, Analyzer): the old implementation was a
    stringly-typed activation flag, never cleanly realized as separate installable dependencies.
    In `tango`, addons should be first-class composable components with a defined ABC.
    Needs a design decision before the migration tool handles them.
- [ ] Build a one-way migration tool from old to new input format
- [x] Stand up the parallel module structure with `mypy --strict` and `ruff` passing from the first commit
- [ ] Bring in classes, methods, and functions to make the new structure functional
- [x] Add test coverage for `tango`. `tests/unit/test_serde_roundtrip.py` and
    `tests/unit/test_locked_state.py` cover `LockedState`/serialization behavior,
    and `tests/regtest/test_lcoe_regression.py` (originally `test_tango_next.py`
    — renamed once the old-vs-new parity comparison it used to house was
    removed) exercises the CLI/orchestrator/component stack end-to-end
    (e.g. `hydro_sf_electric.yml` under `InjectionPolicy.MANUAL`). The
    old-vs-new parity test that used to live alongside it
    (`test_old_new_parity.py`) was removed 2026-09-18 once old tango itself
    was deleted — see the note earlier in this doc.

*(A trade-off assessment of the TESPy dependency — parked, not urgent — has moved to*
*[Appendix A](#appendix-a-tespy-dependency-assessment).)*

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
  not be assembled piecemeal at higher levels.  Each level owns its own state and delegates
  to children; the parent only reads child state after the child has solved.  In TANGO
  terms: `Orchestrator.run_timestep` calls `component.solve()`; `SurfacePlant.solve()`
  calls `PowerPlant.solve()`, which calls `Turbine.solve()`, `Pump.solve()`, etc.  Net
  power is then read upward from the fully-solved hierarchy — not assembled by passing
  lists (`prod_pump_w_list`) or adding corrections at a separate economic layer.  This is
  the fix for the `surface.w_net` ≠ economic-layer inconsistency described above.
- **Serialization:** Pydantic's `model_dump()` / `model_validate()` serve as the
  serialization layer for all `Component` subclasses — no separate mixin needed.
  `Component.from_dict()` handles YAML-dict → object construction; `Workflow.from_file()`
  handles YAML file → object. Round-trip tests in `tests/unit/test_serde_roundtrip.py`
  verify that `LockedState` fields survive `model_dump()` → `from_dict()` correctly.
  If binary formats (MessagePack) are ever needed, extend at that point — don't add
  the abstraction speculatively.

**Tasks:**
- [x] Convert all classes to Pydantic `BaseModel` (preferred) or `dataclass` —
    every `tango` component subclasses `Component(BaseModel, ABC)`
    (`core/component.py`); `state`/`history` are `dataclass` per the
    task's own "preferred or" allowance.
- [x] Add a component-specific `state` object to each class; move all transient state variables into it
- [x] Implement `LockedState` — enforces each state variable is updated once and only once per timestep
    (`core/locked_state.py`; cascaded from the orchestrator via
    `Component.mark_all_stale()`, not called by components themselves —
    2026-08).
- [x] Implement `history` object — saves state at user-specified intervals, with
    `None` supported for no temporal output (`save_interval: int | None`)
- [ ] `iter_history` object that saves the state for each solver iteration —
    **open question, not committed (2026-08): may not be worth building.**
    Not built today; the convergence-loop rework
    (`SystemBCIteration._converge_injection_T`) re-solves components up to
    20x per timestep with no per-iteration history recorded, only the
    converged final state. Chad's read: this arguably belongs to debugger
    territory (step through with a real debugger when you need
    per-iteration visibility) rather than a first-class recorded-history
    feature. Revisit if a concrete need for recorded (not just
    step-through) per-iteration state actually comes up.
- [x] Serialization: Pydantic `model_dump()` / `model_validate()` on `Component`
    handles the serde role directly — no separate mixin needed. Round-trip
    tests cover `LockedState` field fidelity (`tests/unit/test_serde_roundtrip.py`).
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
- [ ] Once all configurations are validated against `tango`, remove most or all references to
      `src/tango/` (old tango) from the codebase and documentation. Until then, old tango serves
      as the reference implementation and must not be deleted.
- [ ] Where results diverge, investigate bugs in both the old and new code
- [ ] Compare performance against pre-refactor baselines; investigate regressions
- [ ] Once `tango` is starting to stabilize (past the current example-porting churn),
      profile it properly (e.g. `cProfile`/`py-spy`, not just wall-clock comparison against
      old tango) to find real hotspots before optimizing anything — candidates worth a look
      going in: `LockedState` read/write overhead given how often it's touched per timestep,
      the `NumericalWell` marching loop's per-cell CoolProp lookups (`FluidState.with_HP`/
      `with_PT`, one call per cell per timestep), and `GraphSurface`'s TESPy `Network.solve()`
      being rebuilt/resolved from scratch every timestep rather than warm-started. Don't
      restructure for performance before this profiling step — premature optimization risk
      is real here given how much of the architecture (state/history separation, generic
      per-node diagnostics) was deliberately chosen for correctness/clarity over raw speed.
- [ ] Store web app lines and graphics as annotations in the TANGO run file
- [ ] Onboard Janna or additional support
- [ ] Fill out the `tango` example coverage matrix (AGS / EGS / CPG / Hydrothermal
      × heat / power extraction) — see "`tango` example coverage matrix" above.
      CPG needs a CO2 `FluidState` path first; the others are mostly new
      `power_plant` topologies on existing components.
- [x] ~~Beyond the matrix, port the broader set of old-tango examples confirmed actually
      running~~ — moot as of 2026-09-18: old tango's `examples/` and
      `REPO_CLEANUP_AUDIT.md` are both deleted (internal-release cleanup);
      preserved at git tag `pre-tango-core-rename-2026-09-18`. See
      "Beyond the matrix" above for the fuller note.
- [ ] Design combined heat-and-power (cogeneration) economics for `tango`
      before building a cogeneration example — see the note above. `src/tango/`
      precedent exists (`flexible_SF_cogeneration_e/h.yml`); the gap is a
      combined-cost formulation on top of `MainProduct`, not the surface-plant
      topology.
- [ ] Design a lightweight, generic seasonal/variable heat-demand mechanism for
      `tango` (decoupled from the Hotmaps-specific `HotmapsDispatchDT` in
      `src/tango/`) before treating any pure-heat or cogeneration example as
      representative — see the note above.
- [ ] **A clean pymoo optimization API for `tango`** — parameters set via a
      list of explicit functions operating on a config dict, objectives extracted
      the same way, dict-modify-then-reinstantiate throughout (never mutating a
      live `Workflow`/component), wrapped so users don't need to understand
      pymoo's `*args`/`**kwargs`-heavy `Problem` API directly. Should ship with a
      couple of worked examples and lightweight test coverage (not full
      optimization runs — sanity-check that parameter-setting functions actually
      perturb the objective). `src/tango/`'s
      `optimizerr.py` is NOT the reference for this — see
      `docs/tango_tasks.md`'s optimizerr.py review (2026-07-24) for why.
      `applications/sweep_demo_AGS_direct_heat/sweep_demo_AGS_direct_heat.py` (2026-07-24) is a
      small working precedent for the underlying mechanism this API would
      build on: it sweeps `common.rock_k` by mutating a copy of
      `Workflow.to_dict()` and reinstantiating, rather than mutating a live
      `Workflow`/component in place — the exact dict-modify-then-reinstantiate
      pattern this pymoo API needs for both parameter-setting and (eventually)
      config-side objective extraction.

      **Design principle, decided 2026-07-24: for multi-objective runs, suggest
      a candidate, never auto-select one.** `optimizerr.py` calls an
      Achievement Scalarizing Function (ASF) or pseudo-weights method
      automatically inside the optimization run to collapse the Pareto front
      down to one "final" solution (`MOOOptimizer._select_asf_solution`/
      `_select_pseudo_weights_solution`). Both methods are legitimate MCDM
      techniques, but both necessarily encode an implicit objective-weighting
      preference to do the collapse — there is no preference-free way to pick
      one point off a genuine Pareto front. Baking that collapse into the
      optimization call throws away exactly the information NSGA2-style MOO
      exists to surface: tradeoffs a fixed weighting would never show you (e.g.
      "give up 2% on cost, gain 15% on efficiency"). If a fixed collapse rule
      is going to be applied regardless, a weighted-sum scalarization fed to a
      single-objective optimizer gets to the same kind of single answer with
      far less machinery — the point of running MOO is to *not* pre-commit to
      that. `tango`'s pymoo API should write every point on the returned
      front to a dataframe/CSV (plus one `euclidean`-distance column as a sort
      hint, not a filter) and leave the choice to the human — return the full
      front by default. The ASF/pseudo-weights *math* from
      `optimizerr.py` is still worth keeping (see the `docs/tango_tasks.md`
      review) — just re-scoped as a separate, explicitly-invoked, opt-in
      helper that operates on an already-returned front
      (`suggest_solution(front, method="asf", ...)`-shaped), clearly labeled as
      *a* suggestion among valid alternatives, never called automatically and
      never presented as *the* answer.

      Explicitly not started, not urgent — captured here so the intent isn't
      lost, not a commitment to build it soon.


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

The idea: wrap `tango_cli run` in a top-level exception handler that, on any
unhandled error, packages the context and sends it to an LLM agent for interpretation.

**What the agent receives:**
- The full input YAML (the system configuration the user submitted)
- The Python traceback and exception message
- The last-known component states (serialized via `model_dump()`) — what each component
  computed before the failure

**What the agent returns:**
- A plain-English explanation of what went wrong and why
- A concrete suggestion for how to fix it (e.g. "your injection pressure of 45 MPa
  exceeds the fracking threshold of 38 MPa for this reservoir depth — try reducing
  `injection_pressure` in the surface spec, or switch to `mode: auto-pressure` to
  let the solver find a safe value automatically")
- If appropriate, a corrected or adjusted input snippet the user can paste in

**Why this is particularly well-suited to LLM assistance:** The error messages TANGO
produces (and the ones CoolProp and TESPy produce underneath it) are correct but
written for developers, not operators. The mapping from "what the physics failed on"
to "what the user should do about it" is well-defined enough to be reliably produced
by an LLM that has been given the component context — but tedious and error-prone to
hard-code as static error messages.

**Implementation approach, prerequisites, and error-taxonomy design:** see
[Appendix: AI-Assisted Error Interpretation — Implementation Sketch](../appendices/ai_error_interpretation_sketch.md)
for the code-level sketch (a top-level exception handler wrapping `tango_cli run`,
routed through a stable `TangoError` exception taxonomy modeled on Rust's
`thiserror`/`anyhow` pattern).

*Diagram: [Execution Flow](../archive/diagrams/phase1_execution_flow.drawio) — shows the
AI error agent as a future hook on the right side of the simulation loop.*

---

### Future Direction — Performance & Scalability

Full sweeps and optimization runs (`pymoo_api`-driven NSGA-II, sensitivity sweeps) can
require thousands of individual TANGO simulations, and each one currently pays the cost
of a full numerical time-march. As sweep sizes and optimization budgets grow, simulation
throughput becomes the limiting factor rather than the physics itself. Three
complementary directions, roughly in order of effort:

**1. Profile first, then cut low-hanging fruit.** Before assuming a rewrite is
necessary, profile a representative run to find where time actually goes. A likely
candidate: `NumericalWell`'s marching scheme currently uses 100 cells per well
regardless of well length or how much spatial resolution the result actually needs —
it's plausible that far fewer cells (or an adaptive cell count) would give
indistinguishable accuracy at a fraction of the cost. Any such change needs a
convergence study (does the answer change materially as cell count drops?) before
being adopted as a default, not just a speed measurement.

**2. Train ML surrogates for optimization loops.** NSGA-II-style optimization
evaluates a candidate design, checks dominance, and generates new candidates —
tolerating an approximate objective function is much cheaper here than in a
one-shot single simulation, because errors get corrected out over many
generations. The proposed workflow: run full TANGO simulations across an LHS
(or other space-filling) design to build a training set, fit a regression model
(e.g. a random forest) to predict the optimization objectives from the design
parameters, then run PyMOO's NSGA-II against the trained surrogate instead of
full TANGO — orders of magnitude cheaper per evaluation. Critically, the
surrogate-derived Pareto front must be validated with full TANGO runs at the
final candidate points before being presented as a result; the surrogate finds
candidates faster, it does not replace verification.

**3. Port hot paths to a faster language.** If profiling identifies a
genuinely hot inner loop that resists both of the above (e.g. the well
marching scheme's per-cell physics), porting just that piece to a compiled
language (Rust and Julia are the natural candidates, given TANGO's existing
Rust-flavored error-handling direction and Julia's numerical-computing
ecosystem) is the highest-effort but highest-ceiling option. This should be a
last resort, scoped narrowly to whatever profiling actually identifies as the
bottleneck — not a wholesale rewrite — and only after (1) and (2) have been
tried, since both are cheaper and may make (3) unnecessary.

---

### Future Direction — Subsurface as TESPy Components (Fully Implicit Solve)

Today's architecture solves subsurface and surface as two separate, nested systems:
`SystemBCIteration`'s outer Picard/Newton-step boundary-condition loop marches the
well/reservoir chain explicitly (a single linear chain, one convergence variable),
calling a fresh `GraphSurface` TESPy `Network` solve each iteration. That doesn't
generalize to a genuine field-level network — multiple wells with non-uniform,
independently-specified boundary conditions, branching topologies, shared reservoir
compartments — since each new topology shape would need its own bespoke BC-iteration
logic. An open idea, not yet started: extend the wellbore model to be a TESPy-base-class
component too, so subsurface and surface solve as **one** simultaneous, arbitrarily
graph-shaped TESPy network instead of a linear outer march wrapping a nested inner
solve — handling non-uniform BCs and branching as a natural consequence of the graph
structure rather than per-topology iteration code. (A secondary side benefit for
today's single-chain case: it would also collapse the current two-level iteration into
one Newton solve.)

**This idea has already been explored once, with a different conclusion** — see
[`subsurface_as_tespy_components.md`](subsurface_as_tespy_components.md) for the full
writeup, including why literally subclassing TESPy's `Component` runs into a real
architectural mismatch with `tango`'s Pydantic-based component model, and why
folding subsurface into one TESPy network would also collide with the outer circuit's
deliberately linear (`component_idx`/`prev`/`next`) representation. **Do not start a
prototype of this without explicit sign-off** — it's flagged as a backlog item in
`docs/tango_tasks.md`, deliberately held.

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

---

## Appendix A: TESPy Dependency Assessment

*Parked, not urgent — kept for reference when Phase 2 optimization/LCOE work begins,*
*since that is where the trade-offs below matter most.*

`tango` uses [TESPy](https://github.com/oemof/tespy) to model the single-flash power
plant cycle (valve → droplet separator → turbine/condenser/pump branches → mixer). TESPy
was chosen for Phase 1 to achieve numerical parity with `src/tango/`, which also relies on
it. The dependency is appropriate for that goal but carries several rough edges that should
be weighed for Phase 2+.

**TESPy shortcomings observed during Phase 1 implementation:**

- **Silent unit inconsistency.** `h_unit="kJ/kg"` only controls display formatting;
  `component.P.val` and `component.Q.val` are always stored in **Watts** (SI), not kW.
  This caused a 1,000× power error during implementation — TESPy gives no warning.
- **Stringly-typed API.** `connection.set_attr(fluid={"Water": 1}, T=..., p=...)` — wrong
  key names fail silently at construction time and only error (confusingly) at solve time.
- **No warm-start between solves.** Each call to `network.solve("design")` re-initializes
  from scratch; there is no way to hand TESPy a prior solution as an initial guess. This
  is a significant performance penalty for time-step simulations where the state changes
  slowly between steps.
- **Noisy convergence output.** TESPy emits solver-convergence messages via its own
  `"TESPyLogger"` with a hardcoded level that must be overridden explicitly; standard
  Python `logging.basicConfig` does not suppress it.
- **Opaque solver failures.** Convergence errors surface as bare exceptions with
  internal TESPy tracebacks, not as structured errors with state-point context. Difficult
  to distinguish "physically infeasible state" from "solver failed to converge on a valid
  state."
- **Limited to steady-state.** TESPy solves one steady-state operating point per call;
  transient effects in the surface plant are not modeled. This is acceptable for the
  current timestep-averaged approach but limits future fidelity.

**Case for migrating to a direct CoolProp implementation (Phase 2+):**

A direct CoolProp implementation of the single-flash cycle would:
- Eliminate solver overhead (explicit enthalpy/entropy calculations, no Newton loop over
  the cycle graph).
- Remove the warm-start limitation — each timestep can start from the previous solution
  with no extra overhead.
- Produce clean, structured errors via `CoolPropError` already in the `tango` error
  taxonomy.
- Reduce the dependency surface: CoolProp is already required; TESPy would no longer be.
- Make the cycle physics fully transparent and testable at the unit level.

The trade-off is implementation effort: TESPy encapsulates cycle topology and constraint
propagation that would need to be re-derived explicitly. For a single-flash plant the
physics is simple enough that a direct implementation is tractable; for more complex cycles
(double-flash, ORC with recuperator) the trade-off is less clear.

**Recommendation:** Retain TESPy for Phase 1 (parity target). Evaluate replacing it with
a direct CoolProp implementation in Phase 2, scoped to the single-flash plant first.
The decision should be made when the Phase 2 optimization/LCOE work begins — that is where
the no-warm-start penalty will be most visible.

**2026-09-17 update — broader suitability review, prompted by the ORC port.** With the
ORC cycle ported from old tango (`flexible_ORC_manual.yml` → `GraphSurface`;
old tango and this file removed, preserved at git tag
`pre-tango-core-rename-2026-09-18`),
`tango` is now past "single-flash only," which is exactly the case this appendix
already flagged as making the direct-CoolProp trade-off "less clear." The
direct-CoolProp-migration recommendation above should be read as weaker for anything
beyond single-flash going forward.

A wider review confirmed there's no better foundation to switch to right now:

- **TESPy project health:** actively maintained, backed by DLR (German Aerospace Center)
  via the `oemof` energy-modeling framework — not a solo/hobby project. A 1.0 roadmap
  issue opened 2026-09-17; a 0.11.0 solver-refactor cycle is underway. Adoption is
  academic rather than industrial, but includes direct precedent for our exact problem:
  Witte et al., *"Parametric optimization and comparative study of an organic Rankine
  cycle power plant for two-phase geothermal sources"* (Energy, 2022), modeling a
  two-phase-geothermal ORC in TESPy. Known, acknowledged limitation: Newton-Raphson
  convergence is sensitive to poor initial guesses and small-magnitude flows
  (`oemof/tespy` issue #314) — a recurring robustness concern worth budgeting for, not a
  one-off bug.
- **Our pin is stale.** `pyproject.toml` pins `tespy==0.7.1.post1` (Dec 2023); current is
  0.11.2 (Sept 2026) — 4 minor releases behind. This matters beyond routine upkeep:
  newer TESPy documents a friendlier custom-component API (`dependents()`,
  `dc_cmc`/`num_eq_sets`) that lets the solver derive Jacobian structure automatically,
  which does not exist in 0.7.1.post1. Bumping the pin is a prerequisite for any
  custom-component work, not just hygiene (tracked in `docs/tango_tasks.md`).
- **Custom components on top of TESPy are feasible today, and there's already a
  concrete candidate.** Every component subclasses
  `tespy.components.component.Component`, implementing `component()`,
  `inlets()`/`outlets()`, `get_parameters()` (a dict of `dc_cp`/`dc_cc`/`dc_cm` data
  containers wiring each parameter to a residual `func` and a Jacobian-filling
  `deriv`), and `get_mandatory_constraints()`. On our pinned version, Jacobians are
  hand-written analytic derivatives (a `numeric_deriv` finite-difference fallback
  exists but is opt-in per equation, not automatic differentiation).
  `tespy.tools.helpers.UserDefinedEquation` offers a lighter path for one-off equations
  without a full subclass. No custom components exist in `tango` today —
  `GraphSurface` maps YAML `type:` strings straight onto stock TESPy classes — but the
  `PumpOrValve` pseudo-type (resolved today by building and solving two full parallel
  networks and picking whichever is valid) is exactly the kind of case a single custom
  hybrid component would eliminate, and is the natural first target once the version
  bump lands.
- **Alternatives surveyed — none beat staying on TESPy right now:**
  - *Modelica/OpenModelica:* still not viable on macOS — native Mac binaries were
    discontinued after v1.16, and 1.26/1.27 (2025-2026) haven't restored them; current
    guidance is Docker+XQuartz or building from source. The earlier "glitchy" assessment
    holds, arguably more strongly now that there's no native binary at all.
  - *Rumoca* (Rust-based Modelica compiler): still explicitly self-described as
    early/rough/pre-1.0. "Too beta" remains accurate — confirmed hands-on
    2026-07-29 (`docs/modelica-investigation.md`): a real MSL-based model
    flattened successfully but an unresolved 184-equation DAE imbalance and a
    broken editor/LSP integration were both hit in a single time-boxed spike.
    (Separately, Modelica's acausal connector semantics do give a real,
    structural mass/momentum/energy conservation guarantee that TESPy's
    causal component model doesn't — see
    `docs/long_term_architecture_exploration.md` — but that's an argument for
    the Modelica *language*, not for Rumoca's current maturity.)
  - *Commercial Modelica (Dymola, SimulationX):* still priced out of reach.
  - *Julia / ModelingToolkit.jl:* the most technically interesting option — genuinely
    declarative, acausal component modeling (symbolic DAE, index reduction) that
    handles both steady-state and transient natively, unlike TESPy's imperative,
    steady-state-only equation building. But `ModelingToolkitStandardLibrary.jl`'s
    thermal/hydraulic domains are thin — no ready-made turbine/condenser/two-phase-HX
    components. Adopting it would mean building the entire geothermal/ORC component
    library from scratch on a better foundation, not avoiding that work, plus a full
    stack switch away from the Python/CoolProp/`pymoo` ecosystem already built.
  - *DWSIM:* open source, actively maintained, native macOS, Python API, validated
    against Aspen HYSYS — but chemical-process/flowsheeting oriented, uncertain fit for
    turbomachinery/ORC power-cycle work. Not investigated in depth; worth a spike only
    if TESPy becomes a real blocker.

**Updated recommendation:** keep TESPy as the surface-plant backend. Bump the version
pin (backlog item, `docs/tango_tasks.md`) to unlock the modern custom-component
API, then build tango-specific components *on top of* TESPy rather than replacing it —
see
[`subsurface_as_tespy_components.md`](subsurface_as_tespy_components.md) for the
larger, longer-horizon version of that idea (subsurface joining the same TESPy network).
