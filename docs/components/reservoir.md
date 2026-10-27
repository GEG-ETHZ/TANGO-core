# Reservoir

<span class="tango-chip reservoir">reservoir</span> `components/reservoir/` · config `type: reservoir`
{ .tango-lede .reservoir }

The reservoir sits between the injection well and the production well. It
turns the injected flow into a pressure drop across the well pattern and
returns the produced temperature, which falls over the years as the rock
cools. One variant exists, `lumped`: a closed-form model with no internal
iteration. The well pattern (doublet, five-spot) comes from
`layout.well_pattern`. External reservoir simulators (CMG, MOOSE,
Eclipse, OPM, tNAV) are planned as further variants of this type.

## How the model works

::: tango.components.reservoir.lumped
    options:
      members: false
      show_root_heading: false
      show_root_toc_entry: false

## Config keys

--8<-- "docs/reference/generated/config-reservoir.md"

## Outputs per timestep

Columns in `<name>.smry.csv`, where `<name>` is the component's key in the config.

--8<-- "docs/reference/generated/outputs-reservoir.md"
