# Applications

`applications/` holds studies that run many TANGO simulations: parameter sweeps, design optimizations, surrogate-model pipelines and demonstrations. Each application starts from one configuration in [`example_configs/`](https://github.com/GEG-ETHZ/TANGO-core/blob/main/example_configs/README.md), varies it, and runs `Workflow(cfg).run()` once per design point, in parallel. Every application is a self-contained directory. Nothing outside the directory imports from it, and `tango_cli init --app <name>` copies one into your own project.

## Catalog

| Application | Kind | Base configuration | What it answers |
|---|---|---|---|
| `demo_hydro_sf_electric` | Demo | `hydro_sf_electric.yml` | One run, plotted: well temperature profiles, reservoir temperature, power over time |
| `demo_well_mesh_convergence` | Demo | `hydro_sf_electric.yml` | How fine the `NumericalWell` cell mesh must be; documents the default cell length |
| `sweep_demo_AGS_direct_heat` | Demo | `AGS_direct_heat.yml` | Minimal example of the edit-the-config-then-rerun sweep pattern |
| `run_AGS_direct_heat_sweep` | Sweep | `AGS_direct_heat.yml` | Well depth × mass flow × loop length × loop diameter (12,870 designs), Triemli site |
| `run_EGS_direct_heat_sweep` | Sweep | `EGS_direct_heat.yml` | Well depth × mass flow (100 designs), Triemli site |
| `run_hydro_df_electric_sweep` | Sweep | `hydro_df_electric.yml` | One-at-a-time sensitivity of LCOE to reservoir, well and plant parameters |
| `opt_*` (one per example configuration, 16 in all) | Optimization | The configuration of the same name | Designs that minimize LCOE and maximize mean net power (electric, or thermal for direct heat); see [Optimizations](#optimizations) |

On hold, under `_on_hold/`: `opt_hydro_df_electric_surrogate`, the `opt_hydro_df_electric` search on a trained surrogate model; see [On hold](#on-hold).

## Structure of an application

| Kind | Entry point | Pipeline | Also contains |
|---|---|---|---|
| Demo (`demo_*`, `sweep_demo_*`) | `<name>.py` | none | — |
| Sweep (`run_*_sweep`) | `<name>.py` (generate → sweep → summarize → plot) | `dvc.yaml` | `common.py` (design bounds), `params.yaml`, `generate.py`, `sweep.py`, `summarize.py`, `plot.py`, SLURM `<name>_job.sh` |
| Optimization (`opt_*`) | `<name>.py` | `dvc.yaml` | `params.yaml`, SLURM `<name>_job.sh` |

Results go to the application's `outputs/` directory, or to `--save-dir` where the script supports it. DVC stages depend on `src/tango.hash`, so a change to the package invalidates them automatically.

## Running

Smoke-test every application end to end (tiny designs, temporary directories, nothing written to `outputs/`):

```bash
just apps            # add --slow for the real sweep grids
```

Run one application:

```bash
# Demo
uv run python applications/demo_hydro_sf_electric/demo_hydro_sf_electric.py

# Sweep, quick check first, then the cached DVC pipeline
uv run python applications/run_EGS_direct_heat_sweep/run_EGS_direct_heat_sweep.py --smoke
cd applications/run_EGS_direct_heat_sweep && uv run dvc repro

# Optimization, tiny check into a throwaway directory
uv run python applications/opt_hydro_sf_electric/opt_hydro_sf_electric.py \
    --smoke --save-dir /tmp/opt-check --no-plot
```

On the ETH Euler cluster, submit full-size runs with `just slurm <app> ...` from anywhere in the checkout. See [Running on Euler](https://github.com/GEG-ETHZ/TANGO-core/blob/main/docs/guides/euler.md).

| Flag | Applies to | Effect |
|---|---|---|
| `--smoke` | sweeps, optimizations | Sweeps: tiny corner-of-hypercube design set in a temporary directory. Optimizations: a 2-generation, population-6 search with any constraint relaxed |
| `--clean` | sweeps, optimizations | Delete generated outputs before running |
| `--n-workers` / `--n-processes` | sweeps / optimizations | Parallel worker count |
| `--n-max-gen`, `--pop-size` | optimizations | NSGA-II generations and population size |
| `--no-plot`, `--plot-only` | optimizations | Split the search from the plotting, as the DVC stages do |
| `--save-dir` | optimizations | Where results and checkpoints go |
| `--skip-param-check` | optimizations | Skip the check that every decision variable matters |

## Optimizations

Each `opt_*` script defines its decision variables, bounds and objectives and hands them to `tango.pymoo_api.OptApp`, which supplies the command line, the baseline run, the NSGA-II search (`tango.pymoo_api.Minimization`) and the plots. Each has its own DVC pipeline and SLURM job script.

Every application searches mass flow rate, injection pressure and the surface pipe diameter. Doublets also search the injection and production well diameters, plus the target extraction pressure where the production well has a pump. AGS applications also search well depth, horizontal loop length and diameter, and vertical well diameter. Condensing pressures for water and ORC cycles are site conditions and are not searched. Each application also reports production temperature, specific investment cost and OPEX for its Pareto front.

| Application | Plant-specific variables |
|---|---|
| `opt_hydro_sf_electric`, `opt_hydro_sf_electric_5spot`, `opt_EGS_electric` | Flash (separator) pressure |
| `opt_hydro_df_electric` | High-pressure flash pressure, low-pressure flash as a fraction of it |
| `opt_hydro_ORC_electric`, `opt_AGS_ORC_electric`, `opt_CO2_EGS_ORC_electric` | ORC feed-pump (evaporating) pressure |
| `opt_CO2_AGS_ORC_electric` | ORC feed-pump pressure, `preheater` CO2 outlet pressure |
| `opt_CO2_EGS_electric`, `opt_CPG_electric`, `opt_CO2_AGS_electric` | CO2 condensing (turbine exhaust) pressure |
| `opt_CO2_AGS_direct_heat` | District-heating exchanger outlet pressure |
| `opt_hydro_direct_heat`, `opt_EGS_direct_heat`, `opt_CO2_EGS_direct_heat`, `opt_CPG_direct_heat` | None |
| `opt_AGS_direct_heat` | None; also constrains production temperature to at least 105 °C |

Before searching, every application checks that each decision variable matters: moving it up and down from the configuration's own value must change at least one objective or constraint, or the run stops with `InertParameterError` naming it. This costs `1 + 2 × (number of variables)` extra simulations; skip it with `--skip-param-check` once an application is known to be good.

## On hold

Applications in `_on_hold/` are kept but no longer run: `just slurm`, `just apps`, the wheel and `tango_cli init` all skip them.

- `opt_hydro_df_electric_surrogate`: `opt_hydro_df_electric`'s search against a trained surrogate model instead of the real simulation. Its LCOE predictions near the Pareto front never got within the 1% needed to trust the result. Whether to bring it back or delete it is tracked in [#106](https://github.com/GEG-ETHZ/TANGO-core/issues/106).

## Adding an application

1. Copy the closest existing application directory and rename every file prefix to the new name.
2. Point it at a configuration in `example_configs/`. Add a new configuration there first if none fits.
3. Give it a fast end-to-end mode with `--smoke`. The `apps` recipe in the `justfile` finds every `opt_*` application and runs it with `--smoke`; add a sweep's invocation there by hand.
4. List every file in `pyproject.toml`'s `[tool.hatch.build.targets.wheel.force-include]`, so that `tango_cli init --app` ships it.
5. Add a row to the catalog above.
