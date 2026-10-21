# Optimization

An optimization searches the design space of one config for the best
trade-off between objectives, for example the lowest LCOE against the
highest net power. TANGO runs a full simulation for every candidate design,
so an optimization is many ordinary runs steered by a genetic algorithm
(NSGA-II, from [pymoo](https://pymoo.org)). When full runs are too slow,
a surrogate model trained on runs stands in for the simulator.

| Approach | Module | Use it when | Ready-made apps |
|---|---|---|---|
| Direct | `pymoo_api` | Each run takes seconds to minutes | `applications/opt_hydro_sf_electric`, `opt_hydro_df_electric`, `opt_AGS_direct_heat` |
| Surrogate | `surrogate_api` | Runs are too slow for thousands of evaluations | `applications/opt_hydro_df_electric_surrogate` |

To start, copy the closest app (`uv run tango_cli init . --app <name>`)
and change its parameters and objectives. Run it small first: a tiny
`--n-max-gen` and `--pop-size` with a throwaway `--save-dir`.

## The three building blocks

A **parameter** (`ParamSpec`) is one decision variable: a name, bounds,
and a function that writes the value into a copy of the config. Each
candidate is a fresh config, never a modified live object.

```python
--8<-- "applications/opt_hydro_sf_electric/opt_hydro_sf_electric.py:param"
```

An **objective** (`ObjectiveSpec`) reads one number from a finished run;
every objective is minimized, so a quantity to maximize is negated.
Constraints (`ConstraintSpec`) work the same way and mark a design
infeasible instead of ranking it.

```python
--8<-- "applications/opt_hydro_sf_electric/opt_hydro_sf_electric.py:objective"
```

**`Minimization`** ties them to a base workflow and runs the search, in
parallel when `n_processes` is above one. A run that fails to converge or
breaks a physical limit counts as infeasible instead of stopping the search.

```python
--8<-- "applications/opt_hydro_sf_electric/opt_hydro_sf_electric.py:minimization"
```

The examples above are included from `applications/opt_hydro_sf_electric/opt_hydro_sf_electric.py`, so they always match the code.

## How the direct optimization works

::: tango.pymoo_api
    options:
      members: false
      show_root_heading: false
      show_root_toc_entry: false

## How the surrogate optimization works

::: tango.surrogate_api
    options:
      members: false
      show_root_heading: false
      show_root_toc_entry: false

Every class and option: [API reference](../reference/optimization.md).
