# Injection-Enthalpy Convergence

How `SystemBCIteration` finds a self-consistent injection enthalpy
every timestep. Code: `src/tango_core/orchestrators/system_bc_iteration.py`
(`_converge_injection_enthalpy`). Reference case:
`templates/hydro_sf_electric.yml`, a doublet with a single-flash
surface plant; the same mechanism applies to every `SystemBCIteration`
circuit. Status: available.

Components exchange specific enthalpy, not temperature, along with
pressure and mass flow. The injection well needs an inlet enthalpy before
its fluid properties can be evaluated. That enthalpy is not an input: it is
whatever leaves the surface plant, which depends on everything upstream in
the circuit. Because the components are solved explicitly, one after
another, the loop guesses the injection enthalpy, solves the whole circuit,
and repeats until the enthalpy that comes back matches the guess.

## A. The physical circuit

![Circuit diagram: injection well through reservoir, production wells, and surface plant, back to injection well](diagrams/img/tango/t_convergence_circuit.png)

In the single-flash surface plant, the wellhead fluid reaches the
injection enthalpy through three paths:

- **Separator:** the vapor/liquid split is a flash calculation on the
  enthalpy that arrives from the wellhead, at the valve's fixed outlet
  pressure. The split sets the mass flow through *both* branches, so even
  the branch with a pinned outlet *state* carries a wellhead-dependent mass
  *weighting* into the merge.
- **Condenser branch:** its outlet temperature, pressure and enthalpy are
  pinned boundary conditions, independent of the wellhead. Its mass flow
  is not (see the separator).
- **Liquid branch (via `brine_pump`):** neither its state nor its mass flow
  is pinned; both depend on the reservoir and production-well output.

## B. The convergence loop

Because the reservoir's output reaches the injection enthalpy through
the merge, the reservoir is re-solved on every attempt, like every other
component.

![Flowchart: snapshot convergence state once, then loop restore/mark-stale/solve/wire for every component up to 20 times, check injection enthalpy, and finish when converged](diagrams/img/tango/t_convergence_loop.png)

1. **`snapshot_convergence_state()`**, once, before iterating. Every
   component deep-copies its whole `state`, including cross-timestep
   accumulators such as `LumpedReservoir`'s `energy_extracted` and
   `ever_solved` and `NumericalWell`'s dimensionless time `t_d`. The
   snapshot is the state as committed at the end of the *previous*
   timestep.
2. **For each component, in circuit order**, on every attempt and with no
   exceptions: `restore_convergence_state()` → `mark_all_stale()` →
   `solve()` → wire the outlet to the next inlet. Restoring first means
   each attempt starts from last timestep's state, not from what the
   previous attempt left behind.
3. **Check the injection enthalpy** after each full pass: if
   `|Δh_inj| < 1 kJ/kg` (`_DH_SURFACE_TOL`), the loop has converged.
   Otherwise the next guess comes from Aitken relaxation
   (`core/accelerators.py::aitken_relax`), and the loop repeats, up to 20
   attempts (`DEFAULT_MAX_INNER_ITER`). After 20 attempts it raises
   `ConvergenceError`. The tolerance is absolute because enthalpy's zero
   point is an arbitrary reference state. It is on enthalpy rather than
   temperature because near a fluid's critical point the temperature can
   stop changing while the enthalpy is still off by several kJ/kg.
4. **The converged pass is the result.** It used the converged enthalpy
   and started from a clean restore of the snapshot.

If a guess drives the fluid below its freezing point, CoolProp raises a
"Tmelt" error. The loop then resets the guess to the enthalpy at 275 K and retries.

Implementation: `core/component.py` (`snapshot_convergence_state`,
`restore_convergence_state`) and `orchestrators/system_bc_iteration.py`
(`_converge_injection_enthalpy`).
