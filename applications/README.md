# `applications/`

Multi-run pipelines (demos, sweeps, optimizations) built on top of one
[`../example_configs/`](../example_configs/README.md) config — as opposed to
[`../example_configs/`](../example_configs/README.md) itself, which is
single-simulation configs only. Each app is its own directory; nothing here
is a library import target for anything outside its own directory.

## Demos — `demo_*` / `sweep_demo_*`

Standalone scripts, no DVC pipeline, no job script. Run directly:

```bash
uv run python applications/demo_hydro_sf_electric/demo_hydro_sf_electric.py
```

| App | What it shows |
|---|---|
| `demo_hydro_sf_electric` | Runs `hydro_sf_electric.yml` and plots four figures (axial T profile, reservoir T, etc.). |
| `demo_well_mesh_convergence` | Mesh-convergence check for `NumericalWell`'s cell resolution — documents *why* the default cell length is what it is. |
| `sweep_demo_AGS_direct_heat` | Minimal parameter-sweep demo: the dict-modify-then-reinstantiate `Workflow` pattern, not a real sweep pipeline. |

## Optimizations — `opt_*`

One app per example config: multi-objective optimization (NSGA2 via
`tango.pymoo_api.Minimization`) minimizing LCOE and maximizing mean net
power (electric, or thermal for the direct-heat configs), each with its own
DVC pipeline and SLURM job script. Every app script defines its own decision
variables, bounds, and objectives and hands them to `tango.pymoo_api.OptApp`,
which supplies the CLI, the baseline run, the search, and the plots.

Every app searches mass flow rate, injection pressure, and the surface pipe
diameter. Doublets also search the injection and production well diameters,
plus the target extraction pressure where the production well has a pump; AGS
apps also search well depth, horizontal loop length and diameter, and
vertical well diameter. Condensing pressures for water and ORC cycles are
site conditions and are not searched. Each app also reports production
temperature, specific investment cost, and OPEX for its Pareto front.

| App | Plant-specific variables |
|---|---|
| `opt_hydro_sf_electric`, `opt_hydro_sf_electric_5spot`, `opt_EGS_electric` | Flash (separator) pressure |
| `opt_hydro_df_electric` | High-pressure flash pressure, low-pressure flash as a fraction of it |
| `opt_hydro_ORC_electric`, `opt_AGS_ORC_electric`, `opt_CO2_EGS_ORC_electric` | ORC feed-pump (evaporating) pressure |
| `opt_CO2_AGS_ORC_electric` | ORC feed-pump pressure, `preheater` CO2 outlet pressure |
| `opt_CO2_EGS_electric`, `opt_CPG_electric`, `opt_CO2_AGS_electric` | CO2 condensing (turbine exhaust) pressure |
| `opt_CO2_AGS_direct_heat` | District-heating exchanger outlet pressure |
| `opt_hydro_direct_heat`, `opt_EGS_direct_heat`, `opt_CO2_EGS_direct_heat`, `opt_CPG_direct_heat` | None |
| `opt_AGS_direct_heat` | None; also constrains production temperature to at least 105 °C |

Before searching, every app checks that each decision variable actually
matters: moving it up and down from the config's own value must change at
least one objective or constraint, or the run stops with
`InertParameterError` naming it. This costs `1 + 2 × (number of variables)`
extra simulations; skip it with `--skip-param-check` once an app is known to
be good.

For a fast end-to-end check, run an app with `--smoke` (a 2-generation,
population-6 search plus any relaxed constraint) and a throwaway `--save-dir`.
The top-level `justfile`'s `apps` recipe does this for every app, running
`--no-plot` then `--plot-only` against the same `--save-dir` to exercise the
two-stage optimize/plot split in each app's `dvc.yaml`.

## On hold — `_on_hold/`

Apps that are kept but no longer run: `just slurm`, `just apps`, the wheel
and `tango apps` all skip them.

- `opt_hydro_df_electric_surrogate`: `opt_hydro_df_electric`'s search against
  a trained surrogate model instead of the real simulation. Its LCOE
  predictions near the Pareto front never got within the 1% needed to trust
  the result. Whether to bring it back or delete it is tracked in
  [#106](https://github.com/GEG-ETHZ/TANGO-core/issues/106).

## Sweeps — `run_*_sweep`

Full generate → sweep → summarize → plot DVC pipelines, one directory per
sweep. Each has a `common.py` (grid/LHS bounds), `dvc.yaml`, `params.yaml`
(tunable knobs DVC tracks for staleness), a `--clean` flag, a `--smoke` flag
(tiny corner-of-hypercube design matrix, written to a throwaway tempdir —
never touches `outputs/`), and a SLURM `*_job.sh` script for Euler.

| App | Sweeps |
|---|---|
| `run_AGS_direct_heat_sweep` | Well depth × mass flow rate × horizontal loop length × loop diameter (12,870 designs) for the Triemli AGS site. |
| `run_EGS_direct_heat_sweep` | Well depth × mass flow rate (100 designs) for the Triemli EGS site. |
| `run_hydro_df_electric_sweep` | One-at-a-time (OFAT) sweep across the double-flash topology's material/reservoir/well/surface-plant parameters. |

Run one via DVC (from the app's own directory):

```bash
cd applications/run_hydro_df_electric_sweep
uv run dvc repro    # runs only stale stages, caches the rest
```

Or submit it on Euler/other SLURM clusters (see the top-level `README.md`'s
"Running on Euler" section):

```bash
just slurm run_hydro_df_electric_sweep
```
