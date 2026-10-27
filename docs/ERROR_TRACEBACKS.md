# Error Tracebacks

How TANGO adds context to an error as it travels up the call stack, so that a
failure names the component, the timestep and iteration, and the original
message. Status: available for CoolProp errors.

## Goal

An error raised deep inside a property call should tell the reader three
things:

1. **Where**: which component, and its index in the circuit.
2. **When**: which timestep and simulated time, and which convergence
   iteration.
3. **What**: the original error message, unchanged.

Each layer of the call stack catches the error, adds the context it knows
and re-raises it with `raise ... from exc`, so the original traceback stays
attached.

## CoolProp errors

CoolProp property updates are wrapped in `src/tango/core/fluid_state.py`.
A failed update, for example a negative pressure, raises `CoolPropError`
with the inputs that caused it:

```python
    def update_PT(self, P: float, T: float) -> None:
        """Update this state in place from pressure (Pa) and temperature (K)."""
        try:
            self._state.update(CoolProp.PT_INPUTS, P, T)
        except ValueError as exc:
            raise CoolPropError(
                f"updatePT(P={P:.6g} Pa, T={T:.6g} K) failed for {self.fluid_name}: {exc}",
            ) from exc
```

`SystemBCIteration._converge_injection_T`
(`src/tango/orchestrators/system_bc_iteration.py`) adds **where**: the
component and the iteration of the injection-temperature loop. A "Tmelt"
error is the one exception: the guess drove water below its freezing
point, so the loop resets the guess to 275 K and retries instead of
failing.

```python
                try:
                    component.solve(self._next_inlet(component))
                except CoolPropError as exc:
                    if "Tmelt" in str(exc):
                        ...  # reset the guess to 275 K and retry
                    raise CoolPropError(f"""
                    Component: {component.__class__.__name__}
                    Component Index: {component.component_idx}
                    Converge Injection Temp Iteration: {inner_iter}
                    {exc}
                    """) from exc
```

`SystemBCIteration.run_timestep` adds **when**:

```python
            if surface is not None:
                try:
                    self._converge_injection_T(inj_well, surface, snapshot)
                except CoolPropError as exc:
                    raise CoolPropError(f"""
Iteration: {t}
Time: {t * self.dt_years} years
{exc}
                                        """) from exc
```

`SystemDirect.run_timestep` (`src/tango/orchestrators/system_direct.py`)
adds the timestep and the component in one step, because it has no inner
loop.

The wrapped CoolProp inputs are:

1. `CoolProp.HmassP_INPUTS` (`FluidState.update_HP`)
2. `CoolProp.PT_INPUTS` (`FluidState.update_PT`)

A failed TESPy network solve in the surface plant raises
`TESPyCoolPropError` (`src/tango/components/surface/graph.py`). It
subclasses `CoolPropError`, so the same orchestrator layers add where and
when. Every `TangoError` that reaches `tango_cli run` ends the run with exit
code 2.
