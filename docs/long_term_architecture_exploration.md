# Long-term architecture exploration

**Status: speculative, not a roadmap.** This is the parking lot for
"if we ever had a real greenfield opportunity" architecture thinking —
deliberately kept separate from `docs/TANGO_vision_and_roadmap/README.md` (which
is already fairly bloated and is meant to track the concrete, near-term
`tango` roadmap) so long-horizon ideas don't get lost but also don't
clutter the doc people read to find out what's actually being built next.
Nothing here should be read as planned, scheduled, or blocking any current
work. Started 2026-07-24.

---

## The discomfort this is tracking

TANGO's surface-plant modeling (`GraphSurface`, built on TESPy) and fluid
properties (CoolProp) work well today, but there's a real architectural
mismatch worth naming plainly: **TESPy is a causal, imperatively-solved
network** — you specify a fixed topology, fixed pressures/setpoints on
individual components, and TESPy's Newton solver resolves the resulting
system. This was explored in depth in a prior session (see
`docs/diagrams/src/graph_surface_state_provenance.drawio` and the vision
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
  source, not something tied to Dymola/OpenModelica specifically. But
  Rumoca is explicitly self-described as "in active development... expect
  bugs and rough edges," so full-coverage compilation of real-world
  libraries using advanced Modelica features (`redeclare`, inheritance,
  conditional components, external C functions, table lookups) is a
  real open question, not a verified fact — worth testing directly
  against MSL before drawing conclusions either way.
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
