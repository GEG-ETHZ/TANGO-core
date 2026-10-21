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
| `opt_hydro_sf_electric` | Optimization | `hydro_sf_electric.yml` | Mass flow and wellhead pressures that minimize LCOE and maximize net power |
| `opt_hydro_df_electric` | Optimization | `hydro_df_electric.yml` | The same objectives for the double-flash plant |
| `opt_hydro_df_electric_surrogate` | Surrogate optimization | `hydro_df_electric.yml` | The same search on a trained surrogate model, re-checked against real runs |
| `opt_AGS_direct_heat` | Optimization | `AGS_direct_heat.yml` | AGS depth, loop geometry and flow that minimize LCOE, with a minimum production temperature |

## Structure of an application

| Kind | Entry point | Pipeline | Also contains |
|---|---|---|---|
| Demo (`demo_*`, `sweep_demo_*`) | `<name>.py` | none | — |
| Sweep (`run_*_sweep`) | `<name>.py` (generate → sweep → summarize → plot) | `dvc.yaml` | `common.py` (design bounds), `params.yaml`, `generate.py`, `sweep.py`, `summarize.py`, `plot.py`, SLURM `<name>_job.sh` |
| Optimization (`opt_*`) | `<name>.py` | `dvc.yaml` | `params.yaml`, SLURM `<name>_job.sh` |
| Surrogate (`opt_*_surrogate`) | `run_trajectory.py` → `train_surrogate.py` → `optimize_surrogate.py` → `validate_surrogate.py` | `dvc.yaml` | `common.py`, `params.yaml`, SLURM job script |

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

# Optimization, tiny check (no --smoke flag; use a small population)
uv run python applications/opt_hydro_sf_electric/opt_hydro_sf_electric.py \
    --n-max-gen 2 --pop-size 6 --save-dir /tmp/opt-check --no-plot
```

On the ETH Euler cluster, submit the job script instead. See [Running on Euler](https://github.com/GEG-ETHZ/TANGO-core/blob/main/docs/guides/euler.md).

```bash
sbatch --cpus-per-task=16 run_hydro_df_electric_sweep_job.sh --n-samples 200
```

| Flag | Applies to | Effect |
|---|---|---|
| `--smoke` | sweeps | Tiny corner-of-hypercube design set in a temporary directory |
| `--clean` | sweeps, optimizations | Delete generated outputs before running |
| `--n-workers` / `--n-processes` | sweeps / optimizations | Parallel worker count |
| `--n-max-gen`, `--pop-size` | optimizations | NSGA-II generations and population size |
| `--no-plot`, `--plot-only` | optimizations | Split the search from the plotting, as the DVC stages do |
| `--save-dir` | optimizations | Where results and checkpoints go |

## Adding an application

1. Copy the closest existing application directory and rename every file prefix to the new name.
2. Point it at a configuration in `example_configs/`. Add a new configuration there first if none fits.
3. Give it a fast end-to-end mode: `--smoke` for a sweep, or a small `--n-max-gen`/`--pop-size` for an optimization. Add that invocation to the `apps` recipe in the `justfile`.
4. List every file in `pyproject.toml`'s `[tool.hatch.build.targets.wheel.force-include]`, so that `tango_cli init --app` ships it.
5. Add a row to the catalog above.
