# Implicit solver exploration: residual/Jacobian components in tango

Context: this note grew out of a question about whether TANGO's subsurface components
(wells, reservoir) should extend tespy's `Component` base class, in order to eventually
solve the well/reservoir/surface loop as one coupled implicit system instead of marching
through it explicitly (see [`TANGO_vision_and_roadmap/README.md`](TANGO_vision_and_roadmap/README.md)'s
discussion of the two fracking mechanisms around line 257 for the motivating problem, and
[`TANGO_vision_and_roadmap/subsurface_as_tespy_components.md`](TANGO_vision_and_roadmap/subsurface_as_tespy_components.md)
for how this note's conclusions bear on that specific proposal).

## What tespy's implicit solve actually looks like

tespy's `Network.solve_control()` (`tespy/networks/network.py`) runs a Newton loop:

- `solve_components()` — every `Component` contributes a `residual` vector and a sparse
  `jacobian` dict of `{(row, col): value}` for its own equations.
- `solve_connections()` — connections (mass flow, pressure, enthalpy, fluid composition)
  contribute their own continuity rows the same way.
- `matrix_inversion()` — the assembled sparse Jacobian is factored (direct sparse LU) and
  solved for one Newton step, updating every unknown across the whole network at once.

Crucially, most of tespy's Jacobian entries are **hand-coded analytic partial
derivatives** (e.g. `energy_balance_deriv` in `tespy/components/heat_exchangers/base.py`
sets `self.jacobian[k, i.m.J_col] = o.h.val_SI - i.h.val_SI` directly), with a
numeric-differentiation fallback (`_numeric_deriv`) for equations that don't have one.
So the actual contract a component fulfills is "contribute residual + Jacobian rows" —
that part is solver-agnostic and has nothing to do with tespy's domain coverage (which is
surface/process-plant components only; it has no wellbore or reservoir physics at all).

## Why this would help the fracking/BC-causality problem

`SystemBCIteration` (`src/tango/orchestrators/system_bc_iteration.py`) currently
hand-rolls a fixed-point (Picard) update:

```
test_p += target_reservoir_P − inj_well.outlet.P
```

plus a separate inner temperature-convergence loop, plus a `MANUAL_FRACKING_CHECK` mode
that is a *different* code path entirely for when the fracking threshold rather than the
pressure target is the binding constraint. Flow-induced and pressure-induced fracking are
checked as two independent mechanisms (see the vision doc) precisely because the explicit,
component-by-component march has no way to express "reservoir inlet pressure is bounded by
one constraint, regardless of which upstream input pushed it there."

A shared residual vector — with wellhead pressure `p` and mass rate `Q` both as free
unknowns, constrained by whichever equations are active — removes that branching: it
becomes one combined constraint on reservoir inlet pressure, not two separately-coded
checks.

## The actual hard part isn't the solver mechanics

The fracking switch itself is a discontinuity (`if p > p_frac: mode changes`), and Newton's
method needs a differentiable residual near the solution. That's true regardless of
whether the Jacobian assembly is tespy's or hand-rolled — the fix is to reformulate the
switch as a smooth complementarity condition (e.g. a Fischer–Burmeister-style combination
of "`Q = fracking_flow(p)`" and "`p ≤ p_frac`" into one equation) rather than a branch. That
reformulation is the real design work here, and it's orthogonal to which framework hosts
the Jacobian.

## Why not literally subclass tespy's `Component`

tespy's `Component` is a plain class built around an `OrderedDict` of `dc_cp`/`dc_simple`
property containers, `design`/`offdesign` mode switching, and `parameters`/
`get_parameters()` conventions. `tango.core.Component` is a Pydantic `BaseModel` with
`LockedState`-frozen fields and serialization as a first-class concern. These two
metaclass/`__dict__` models don't compose cleanly by inheritance — doing this "properly"
would mean writing an adapter class (a tespy-`Component` shim that reads off the Pydantic
well model and emits residual/Jacobian rows), which is really the same component-adapter
pattern already used for `GraphSurface`'s tespy integration, just applied one layer deeper
into the subsurface.

## Suggested direction

Borrow the *pattern* — assemble a sparse residual/Jacobian from each component, one
`spsolve` per outer iteration — directly inside `tango`'s own `Component`/
orchestrator, rather than inheriting from tespy at all:

1. Add `residual()`/`jacobian()` hooks next to `solve()` on `tango.core.Component`
   (or a mixin/ABC layered on top, so components that don't participate in the implicit
   loop are unaffected).
2. Replace `SystemBCIteration`'s fixed-point update with a real 1-D Newton step first —
   e.g. `Δtest_p` from a numerically-estimated `d(inj_well.outlet.P)/d(test_p)` — before
   generalizing to the full coupled system.
3. Formulate the fracking complementarity condition (step above) so the two-mechanism
   split in `InjectionPolicy` collapses into one constraint.
4. Keep surface's real tespy `Network` solve at the boundary rather than folding it into
   the same matrix — couple wells+reservoir to surface via an interface residual, not by
   merging both solvers into one system.

This gets the causality fix without importing tespy's design/offdesign/characteristic-curve
machinery, and avoids fighting the Pydantic model shape that the rest of `tango` is
built on.
