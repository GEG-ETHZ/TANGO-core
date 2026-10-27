# Example configurations

`example_configs/` holds the maintained reference configurations for TANGO. Each file describes one complete geothermal system, from reservoir to economics. Each one is a valid starting point for your own study. Every file is covered by the full-length regression suite ([`tests/regtest/test_example_configs.py`](https://github.com/GEG-ETHZ/TANGO-core/blob/main/tests/regtest/test_example_configs.py)), which fails if a file here has no golden-value check. These files are therefore the source of truth for what a valid configuration looks like. `tango_cli init` ships them with the installed package.

## Run one

```bash
uv run tango_cli validate example_configs/hydro_sf_electric.yml   # check the file, no simulation
uv run tango_cli run example_configs/hydro_sf_electric.yml --save-dir results/
```

## Configurations

| File | System type | Plant and product | Fluid | Injection mode | Used by |
|---|---|---|---|---|---|
| `hydro_sf_electric.yml` | Hydrothermal, doublet | Single-flash, electricity | H₂O | `manual-fracking-check` | Flagship reference; `demo_hydro_sf_electric`, `demo_well_mesh_convergence`, `opt_hydro_sf_electric`, LCOE regression |
| `hydro_sf_electric_5spot.yml` | Hydrothermal, five-spot pattern | Single-flash, electricity | H₂O | `manual` | `opt_hydro_sf_electric_5spot` |
| `hydro_df_electric.yml` | Hydrothermal, doublet | Double-flash, electricity | H₂O | `manual-fracking-check` | `opt_hydro_df_electric`, `run_hydro_df_electric_sweep` |
| `hydro_ORC_electric.yml` | Hydrothermal, doublet | Binary (ORC), electricity | H₂O | `manual-fracking-check` | `opt_hydro_ORC_electric` |
| `hydro_direct_heat.yml` | Hydrothermal, doublet | Heat exchanger, heat | H₂O | `manual-fracking-check` | `opt_hydro_direct_heat` |
| `EGS_electric.yml` | Enhanced (EGS), doublet, Triemli site | Single-flash, electricity | H₂O | `manual-fracking-check` | `opt_EGS_electric` |
| `EGS_direct_heat.yml` | Enhanced (EGS), doublet, Triemli site | Heat exchanger, heat | H₂O | `manual-fracking-check` | `opt_EGS_direct_heat`, `run_EGS_direct_heat_sweep` |
| `CO2_EGS_electric.yml` | Enhanced (EGS), doublet | Direct CO₂ turbine, electricity | CO₂ | `manual-fracking-check` | `opt_CO2_EGS_electric` |
| `CO2_EGS_ORC_electric.yml` | Enhanced (EGS), doublet | Binary (ORC) with a pre-injection cooler, electricity | CO₂ | `manual-fracking-check` | `opt_CO2_EGS_ORC_electric` |
| `CO2_EGS_direct_heat.yml` | Enhanced (EGS), doublet | Heat exchanger, heat | CO₂ | `manual-fracking-check` | `opt_CO2_EGS_direct_heat` |
| `CPG_electric.yml` | CO₂ plume (CPG), doublet | Direct CO₂ turbine, electricity | CO₂ | `manual-fracking-check` | `opt_CPG_electric` |
| `CPG_direct_heat.yml` | CO₂ plume (CPG), doublet | Heat exchanger, heat | CO₂ | `manual-fracking-check` | `opt_CPG_direct_heat` |
| `AGS_direct_heat.yml` | Advanced closed loop (AGS), Triemli site | Heat exchanger, heat | H₂O | `manual` | `opt_AGS_direct_heat`, `run_AGS_direct_heat_sweep`, `sweep_demo_AGS_direct_heat` |
| `AGS_ORC_electric.yml` | Advanced closed loop (AGS) | Binary (ORC), electricity | H₂O | `manual` | `opt_AGS_ORC_electric` |
| `CO2_AGS_electric.yml` | Advanced closed loop (AGS) | Direct CO₂ turbine, electricity | CO₂ | `manual` | `opt_CO2_AGS_electric` |
| `CO2_AGS_ORC_electric.yml` | Advanced closed loop (AGS) | Binary (ORC), electricity | CO₂ | `manual` | `opt_CO2_AGS_ORC_electric` |
| `CO2_AGS_direct_heat.yml` | Advanced closed loop (AGS) | Heat exchanger, heat | CO₂ | `manual` | `opt_CO2_AGS_direct_heat` |

How a configuration maps onto the code is described in [Config to objects](https://github.com/GEG-ETHZ/TANGO-core/blob/main/docs/architecture/config.md). The meaning of each injection mode is described in [Boundary-condition iteration](https://github.com/GEG-ETHZ/TANGO-core/blob/main/docs/runtime/bc-iteration.md).

A file name containing `ORC` means a binary plant: the geofluid heats a secondary working fluid (R245fa) that drives the turbine, and `tango_cli run --save-dir` writes a phase diagram for each fluid.

## Conventions

1. **One system per file.** Each file has a `title`, optionally a `description` block (`summary`, `date`, `description`), and inline comments on every physical parameter with its unit.
2. **SI units throughout** (Pa, K, kg/s, m), unless a comment states otherwise.
3. **The header comment draws the component circuit**, in `component_idx` order.
4. **Names follow `<system>_<plant>_<product>[_<variant>].yml`**, for example `hydro_sf_electric_5spot.yml`.

## Adding a configuration

1. Copy the closest existing file and change only what differs.
2. Run `uv run tango_cli validate` and then `uv run tango_cli run` on it.
3. Add it to `_CONFIGS` in `tests/regtest/test_example_configs.py`, with its golden LCOE value. The suite fails until you do.
4. Add a row to the table above.
