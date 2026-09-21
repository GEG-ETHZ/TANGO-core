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
| `hydro_df_electric.yml` | Conventional hydrothermal, double-flash electric power plant (two flash stages). |
| `hydro_orc_electric.yml` | Hydrothermal system with a binary (ORC) power plant. |
| `AGS_direct_heat.yml` | Advanced Geothermal System (AGS), closed-loop borehole, direct-heat only (no electricity). |
| `EGS_direct_heat.yml` | Enhanced Geothermal System (EGS), doublet/reservoir topology, direct-heat only. |
