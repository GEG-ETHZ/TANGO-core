# `tango.core`

`core` holds the building blocks every other subpackage is made of. It knows nothing about any particular well, reservoir or plant. It defines what a component *is*, how values travel between components, how the config is validated, and what can go wrong. Most of its rules exist to stop a silent wrong number. A value read too early, a copy that drifts out of sync or an unconverged result all become an immediate error instead.

## The ideas you need

**A component is a pydantic model with a `solve`.** `Component` is both a pydantic `BaseModel` and an abstract class. Its fields are the YAML keys, so a component is built straight from its config block (`from_dict`) and can be written back out unchanged. A subclass declares its config fields, computes derived values in `init()`, and implements `solve(inlet)`, which must set `self.outlet`. Unknown YAML keys are rejected (`extra="forbid"`).

**A `Stream` is the only thing that crosses a boundary.** It carries temperature (K), pressure (Pa) and mass flow rate (kg/s), nothing else. Components never call each other. An orchestrator passes one component's `outlet` to the next one's `solve(inlet)`.

**Mutable values are guarded.** Every value that changes during a run is a `LockedState`. It must be written exactly once per solve. Reading it before that write, or writing it twice, raises a `LockedStateError` (`StaleAccessError`, `FreshAccessError`, `DoubleWriteError`). The orchestrator calls `mark_all_stale()` before every solve to open the next write. These values live in the component's `state` dataclass. After each timestep, `record()` appends them to a matching `*History`, so the whole time series is kept.

**Config and errors are typed.** The top-level config blocks are pydantic schemas: `Common`, `Layout`, `SimConfig` and `Description`. `Common` is built once and shared by reference with every component, so all components see the same fluid and rock properties. Every failure tango raises deliberately is a `TangoError` subclass. That is how `tango_cli` tells a config error (exit 1) from a simulation error (exit 2).

## Read these first

1. `component.py`, `Component`: the class docstring explains the solve lifecycle, and `snapshot_convergence_state` shows what an iteration restores.
2. `locked_state.py`, `LockedState`: the write-once guard.
3. `stream.py`, `Stream`: the three quantities on the wire.
4. `specs.py`, `SimConfig`: timesteps, `injection_mode` and the checks between them (`check_injection_mode_requirements`).

## Reference

| Module | Holds |
|---|---|
| `component.py` | `Component`: `from_dict`, `init`, `solve`, `snapshot_convergence_state`, `restore_convergence_state` |
| `stream.py` | `Stream`, `StreamHistory` |
| `locked_state.py` | `LockedState` |
| `state_methods.py` | `StateMethods`: `mark_all_stale`, `record` |
| `orchestrator.py` | `Orchestrator`, the interface the orchestrators implement |
| `specs.py` | `Common`, `Layout`, `SimConfig`, `Description` |
| `policies.py` | `InjectionPolicy`, `MainProduct`, `ProjectMaturity`, `ComponentRole` |
| `errors.py` | `TangoError` and its subclasses, such as `ConvergenceError`, `ConfigError`, `FrackingViolationError`, `CoolPropError` |
| `fluid_state.py`, `fluid_utils.py` | `FluidState` over CoolProp; friction, hydrostatics, `fracking_flow` |
| `accelerators.py`, `numerics.py` | `aitken_relax`; `secant_solve` with `PUMP_BOOST_TOL_PA = 1.0`, `PUMP_BOOST_MAX_ITER = 20` |
| `constants.py`, `economic_constants.py`, `physics_models.py`, `init_protocol.py` | Physical and cost constants, model enums, the `Init` protocol |

The rules behind these classes are the [TANGO commandments](https://github.com/GEG-ETHZ/TANGO-core/blob/main/CONTRIBUTING.md#tango-commandments).
