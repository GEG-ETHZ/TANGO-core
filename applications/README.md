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

Multi-objective optimization (NSGA2 via `tango.pymoo_api.Minimization`) against
a real config, each with its own DVC pipeline and SLURM job script. No
dedicated `--smoke` flag — use tiny `--n-max-gen`/`--pop-size` plus a
throwaway `--save-dir` for a fast end-to-end check instead (see the top-level
`justfile`'s `demos` recipe for the exact invocation).

| App | Optimizes |
|---|---|
| `opt_hydro_sf_electric` | Single-flash: mass flow rate, injection wellhead pressure, target extraction pressure → minimize LCOE, maximize mean net electric power. |
| `opt_hydro_df_electric` | Same objectives, double-flash topology. |
| `opt_hydro_df_electric_surrogate` | Same search, against a trained surrogate model instead of the real simulation (see its own `train_surrogate.py`/`validate_surrogate.py`) — much cheaper per evaluation. |
| `opt_AGS_direct_heat` | AGS direct-heat design (depth, loop length/diameter, mass flow rate) → minimize LCOE, subject to a minimum production-temperature constraint. |

Each app runs `--no-plot` then `--plot-only` against the same `--save-dir` in
CI/smoke checks, exercising the two-stage optimize/plot split described in its
own `dvc.yaml`.

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

Or submit the job script on Euler/other SLURM clusters (see the top-level
`README.md`'s "Running on Euler" section):

```bash
sbatch --cpus-per-task=16 run_hydro_df_electric_sweep_job.sh --n-samples 200
```
