# How injection-enthalpy convergence works

`tango` &middot; `orchestrators/system_bc_iteration.py`

Reference case: `flexible_SF_manual.yml`, DOUBLET single-flash. The same
mechanism applies to any `SystemBCIteration` circuit.

Every timestep, tango has to find the injection state that's
self-consistent with the prescribed injection wellhead pressure and mass
flow rate and everything downstream of it. Components exchange specific
enthalpy (not temperature) along with pressure and mass flow, so the
unknown is the injection enthalpy. It must be guessed initially to enable
property calculations of the fluid in the injection well, but it is fully
determined from the other states and parameters. Because this is an
explicit solver, we must solve iteratively until the returning enthalpy is
stable.

## A. The physical circuit

![Circuit diagram: injection well through reservoir, production wells, and surface plant, back to injection well](diagrams/img/t_convergence_circuit.png)

- **Separator:** the vapor/liquid split fraction is a flash calculation on
  whatever enthalpy actually arrives from the wellhead (at the valve's
  fixed outlet pressure). That fraction sets the mass flow through *both*
  branches — so even the branch with a pinned outlet *state* still carries
  a wellhead-dependent mass *weighting* into the merge.
- **Condenser branch:** its own outlet T/P/enthalpy are pinned boundary
  conditions, genuinely decoupled from the wellhead — but not its mass
  flow (see separator, above).
- **Liquid branch (via brine_pump):** neither its state nor its mass flow is
  pinned — both are dependent on the reservoir/production-well output.

## B. The convergence loop

Because the reservoir's true output can reach the injection enthalpy
through the merge above, it has to be re-solved on every attempt like
everything else in the circuit.

![Flowchart: snapshot convergence state once, then loop restore/mark-stale/solve/wire for every component up to 20 times, check injection enthalpy, and finish when converged](diagrams/img/t_convergence_loop.png)

- **`snapshot_convergence_state()`** — once, before iterating. Every
  component in the circuit deep-copies its own mutable, cross-timestep
  fields — `t_d_old`, `energy_extracted`, `ever_solved`, and any future
  field of that kind. This is "state as committed at the end of the
  *previous* calendar timestep."
- **For each component, in circuit order** — repeated up to 20 times,
  reservoir included, no exceptions: `restore_convergence_state()` &rarr;
  `mark_all_stale()` &rarr; `solve()` &rarr; wire outlet to next inlet.
  Restoring first means this attempt starts clean from last timestep's
  real state — not from whatever the previous attempt left behind.
- **Check injection enthalpy** — after one full circuit pass: is
  `|Δh_inj| < 1 kJ/kg` (`_DH_SURFACE_TOL`)? If not, loop back to the top
  with the new guess (up to 20 times). If so, converged. The tolerance is
  absolute because enthalpy's zero point is an arbitrary reference state;
  it's on enthalpy rather than temperature because near a fluid's critical
  point the temperature can stop changing while the enthalpy is still off
  by several kJ/kg.
- **This iteration's state is the final answer.** It already used the
  converged enthalpy and the correct, single-copy snapshot restore.

See `core/component.py` (`snapshot_convergence_state`/
`restore_convergence_state`) and `orchestrators/system_bc_iteration.py`
(`_converge_injection_enthalpy`) for the implementation.
