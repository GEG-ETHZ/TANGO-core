# `tango.orchestrators`

An orchestrator runs the component circuit through time. Each timestep it solves the components in order and passes each outlet to the next component. After the last timestep it runs the economics once. The hard part is that the circuit is a closed loop: the plant's outlet is the injection well's inlet. One pass is therefore not a consistent answer, and the loop must iterate until it closes.

## The ideas you need

**Why the circuit iterates.** The loop is cut at the injection well (`component_idx` 0), which is solved first. It needs an injection temperature, but that temperature only exists once the surface plant, last in line, has been solved. `SystemBCIteration` guesses the temperature and solves every component in order. It reads the temperature the plant returns, corrects the guess with Aitken relaxation and repeats. It stops when two guesses differ by less than 0.5 K, or raises `ConvergenceError` after 20 attempts. On the very first timestep the guess comes from the surface conditions.

**One attempt starts from the same place.** Before the loop starts, each component's `state` is snapshotted (a deep copy). Every attempt restores that snapshot, then calls `mark_all_stale()` and `solve(inlet)` on each component in turn. Each attempt thus asks the same question: given last timestep's state, what does this timestep look like with this guess? Attempts never build on each other's leftovers.

**The `auto-*` modes adjust the boundary to stay below the fracking limit.** Injecting too hard fractures the reservoir. Two quantities can cause it: wellhead pressure and mass flow. `auto-pressure` wraps a Newton loop around the temperature loop. It raises the wellhead pressure by the gap between the target reservoir pressure and the pressure at the bottom of the injection well. `auto-flow` wraps a fixed-point loop instead. It sets the mass rate to the fracking flow limit at the current fluid state, capped at `max_mass_rate`. Both stop at a relative change below 1e-3, or raise `ConvergenceError` after 200 iterations. Every mode except plain `manual` then checks both thresholds and raises `FrackingViolationError` if either is exceeded. It never caps the value silently. `auto-both` raises `NotImplementedError`.

**`SystemDirect` is the plain case.** Without `sim_config.injection_mode`, the workflow uses `SystemDirect`: one pass per timestep, no iteration. `SystemBCIteration` subclasses it and replaces only `run_timestep`. Every shipped example config sets `injection_mode`.

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

Diagram: [boundary-condition iteration](https://github.com/GEG-ETHZ/TANGO-core/blob/main/docs/runtime/bc-iteration.md). Deep dives: [injection-temperature convergence](https://github.com/GEG-ETHZ/TANGO-core/blob/main/docs/tango_t_convergence.md) and [the Aitken speed-up](https://github.com/GEG-ETHZ/TANGO-core/blob/main/docs/aitkens_speedup.md).
