# ERROR TRACE BACKS
We want users and agents to know exactly where and when tango is running into errors for quicker debugging. To do this when a function runs into an error we want to propagate exceptions up the call stack adding more context wherever possible and practical. For example if we fail with a value error of negative temperature in a coolProp function we want to know <strong>Where</strong> in the tango simulation this occured i.e. which Component, was it at an outlet in inlet? <strong>When</strong> within the simulation did this occur, was is in a Convergence Loop or part of the Outer Loop, what was the iteration and timestep? And importantly <strong>What Was The Error</strong>, we keep passing the original error message. It's pretty simple but it will save users and contributors lots of time when using the code.
## Cool Prop
This has first been implemented to traceback coolProp errors in the development of Tango Next. For example coolProp is used to update the pressure and temperature of a coolProp fluid in ``src/tango/core/fluid_state.py``.
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
The Value error could be raised by CoolProp if pressure (P) is negative at some point in the simulation. The user would like like to find that point ...
so we add ``try`` and ``except``s for ``CoolPropError``s up the call stack.
In ``system_bc_iteration.py`` in the function ``_converge_injection_T`` we append the <strong>Where</strong> to the message.
```python
                try:
                    component.solve()
                except CoolPropError as exc:
                    raise CoolPropError(f"""
                    Component: {component.__class__.__name__}
                    Component Index: {component.component_idx}
                    Converge Injection Temp Iteration: {inner_iter}
                    {exc}
                    """) from exc
```
And in the ``run_timestep`` function where ``_converge_injection_T`` is called we add <strong>When</strong> to the error message.
```python
            if surface is not None:
                try:
                    self._converge_injection_T(surface, snapshot)
                except CoolPropError as exc:
                    raise CoolPropError(f"""
                    Iteration: {t}
                    Time: {t * self.dt_years} years
                    {exc}
                    """) from exc
            return
```

The coolProp functions that are currently handled like this are:
1. ``CoolProp.HmassP_INPUTS``
2. ``CoolProp.PT_INPUTS``
