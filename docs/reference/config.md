# Config reference

Every key a TANGO config accepts, generated from the code
(`tools/gen_reference.py` reads the pydantic schemas and their
docstrings). How the blocks become objects is described in
[Config to objects](../architecture/config.md); start a new config from an
[template](../guides/templates.md).

## `title` and `description`

--8<-- "docs/reference/generated/config-description.md"

## `common`

Fluid and rock properties shared by every component.

--8<-- "docs/reference/generated/config-common.md"

## `layout`

--8<-- "docs/reference/generated/config-layout.md"

## `sim_config`

--8<-- "docs/reference/generated/config-sim_config.md"

## `components`: <span class="tango-chip well">well</span>

--8<-- "docs/reference/generated/config-well.md"

## `components`: <span class="tango-chip reservoir">reservoir</span>

--8<-- "docs/reference/generated/config-reservoir.md"

## `components`: <span class="tango-chip surface">surface</span>

--8<-- "docs/reference/generated/config-surface.md"

Plant graph nodes:

--8<-- "docs/reference/generated/surface-nodes.md"

## `economic` <span class="tango-chip economic">economic</span>

--8<-- "docs/reference/generated/config-economic.md"
