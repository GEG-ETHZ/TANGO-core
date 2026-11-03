# `tango_core.orchestrators`

An orchestrator runs the component circuit through time. Each timestep it solves the components in order and passes each outlet to the next component. After the last timestep it runs the economics once. The hard part is that the circuit is a closed loop: the plant's outlet is the injection well's inlet. One pass is therefore not a consistent answer, and the loop must iterate until it closes.

## The ideas you need

**Why the circuit iterates.** The loop is cut at the injection well (`component_idx` 0), which is solved first. It needs an injection enthalpy, but that enthalpy only exists once the surface plant, last in line, has been solved. `SystemBCIteration` guesses the enthalpy and solves every component in order. It reads the enthalpy the plant returns, corrects the guess with Aitken relaxation and repeats. It stops when the returned enthalpy and the guess differ by less than 1 kJ/kg, or raises `ConvergenceError` after 20 attempts. On the very first timestep the guess comes from the surface conditions.

**One attempt starts from the same place.** Before the loop starts, each component's `state` is snapshotted (a deep copy). Every attempt restores that snapshot, then calls `mark_all_stale()` and `solve(inlet)` on each component in turn. Each attempt thus asks the same question: given last timestep's state, what does this timestep look like with this guess? Attempts never build on each other's leftovers.

**`manual-fracking-check` checks the fracking limit; nothing adjusts the boundary to meet it.** Injecting too hard fractures the reservoir. Two quantities can cause it: wellhead pressure and mass flow. Once a timestep has converged, `manual-fracking-check` checks both thresholds and raises `FrackingViolationError` if either is exceeded. It never caps the value silently. To find an operating point below the limit, use an `applications/opt_*/` search, which treats that error as an infeasible design.

**`SystemDirect` is the plain case.** Without `sim_config.injection_mode`, the workflow uses `SystemDirect`: one pass per timestep, no iteration. `SystemBCIteration` subclasses it and overrides `run_timestep`, where the iteration lives, and `run`. Every shipped template sets `injection_mode`.

## Read these first

1. `system_direct.py`, `SystemDirect.run`: the time loop.
2. `system_bc_iteration.py`, `run_timestep`: the dispatch on `injection_mode`.
3. `system_bc_iteration.py`, `_converge_injection_T`: the attempt loop and the snapshot restore.
4. `system_bc_iteration.py`, `_converge_injection_pressure`: the outer loop around it.

## Reference

| Class | Key methods |
|---|---|
| `SystemDirect` (`system_direct.py`) | `_next_inlet`, `_record_outlet`, `run_timestep`, `record`, `finalize` (economics), `run` |
| `SystemBCIteration` (`system_bc_iteration.py`) | `_check_fracking`, `_seed_circuit_inlet`, `run_timestep`, `_converge_injection_pressure`, `_converge_injection_flow`, `_converge_injection_T` |

| Constant (`system_bc_iteration.py`) | Value |
|---|---|
| `DEFAULT_MAX_ITER_NO_FRACK` | 200 |
| `DEFAULT_TOLERANCE` | 1e-3 |
| `DEFAULT_MAX_INNER_ITER` | 20 |
| `_DT_SURFACE_TOL` | 0.5 K |

Diagram: [boundary-condition iteration](https://github.com/GEG-ETHZ/TANGO-core/blob/main/docs/runtime/bc-iteration.md). Deep dive: [injection-enthalpy convergence](https://github.com/GEG-ETHZ/TANGO-core/blob/main/docs/tango_t_convergence.md).
