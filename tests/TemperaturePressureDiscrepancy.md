# Surface Temperature and Pressure Discrepancy

Investigation note (2026-07-22): `surface_temperature` and `surface_pressure` can be set both in
`common:` and in the surface component, and components can end up reading different values. This
note records how the two sources are merged; follow-up work is tracked in `docs/tango_tasks.md`.

## Surface temperature and pressure can be defined in two places
In the input .yml files the user can define the surface temperature and pressure in the ``common:`` and ``components: surface: `` section
```yaml
common:
    surface_temperature: 300
    surface_pressure: 110000

components:
    surface:
        surface_temperature: 288
        surface_pressure: 100000
```
In the code for building component objects

```python
def _build_components(
    components_block: dict[str, Any],
    common: dict[str, Any],
    layout: dict[str, Any],
    dt_years: float,
) -> dict[str, Component]:

    # Pull layout/sim_config fields that some components need at spec construction time
    layout_extras: dict[str, Any] = {
        "well_spacing": layout.get("well_spacing", 707.0),
        "surface_temperature": common.get(
            "surface_temperature",
            components_block.get("surface", {}).get("surface_temperature", 288.0),
        ),
        "dt_years": dt_years,
    }
```

We take "surface_temperature" from the common block, and failing that the surface block. However later in build components we merge the "shared parameters" and the "own parameters" from the component block. The own parameters will take precedence and so the surface will take the surface_temperature defined in the component block but a production well will take the surface temperature defined in common.

```python
declared = set(cls.model_fields.keys())
shared = {k: v for k, v in {**common, **layout_extras}.items() if k in declared}
own = {k: v for k, v in comp_cfg.items() if k not in ("type", "unit")}
merged: dict[str, Any] = {**shared, **own}
```

My suggestion is to force the surface to use the surface temperature and pressure defined in common, remove surface_temperature and surface_pressure as allowed parameters in the surface component block.
