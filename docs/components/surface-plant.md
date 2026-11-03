# Surface plant

<span class="tango-chip surface">surface</span> `components/surface/` · config `type: surface`, variant `graph`
{ .tango-lede .surface }

The surface plant turns the produced fluid into electricity or heat and
returns it, cooled, to the injection well. Its layout is not hard-coded:
the config's `power_plant` block lists TESPy nodes (turbines, separators,
heat exchangers, pumps) and the edges between them, and TANGO solves that
network every timestep. A single-flash, double-flash, ORC or direct-heat
plant is therefore a config change, not new code. See
`templates/hydro_sf_electric.yml` (single flash) and
`templates/AGS_direct_heat.yml` (direct heat) for complete graphs.
An Aspen Plus connection is planned as a further variant.

## How the model works

::: tango_core.components.surface.graph
    options:
      members: false
      show_root_heading: false
      show_root_toc_entry: false

## Plant graph nodes

Every `power_plant.nodes.<name>` entry has a `type` from this list and
an optional `role` that decides which plant total its power counts toward.

--8<-- "docs/reference/generated/surface-nodes.md"

## Config keys

--8<-- "docs/reference/generated/config-surface.md"

## Outputs per timestep

Columns in `<name>.smry.csv`, where `<name>` is the component's key in the config.

--8<-- "docs/reference/generated/outputs-surface.md"
