# `example_configs/`

The actively-maintained set of `tango` YAML configs. Every file here backs
either a unit/regression test, an application in [`../applications/`](../applications/README.md),
or both — treat this as the current source of truth for what a valid
`tango` config looks like.

Run any of them directly:

```bash
uv run tango_cli run example_configs/hydro_sf_electric.yml
```

Or just validate one without running it:

```bash
uv run tango_cli validate example_configs/hydro_sf_electric.yml
```

## Configs

| File | System |
|---|---|
| `hydro_sf_electric.yml` | Flexible Single-Flash hydrothermal, manual mass flow rate, electric output. |
| `hydro_sf_electric_5spot.yml` | Single-Flash hydrothermal on a five-spot well pattern. |
| `hydro_sf_electric_autoflow.yml` | Single-Flash hydrothermal, mass flow converged automatically (`auto-flow`). |
| `hydro_sf_electric_autopressure.yml` | Single-Flash hydrothermal, injection pressure converged automatically (`auto-pressure`). |
| `hydro_df_electric.yml` | Conventional hydrothermal, double-flash electric power plant (two flash stages). |
| `hydro_ORC_electric.yml` | Hydrothermal system with a binary (ORC) power plant. |
| `hydro_direct_heat.yml` | Hydrothermal, direct heat. |
| `AGS_direct_heat.yml` | Advanced Geothermal System (AGS), closed-loop borehole, direct-heat only (no electricity). |
| `AGS_ORC_electric.yml` | AGS (water), binary (ORC) power plant. |
| `CO2_AGS_direct_heat.yml` | AGS with CO2, direct heat. |
| `CO2_AGS_electric.yml` | AGS with CO2, direct CO2 power plant (CO2 drives the turbine). |
| `CO2_AGS_ORC_electric.yml` | AGS with CO2, binary (ORC) power plant. |
| `EGS_direct_heat.yml` | Enhanced Geothermal System (EGS), doublet/reservoir topology, direct-heat only. |
| `EGS_electric.yml` | EGS (water), electric output. |
| `CO2_EGS_direct_heat.yml` | EGS with CO2, direct heat. |
| `CO2_EGS_electric.yml` | EGS with CO2, direct CO2 power plant (CO2 drives the turbine). |
| `CO2_EGS_ORC_electric.yml` | EGS with CO2, binary (ORC) power plant with a pre-injection cooler. |
| `CPG_direct_heat.yml` | CO2 Plume Geothermal (CPG), direct heat. |
| `CPG_electric.yml` | CO2 Plume Geothermal (CPG), direct CO2 power plant. |

A file name containing `ORC` means a binary plant: the geofluid heats a
secondary working fluid (R245fa) that drives the turbine, and
`tango_cli run --save-dir` writes a phase diagram for each fluid.
