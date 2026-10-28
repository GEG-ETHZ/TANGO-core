# Grouped subsurface

<span class="tango-chip well">well</span> `components/well/grouped_subsurface.py` · config `type: grouped_subsurface`
{ .tango-lede .well }

An AGS loop's whole subsurface (injection well, horizontal well and
production well) as one circuit component, so the same config shape can be
simulated by different models: tango's own numerical wells, or RAFT, which
also models the surrounding rock.

| Variant | Use it when | Model |
|---|---|---|
| `numerical` | The standard AGS loop, same result as three separate well components | Three numerical wells marched in sequence |
| `raft` | The rock's heat exchange should come from a 3D finite-element model | RAFT simulates the wells and the rock; needs the optional RAFT install ([Install](../guides/install.md#optional-raft-subsurface-simulator)) |

Example: `templates/AGS_ORC_electric_grouped_subsurface.yml` (`numerical`) and
`templates/AGS_ORC_electric_raft.yml` (`raft`), the same site and plant.

## How the models work

### The grouped loop

::: tango_core.components.well.grouped_subsurface
    options:
      members: false
      show_root_heading: false
      show_root_toc_entry: false

### RAFT coupling

::: tango_core.external.raft_wrapper
    options:
      members: false
      show_root_heading: false
      show_root_toc_entry: false

## Config keys

--8<-- "docs/reference/generated/config-grouped_subsurface.md"

## Outputs per timestep

Columns in `<name>.smry.csv`, where `<name>` is the component's key in the config.
RAFT's step sizes and its profile along the well are lists per timestep, so
they are in `<stem>.yml`, not the CSV.

--8<-- "docs/reference/generated/outputs-grouped_subsurface.md"
