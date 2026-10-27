# Outputs

`tango_cli run <config> --save-dir DIR` writes three files; how to run it
is in [Run a simulation](../guides/run.md#3-run-it). This page lists what
each column means. The tables are generated from the code
(`tools/gen_reference.py`), so they list exactly what the files contain.

| File | Contents |
|---|---|
| `<stem>.yml` | The config with every solved value, reloadable with `Workflow.from_file()` |
| `<stem>.smry.csv` | One row per timestep: `timestep`, `year`, then one column per scalar history value of each component, named `<name>_<value>` |
| `<stem>.econ.csv` | One row: the economics results, if the config has an `economic:` block |

Spatial profiles (for example the temperature in every cell of a numerical
well) and the per-node detail of the surface plant are kept in
`<stem>.yml`, not in the CSV.

## <span class="tango-chip well">well</span> Wells

--8<-- "docs/reference/generated/outputs-well.md"

## <span class="tango-chip reservoir">reservoir</span> Reservoir

--8<-- "docs/reference/generated/outputs-reservoir.md"

## <span class="tango-chip surface">surface</span> Surface plant

--8<-- "docs/reference/generated/outputs-surface.md"

## <span class="tango-chip economic">economic</span> Economics (`<stem>.econ.csv`)

--8<-- "docs/reference/generated/outputs-economic.md"
