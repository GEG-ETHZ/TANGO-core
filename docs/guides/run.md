# Run a simulation

This guide runs one TANGO simulation from a config file, saves its results and points to the tools for running many. It assumes TANGO is installed ([Install](install.md)).

## 1. Choose a config

Start from a maintained config in `example_configs/`; never write one from scratch. Each covers one system type and is regression-tested, so it is the reference for what a valid config looks like. The list is in [Example configs](example-configs.md). The flagship is `example_configs/hydro_sf_electric.yml`, a hydrothermal doublet with a single-flash surface plant.

## 2. Validate it

```bash
uv run tango_cli validate example_configs/hydro_sf_electric.yml
```

`validate` checks that every required field is present, every component type is registered and every schema is satisfied, without running any physics. A problem is reported as a `ConfigError` that names the field.

## 3. Run it

```bash
uv run tango_cli run example_configs/hydro_sf_electric.yml --save-dir results/
```

The run logs one summary line per timestep. With `--save-dir DIR`, it writes three files:

| File | Contents |
|---|---|
| `<name>.yml` | Every component's final config and state; reload it with `Workflow.from_file()` |
| `<name>.smry.csv` | One row per timestep, one column per recorded quantity |
| `<name>.econ.csv` | The economics: CAPEX by category, OPEX, LCOE. Omitted if the config has no `economic:` block |

Nothing is written without `--save-dir`. To see every convergence iteration, add `--log-level DEBUG`. [One run](../runtime/one-run.md) shows what happens inside a run.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | The config is invalid (`ConfigError`) |
| `2` | The simulation failed, for example it did not converge or violated the fracking limit (any other `TangoError`) |

An unexpected exception that is not a `TangoError` (a bug) also ends the process with exit code `1`, but prints a Python traceback instead of a one-line message. Report it as a bug.

`uv run tango_cli --version` prints the installed version and the internal distribution notice. Quote the version together with any result you share.

## 4. Run from Python

```python
from tango.workflows.workflow import Workflow

workflow = Workflow.from_file("example_configs/hydro_sf_electric.yml")
workflow.run()
```

Sweeps and optimizations use this pattern: load a config, change values, build a `Workflow` and run it.

## Tests, example configs and applications

Three directories hold runnable material, each for a different purpose:

| Directory | Purpose | Run with |
|---|---|---|
| `tests/` | Automated correctness checks. `tests/unit/` covers components in isolation; `tests/regtest/` runs full simulations, including a golden LCOE per example config | `just test` (see [Running checks](install.md#running-checks)) |
| [`example_configs/`](example-configs.md) | The maintained configs; each backs a test, an application or both | `uv run tango_cli run example_configs/<file>.yml` |
| [`applications/`](applications.md) | Multi-run pipelines built on an example config: sweeps, optimizations and demos | DVC or the app's own script |

### Run a sweep

Each `run_*_sweep/` application is a DVC pipeline (generate → sweep → summarize → plot). It has its own `dvc.yaml`, a `params.yaml` with the tunable settings DVC tracks, and a SLURM `*_job.sh` script. Check the pipeline end to end with `--smoke` first; it uses a tiny sample, writes to a temporary directory and never touches `outputs/`. Then run the stale stages:

```bash
cd applications/run_hydro_df_electric_sweep
uv run python run_hydro_df_electric_sweep.py --smoke   # quick end-to-end check
uv run dvc repro                                       # the real sweep
```

DVC reruns only the stages whose inputs changed. To run the sweep on a SLURM cluster, see [Running on Euler](euler.md).
