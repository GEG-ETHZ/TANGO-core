# Long-Term Architecture Exploration

**Status: speculative, not a roadmap.** This is the parking lot for
"if we ever had a real greenfield opportunity" architecture thinking —
deliberately kept separate from `docs/TANGO_vision_and_roadmap/README.md` (which
is already fairly bloated and is meant to track the concrete, near-term
`tango` roadmap) so long-horizon ideas don't get lost but also don't
clutter the doc people read to find out what's actually being built next.
Nothing here should be read as planned, scheduled, or blocking any current
work. Started 2026-07-24. A follow-up, time-boxed implementation spike
(Rumoca + MSL, a real multi-component model, LSP tooling) is written up
separately in `docs/modelica-investigation.md` (2026-07-29) — that doc
has the concrete, hands-on findings; this one has the framing and the
still-open questions.

---

## The discomfort this is tracking

TANGO's surface-plant modeling (`GraphSurface`, built on TESPy) and fluid
properties (CoolProp) work well today, but there's a real architectural
mismatch worth naming plainly: **TESPy is a causal, imperatively-solved
network** — you specify a fixed topology, fixed pressures/setpoints on
individual components, and TESPy's Newton solver resolves the resulting
system. This was explored in depth in a prior session (see
`docs/archive/diagrams/graph_surface_state_provenance.drawio` and the vision
doc's "`GraphSurface`'s fixed `p_out` values" section) — the upshot: several
plant pressures are externally *imposed* design constants rather than
values *derived* from a genuine resistance/flow relationship, because
that's what TESPy's causal solve pattern requires.

Two of TANGO's own stated goals sit awkwardly next to that:

1. **Integrating external simulation environments** (CMG, MOOSE, DWSIM —
   see the vision doc's "Where to provision sockets for external tools"
   section) for the reservoir side, and potentially others for the surface
   side. Composing a Python-imperative, causally-solved TESPy network with
   a heterogeneous set of external simulators is architecturally awkward —
   there's no shared, principled boundary for how state flows between a
   causal component and an acausal/implicit one.
2. **Physical correctness under real operating variability** — the
   fixed-pressure-constants pattern was defensible for the specific
   design-point calculations TANGO does today, but starts to strain
   exactly where the tool is trying to grow (sweeps, off-design operation,
   coupling to other subsystems that don't share TESPy's assumptions).

None of this is urgent or broken — it's a "the foundation may not scale
with where we want to go" concern, not a bug report.

## Candidate direction: Modelica-family tooling

Modelica is an equation-based, acausal, non-causal modeling language —
components are specified as declarative equations, not solve-order-
dependent imperative networks, and composition of heterogeneous physical
subsystems (thermal, hydraulic, electrical, ...) is the language's core
design point. That's a much closer philosophical match to "compose TANGO's
native physics with external reservoir/surface simulators" than TESPy's
approach.

**Conservation guarantee, confirmed.** Part of the appeal is that Modelica's
acausal connector semantics *structurally* enforce conservation: at every
connection, the sum of a connector's "flow" variables is forced to zero
(a generalized Kirchhoff law), which is how mass, momentum, and energy
balance at junctions falls out of the language/tool itself rather than
depending on each component author getting it right. **TESPy does not make
that guarantee.** TESPy does enforce mass and (where applicable) energy
balance per component — these are `mandatory_constraints` baked into the
base `Component` class and inherited by every stock component — but that
enforcement is per-component code the framework ships, not a structural
property of arbitrary connections the way Modelica's connector semantics
are. Nothing in TESPy stops a component (custom, or the network topology
itself) from imposing a physically-ungrounded constant rather than deriving
it from a real balance relation — which is exactly the "fixed `p_out`
values" issue already flagged above and in the vision doc. That gap is the
concrete version of "physical correctness" concern #2 in the section above.

Chad has used Dymola extensively (best-in-class Modelica fidelity, but
slow compilation and historically poor error messages) and evaluated
OpenModelica (solid open-source concept, but hit a real diagnostic-quality
wall: an FMU failed due to a non-continuously-differentiable input, with
no usable error message until the same model was recompiled in Dymola).

**Rumoca** ([CogniPilot/rumoca](https://github.com/CogniPilot/rumoca)) —
a Rust-native Modelica compiler — surfaced as a candidate worth tracking:

- Explicit multi-stage compiler pipeline (Parse → Resolve → Typecheck →
  Instantiate → Flatten → ToDAE → Structural → Simulate → Codegen), each
  phase its own crate with strict IR boundaries.
- Diagnostics are a deliberate design commitment, not an afterthought:
  contributor guidelines require every compiler phase to own its own error
  enum, and mandate that diagnostics "carry real spans whenever source
  exists" — spans must not be silently dropped during transformations.
  This is a structurally different approach from the OpenModelica failure
  mode above, and directly addresses the diagnostic-quality gap.
- First-class Python interoperability and multiple codegen backends
  (Rust-native simulation with AD Jacobians, Julia/Python symbolic export
  via a companion project called Cyecca for CasADi/SymPy integration,
  WASM, template-based codegen). Fits a Python (PyO3) + Rust toolchain
  preference directly rather than requiring a pivot to a third language.
- Ruled out alternatives: Dyad/JuliaSim (licensing — too commercially
  aggressive; Chad knows the director, disclosed as a conflict, didn't
  appear to bias the technical read), Modia/Julia generally (JIT viewed as
  a worst-of-both-worlds compromise for scientific computing — slower
  iteration than Python, weaker compile-time correctness guarantees than
  Rust). **ModelingToolkit.jl** (the SciML acausal modeling framework;
  Chad has met its lead, Chris Rackauckas) is a distinct project from
  Modia — not a rename or successor, a separate and more actively
  developed Julia DSL for the same acausal-modeling problem — but it's
  the layer Dyad is built on top of, and both are JuliaHub-affiliated.
  MTK's core is genuinely MIT-licensed, but "distinct from Dyad" overstates
  the independence: same company driving the roadmap, Dyad as the
  commercial product on MTK's open core. Same JIT objection as Modia
  applies regardless of the licensing question.

  **2026-09-21 update, prompted by a direct exchange with Michael
  Tiller** — the same person named below in "Known complaints about
  Modelica itself" (ex-Modelica Association board Secretary, now
  JuliaHub VP of Product Management; the conflict-of-interest note there
  applies equally to what follows here, coming directly from him):
  - **Dyad licensing is now explicitly a sales-contact wall, not a
    published number.** `juliahub.com/pricing/dyad` lists concrete
    non-commercial/individual AI-agent tiers ($0/$20/$60/$200 per month),
    but commercial use is "connect with our team" with no figures
    disclosed. Dyad has also moved fast in 2026 — 2.0 (Dec 2025), 3.0 and
    a $65M Series B (Apr 2026) — repositioning around "agentic AI for
    industrial digital twins" rather than just the acausal DSL/compiler.
    That's a venture-funded SaaS trajectory, which if anything reinforces
    the original "too commercially aggressive" read rather than
    softening it. The original "too commercially aggressive" judgment
    stands, though the earlier discussion apparently had more explicit
    published pricing to point to than is available now.
  - **The JIT/iteration-speed objection is real but was stated too
    broadly.** Asked Tiller directly whether keeping a Julia process
    warm (e.g. in a long-lived container) avoids the JIT-compile hit; his
    answer: "With Dyad, we use a `juliaup` distribution to avoid a ton of
    pre-compilation... No Docker required." `juliaup` itself is just a
    version manager (the Julia equivalent of `rustup`); what's actually
    doing the work is a **custom juliaup distribution channel shipping a
    prebuilt sysimage** — i.e. the same technique as `PackageCompiler.jl`
    (precompile once, ship the compiled artifact), just delivered as a
    juliaup channel instead of a standalone sysimage file. This mitigates
    the tax **for code baked into that shipped distribution**; it does
    *not* eliminate JIT compilation for new, user-written code (e.g.
    custom components) written after the distribution is built — that
    still pays the standard Julia JIT cost unless the sysimage is
    rebuilt and reshipped. Whether Dyad's own workflow supports
    rebuilding that distribution locally as you iterate is unconfirmed —
    open question if this gets pursued further. Either way, this
    mitigation is orthogonal to the "weaker compile-time correctness
    guarantees than Rust" half of the objection, which is a static-typing
    trade-off intrinsic to Julia and unaffected by precompilation.
  - **The "full stack switch away from Python/CoolProp/pymoo" objection
    (see the vision doc's TESPy suitability review) was overstated as a
    blocker.** The vision doc's own "multi-simulator federation" section
    already commits to **FMI** as the standard boundary for exactly this
    kind of heterogeneous external-tool composition (CMG, MOOSE, DWSIM).
    If an MTK/Dyad model can be consumed as an FMU, it's just one more
    external tool behind that same boundary, not a stack rewrite. Caveat:
    checked 2026-09-21 — MTK's own FMU *import* is explicitly flagged
    experimental/unstable by SciML, and FMU *export* would go through a
    separate library (`FMIExport.jl`), not something built into MTK/Dyad
    directly. So the stack-fit objection is weaker than originally
    written, but "MTK models via FMI" carries its own unverified
    integration-maturity risk on top of the JIT and thin-stdlib points
    below.
  - **Building the missing components ourselves is licensing-clean but a
    real lift, bigger than the Rumoca spike's.** Both
    `ModelingToolkit.jl` and `ModelingToolkitStandardLibrary.jl` are MIT
    (confirmed 2026-09-21, independent of Dyad's commercial layer — you
    can use plain MTK without touching JuliaHub's commercial terms at
    all), and an official `CoolProp.jl` wrapper exists (CoolProp itself is
    MIT), so there's no licensing blocker to hand-writing a turbine,
    condenser, and two-phase heat exchanger. But `ModelingToolkitStandardLibrary.jl`'s
    Hydraulic domain (confirmed 2026-09-21) is **isothermal, single-phase,
    Tait-equation-of-state only, with no real-fluid-properties backend** —
    materially thinner than what the Rumoca/MSL spike had to work with,
    where `Modelica.Media.Interfaces.PartialTwoPhaseMedium` already
    existed and only two custom components had to be written against it.
    In MTK-land there's no equivalent published two-phase medium/connector
    abstraction to build against — that layer (effort/flow variable
    choice for two-phase state, convective/stream semantics at junctions)
    would need to be designed from scratch before any turbine/condenser/HX
    components could sit on top of it. That's a bigger, more open-ended
    lift than "write two components" — it's original design work with no
    existing implementation to validate against, not just implementation
    effort against an established abstraction.

    **Chad's call, 2026-09-21: this rules MTK out, not just "worth a
    spike."** The point of MTK was getting Modelica's structural
    conservation guarantee without Modelica's downsides (annotation
    format, GUI baggage). Having to hand-build the two-phase medium/
    connector layer from scratch forfeits that cheap-guarantee premise —
    you'd be doing the *harder* version of the work Rumoca already gets
    for free via MSL's mature `Media` library, while *also* giving up the
    Rust/Python stack fit and taking on Julia's JIT/type-safety
    trade-offs. Rumoca dominates MTK on every axis here except license
    terms, and the licensing angle (MIT core, independent of Dyad) turned
    out not to be the actual blocker once this gap surfaced. No spike
    planned; MTK is parked alongside Dyad/Modia for the same underlying
    reason (see above), not pursued further.

## Known complaints about Modelica itself (not tool-specific)

Worth separating "problems with a given Modelica *implementation*" (Dymola
compile speed, OpenModelica diagnostics) from "problems with the *Modelica
language/ecosystem* itself," which no compiler choice fixes:

- **Graphical annotation format.** Modelica's `Icon`/`Diagram` annotations
  (the syntax embedding diagram layout, connector placement, etc. directly
  in `.mo` source) are widely regarded as clunky. Dyad reportedly addresses
  this with a more modern approach. Confirmed directly (2026-07-24):
  Rumoca is purely text/CLI-based — parser, LSP, formatter, WASM
  playground for running the compiler — with no graphical annotation
  handling or visual editor anywhere in it. That's actually a point in its
  favor for this idea: there's no legacy GUI/annotation-rendering layer to
  fight, so a modern front end (e.g. draw.io-based, generating/consuming
  Modelica source rather than embedding layout in it) could realistically
  be built from a clean slate rather than needing to dethrone an existing
  visual tool's opinions.
- **Michael Tiller's broader critiques** — not just a practitioner:
  verified 2026-07-24, he served as Secretary of the Board of the Modelica
  Association for over two decades (stepped down September 2025, remains
  on the board), is President of the North America Modelica Users' Group,
  and wrote *Introduction to Physical Modeling with Modelica*. Someone
  with that much standing in the Modelica Association itself criticizing
  the language/ecosystem carries real weight — worth compiling the actual
  list of complaints (LinkedIn and elsewhere) before this exploration goes
  any further. Chad couldn't recall specifics in the moment; not yet
  researched. **Conflict worth tracking**: Tiller is currently VP of
  Product Management at JuliaHub — the company behind Dyad/JuliaSim, which
  this same exploration already ruled out on licensing grounds. Doesn't
  invalidate his critiques of Modelica-the-language, but worth keeping
  in mind when reading anything from him that touches on alternatives.

## Open questions — nothing here is settled

- **Does Rumoca's Modelica-language coverage support the Modelica
  Standard Library and third-party domain libraries today** (e.g.
  ThermoPower, TIL, ClaRa-style libraries with realistic media models)?
  This matters a lot: if MSL and similar libraries compile cleanly, the
  "no mature domain library ecosystem" concern raised when this was first
  discussed is largely unwarranted, since MSL is tool-independent Modelica
  source, not something tied to Dymola/OpenModelica specifically.
  **Partially answered 2026-07-29** (`docs/modelica-investigation.md`):
  core MSL 4.1.0 resolves and typechecks cleanly against a real checkout,
  and a hand-built multi-component geothermal loop mixing MSL base classes
  with custom two-phase components flattened successfully. Third-party
  libraries (ThermoPower, TIL, ClaRa) and advanced features (`redeclare`,
  inheritance, conditional components, external C functions, table
  lookups) beyond that spike's scope are still untested — Rumoca remains
  self-described as "in active development... expect bugs and rough
  edges."
- **Could CoolProp be preserved rather than replaced**, by bridging it in
  as a Modelica external function call from within Rumoca-compiled models?
  That would give real, rigorous thermodynamic properties without either
  giving up CoolProp's fidelity or keeping TESPy's causal-network
  constraints — a hybrid path worth scoping if this ever becomes concrete.
- **What's the actual multi-simulator federation story?** Worth separating
  two different boundaries here. Rumoca's own Python interop (see above)
  already covers "Rumoca-compiled models talking to Python directly" —
  that boundary doesn't need FMI. The open question is the other one:
  federating with CMG/MOOSE/DWSIM, which are heterogeneous external
  simulators, not Python libraries. **FMI** (Functional Mock-up Interface)
  is the tool-independent open standard for exactly that kind of
  co-simulation boundary, with FMPy as an open-source Python runtime for
  it — noted here for posterity since Chad had already been assuming FMI
  would be the answer here without having written it down. Still open:
  whether Rumoca/Cyecca can export/consume FMUs, or whether that
  federation needs custom glue code regardless of modeling-language choice.
- **Team Rust fluency and maintenance burden** of taking on a second
  implementation language in the stack, beyond what PyO3-wrapping an
  existing crate (like the CoolProp/TESPy dependencies today) already
  requires.
- **Maturity/adoption risk**: Rumoca originates from CogniPilot, a
  drone/robotics org, not an energy or process-simulation shop. No
  evidence yet of production use outside its origin project. Being an
  early adopter in a new domain carries real risk independent of the
  technology's merits.

## Why this is parked, not pursued

There is no current opportunity to greenfield TANGO's physics core, and
nothing above should slow down or complicate `tango` work in
progress. This document exists purely so the thinking isn't lost if that
changes.
