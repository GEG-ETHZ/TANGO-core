# Items Morteza found during review of
[MR #40](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/merge_requests/40)
- [ ] ...

# TODO Items
- [ ] figure out how to get the optimizer tests fast enough to run for MRs
- [ ] restore and update [GUIDELINES.md](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/blob/main/GUIDELINES.md?ref_type=heads)
- [ ] `SimplePressureDrop` looks more like a mixin interface than a core unit abstraction. Consider moving it to a separate file for clarity.
- [ ] src/tango/runner.py has 3 class definitions that aren't consistent and needs some architectural tweaking
- [ ] Clean up src/tango/units/native/surface/flexible_pp.py::get_surface_diagnostics to better address separation of concerns
- [ ] get_dp_simple, get_flow_res_per_dx and some other methods have overlapping logic, you might want to refactor to avoid repetition.
- [ ] make it so that the following files get saved in a user-specified location:
    - [ ] CPG_hot_opt_log
    - [ ] CPG_hot_opt_objective.png
    - [ ] CPG_hot_opt_variables.png
    - [ ] DF_opt_valves_log
    - [ ] DF_opt_valves_objective.png
    - [ ] DF_opt_valves_variables.png
    - [ ] SF_opt_valve_log
    - [ ] SF_opt_valve_objective.png
    - [ ] SF_opt_valve_variables.png

# Idea for making graph network more human readable
Consider doing this

## Compact Format

Instead of separate `nodes`, `edges`, and per-component sections:

```yaml
power_plant_graph:
  inlet:
    type: Source
    connects_to: valve1
  valve1:
    type: Valve
    p_out: 1
    connects_to: droplet_separator1
  droplet_separator1:
    type: DropletSeparator
    connects_to:
      out1: valve2
      out2: turbine1
```

Benefits:
- Merges component config with graph structure
- Eliminates redundant per-component sections
- Multi-port components use dict for `connects_to`

## Implementation

Add two static methods to `PowerPlant` or `SurfaceUnitFlexiblePP`:

1. **`from_compact_format(specs)`** - Transpose compact format → internal format
2. **`to_compact_format(specs)`** - Convert internal → compact (for export/debug)

This keeps existing parsing code unchanged while offering cleaner YAML.
