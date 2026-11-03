# Economics

<span class="tango-chip economic">economic</span> `components/economic/` · config `economic: type: doublet`
{ .tango-lede .economic }

Economics is one central component, configured in the top-level
`economic:` block. It is not part of the fluid loop: it runs once, after
the last timestep, reads the solved wells and surface plant, and computes
capital cost (CAPEX), operating cost (OPEX) and the levelized cost of
electricity or heat (LCOE/LCOH). It prices the wells (from their geometry
and pump power) and the surface plant (from its turbines, pumps and
condensers); it does not price the reservoir, and it never feeds back into
the physics. Its results are the objectives most optimizations minimize.

## How the model works

::: tango_core.components.economic.doublet
    options:
      members: false
      show_root_heading: false
      show_root_toc_entry: false

## Config keys

--8<-- "docs/reference/generated/config-economic.md"

## Results

One row in `<name>.econ.csv`, written when the config has an `economic:` block.

--8<-- "docs/reference/generated/outputs-economic.md"
