# Future direction: subsurface as TESPy components (fully implicit solve)

Linked from [`README.md`](README.md)'s "Future Direction — Subsurface as TESPy
Components" and its `InjectionPolicy` discussion. **Not started, and not to be started
without explicit sign-off** — tracked as a backlog item in `dev_docs/tango_tasks.md`.

## The idea

`tango` currently solves the physical system in two nested layers:

- **Outer loop (`SystemBCIteration`):** an explicit, component-by-component march
  through the well/reservoir/production chain, with a hand-rolled Picard/Newton-step
  update for boundary-condition iteration (e.g. `test_p += target_reservoir_P -
  inj_well.outlet.P`).
- **Inner solve (`GraphSurface`):** a real TESPy `Network`, solved fresh from scratch
  on every outer iteration.

**Primary motivation: scalability to true graph-network topologies outside the surface
plant.** The current outer loop is built around a single linear chain (one injector →
reservoir → one or more producers → surface → back to the injector) with one
`test_p`/pressure-matching variable driving convergence. That doesn't generalize to a
genuine field-level network — multiple injectors and producers with non-uniform,
independently-specified boundary conditions, shared or compartmentalized reservoir
volumes, branching wellbore topologies. Each new topology shape would need its own
bespoke BC-iteration logic layered onto `SystemBCIteration`, because the outer loop's
convergence variable and update rule are hand-derived for the one-chain case. An
**implicit** whole-network solve — TESPy's actual model: every component contributes a
residual + Jacobian row, and one sparse Newton solve updates every unknown across an
arbitrary graph simultaneously — handles branching and non-uniform BCs as a natural
consequence of the graph structure, with no per-topology BC-iteration code to write.
That's the case for extending the wellbore/reservoir model so it participates in
TESPy's implicit system (or something built on the same pattern) rather than staying
inside an outer march: it buys topology generality, not just a cleanup of the current
single-chain case.

(A secondary, more contained benefit if this is pursued: it also collapses the
current two-level architecture — outer BC loop wrapping a from-scratch `GraphSurface`
solve every iteration — into one solve, which is a nice side effect for the *current*
single-chain topology too. But that's not the reason to take this on; see below for a
narrower, lower-risk way to get that side effect without a graph-topology rewrite.)

## This has already been explored once — see `dev_docs/implicit_solver_exploration.md`

A prior exploration (`dev_docs/implicit_solver_exploration.md`) looked at this exact
question — "should TANGO's subsurface components extend tespy's `Component` base
class?" — and reached two conclusions worth restating here rather than re-deriving:

**1. Don't literally subclass `tespy.components.component.Component`.** It's a plain
class built around an `OrderedDict` of `dc_cp`/`dc_simple` property containers,
`design`/`offdesign` mode switching, and `parameters`/`get_parameters()` conventions.
`tango.core.Component` is a `LockedState`-frozen Pydantic `BaseModel` with
serialization as a first-class concern. These two metaclass/`__dict__` models don't
compose cleanly by inheritance. Doing this "properly" would mean writing an adapter
class — a tespy-`Component` shim that reads off the Pydantic well model and emits
residual/Jacobian rows — which is the same component-adapter pattern `GraphSurface`
already uses for its own TESPy integration, just applied one layer deeper into the
subsurface. **"Extends a TESPy base class," if pursued, almost certainly means an
adapter, not real Python inheritance.**

**2. A separate, orthogonal problem also needs solving: the fracking discontinuity.**
This is *not* the motivation for wanting an implicit/graph-topology solve above — it's
a distinct piece of required work that any implicit reformulation (TESPy-based or not)
runs into along the way. The fracking switch (`if p > p_frac: mode changes`) is not
differentiable at the threshold, and Newton's method needs a differentiable residual
near the solution. That's true whether the Jacobian assembly is TESPy's or hand-rolled
— the fix is reformulating the switch as a smooth complementarity condition (e.g. a
Fischer–Burmeister-style combination of `Q = fracking_flow(p)` and `p ≤ p_frac` into one
equation), which as a side effect also collapses `InjectionPolicy`'s two
separately-coded fracking mechanisms into one constraint. Required regardless of
whether the eventual implementation adapts into TESPy or stays fully inside
`tango`, and regardless of whether the scope ends up being one linear chain or a
true multi-well graph.

The prior exploration's own suggested direction was, in fact, to **not** adopt TESPy's
`Component` at all — instead borrow the residual/Jacobian *pattern* directly inside
`tango`'s own `Component`/orchestrator (add `residual()`/`jacobian()` hooks,
replace `SystemBCIteration`'s fixed-point update with a real Newton step, keep
surface's TESPy `Network` solve at the boundary, coupled via an interface residual
rather than merged into one matrix). That gets the causality fix without importing
TESPy's design/offdesign/characteristic-curve machinery or fighting the Pydantic model
shape the rest of `tango` is built on.

## The central tension: the outer circuit's representation is linear by design

This is where the primary motivation above (topology generality) directly collides
with an existing, deliberate choice, not a downstream implementation detail.

`tango`'s outer physical circuit (injection well → reservoir →
production well(s) → surface → back to injection well) intentionally uses
`component_idx`/`prev`/`next` integer fields on each `Component`, **not** a
`nodes`/`edges` graph block like `GraphSurface`'s own internal `power_plant.nodes`/
`edges`. This is deliberate — for human readability, and to give
`sim_config.bc_checkpoint_idx` a clean, explicit integer position in a known linear
order — not a port omission, and it was reconfirmed as recently as the ORC port
(where the outer circuit stayed a plain linear chain even though the ORC's secondary
fluid loop is graph-shaped *inside* one `GraphSurface` node).

But a true multi-well, non-uniform-BC field network — the actual case motivating this
whole idea — is inherently `nodes`/`edges` graph-shaped, not a linear chain: multiple
injectors and producers, possibly a shared reservoir compartment, no single well-order
for `bc_checkpoint_idx` to name. So this isn't just "does TESPy support a custom
wellbore component" — it's "the outer circuit's representation itself needs to become
a graph before a true multi-well network can be expressed at all," independent of
which solver ends up owning the Jacobian. Any prototype needs to make an explicit,
separately-justified case for that representation change (what happens to
`bc_checkpoint_idx`'s clean linear semantics once there's no single "the" order) rather
than treating it as incidental to "extend the wellbore to a TESPy base class."

## What a real prototype needs to resolve first

1. **Is a true multi-well/non-uniform-BC graph topology actually the near-term need**,
   or is this being reached for while the real case in hand is still one chain? If it's
   the latter, an **interface residual** (prior exploration's suggestion — two solves,
   surface and subsurface, coupled but not merged into one matrix) likely gets the
   causality and performance benefits for the single-chain case without taking on a
   representation change at all. Worth ruling out explicitly before committing to
   anything bigger.
2. **Does the outer circuit's linear representation change, and how** — this is the
   real crux once a genuine graph topology is in scope, not a detail to defer to
   implementation. What replaces `bc_checkpoint_idx`'s clean linear semantics once
   there's no single well order?
3. **Subclass vs. adapter** for the wellbore/reservoir component itself — confirmed
   above: adapter, not inheritance, unless a fresh look finds this wrong.
4. **The fracking complementarity reformulation** — a separate, required piece of work
   either way (see above), not the reason to do any of this, but not optional either.
