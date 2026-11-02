# Run a simulation

This guide runs one TANGO simulation from a config file, saves its results and points to the tools for running many. It assumes TANGO is installed ([Install](install.md)).

## 1. Choose a config

Start from a maintained config in `templates/`; never write one from scratch. Each covers one system type and is regression-tested, so it is the reference for what a valid config looks like. The list is in [Templates](templates.md). The flagship is `templates/hydro_sf_electric.yml`, a hydrothermal doublet with a single-flash surface plant.

## 2. Validate it

```bash
uv run tango_cli validate templates/hydro_sf_electric.yml
```

`validate` checks that every required field is present, every component type is registered and every schema is satisfied, without running any physics. A problem is reported as a `ConfigError` that names the field.

## 3. Run it

```bash
uv run tango_cli run templates/hydro_sf_electric.yml --save-dir results/
```

The run logs one summary line per timestep. With `--save-dir DIR`, it writes three files:

| File | Contents |
|---|---|
| `<name>.yml` | Every component's final config and state; reload it with `Workflow.from_file()` |
| `<name>.smry.csv` | One row per timestep, one column per recorded quantity |
| `<name>.econ.csv` | The economics: CAPEX by category, OPEX, LCOE. Omitted if the config has no `economic:` block |

Every run needs either `--save-dir DIR` or `--no-save`, which writes nothing; without one of them `tango_cli run` stops with an error, so results are never lost by forgetting the flag. To see every convergence iteration, add `--log-level DEBUG`. [One run](../runtime/one-run.md) shows what happens inside a run.

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

workflow = Workflow.from_file("templates/hydro_sf_electric.yml")
workflow.run()
```

Optimizations use this pattern: load a config, change values, build a `Workflow` and run it.

## Tests, templates and applications

Three directories hold runnable material, each for a different purpose:

| Directory | Purpose | Run with |
|---|---|---|
| `tests/` | Automated correctness checks. `tests/unit/` covers components in isolation; `tests/regtest/` runs full simulations, including a golden LCOE per template | `just test` (see [Running checks](install.md#running-checks)) |
| [`templates/`](templates.md) | The maintained configs; each backs a test, an application or both | `uv run tango_cli run templates/<file>.yml --save-dir results/` |
| [`applications/`](applications.md) | Multi-run pipelines built on a template: optimizations and demos | DVC or the app's own script |
