# Wells

<span class="tango-chip well">well</span> `components/well/` · config `type: injection_well`, `production_well`, `production_well_with_pump`, `horizontal_well`
{ .tango-lede .well }

Wells carry the fluid between the surface and the reservoir: the injection
well takes the cooled fluid down, the production well brings the hot fluid
up, and a pumped production well adds the pressure the surface plant
needs. Every well computes friction and the hydrostatic pressure change;
the numerical variant also computes the heat exchanged with the rock.

| Variant | Use it when | Model |
|---|---|---|
| `lumped` | Quick studies and sweeps | One segment, closed form; temperature follows the geothermal gradient, no heat exchange with the rock |
| `numerical` | Heat loss to the rock matters, or the well is inclined or horizontal (`angle_from_vert_deg`) | Marched cell by cell, with CoolProp fluid properties and a heat-loss model at every node |

`horizontal_well` (AGS closed loops) exists only as `numerical`.
External well simulators (Moskito, OLGA, T2Well) are planned as further
variants.

## How the models work

### Lumped wells

::: tango.components.well.lumped
    options:
      members: false
      show_root_heading: false
      show_root_toc_entry: false

### Numerical wells

::: tango.components.well.numerical
    options:
      members: false
      show_root_heading: false
      show_root_toc_entry: false

## Config keys

--8<-- "docs/reference/generated/config-well.md"

## Outputs per timestep

Columns in `<name>.smry.csv`, where `<name>` is the component's key in the config.

--8<-- "docs/reference/generated/outputs-well.md"
