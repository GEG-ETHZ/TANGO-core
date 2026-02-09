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
These tasks are generally aimed at making TANGO more in line with well established best practices in software development.

# copied from https://gitlab.ethz.ch/geg/tango-projects/tango-super/-/issues/3e
## Urgent/Important
- [x] make sure users have control over where output and artifact files end up and that it's never under `src/tango/`.  Additionally, it should be possible for the user to not save any files at all.  This is important because full factorial HPC runs will generate a ton of files (storage usage!) if this is not fixed.  
- [ ] eliminate dueling parameters, e.g. `specs`, `parameter_overrides`, and `params_json` in src/tango/utils.py.  It's really easy to accidentally and silently set conflicting parameters without any awareness.  
- [x] remove `eval` functions because they are masking circular imports and generally make it more difficult to reason about what TANGO is doing. They also create security risks.

## Readability/Maintainability/Usability Improvements
- [ ] lots of places where there are hardcoded values (e.g. `100_000` for the bar to Pa conversion, `1_000_000` for MPa to Pa conversion) without any local context explaining the value that could be using constants defined in the constants module (e.g. BAR_TO_PA), which would make their purpose clear to other devs/users.  Having unexplained float numbers for unit conversions in the code is exactly how NASA + ESA crashed a spacecraft into Mars at 50,000 kph.  Any variables with non standard units should have units in the name, e.g. `P_outet_MPa`.
- [ ] append units of measure (e.g. `pressure_MPa`) to variable names for variables with non-MKS SI units 
- [ ] wellbore flow and heat transfer calculations assume turbulent flow.  We should check `Re` and maybe adjust accordingly
- [ ] make state variables lockable so it's easier to trace where they get updated!
- [ ] change all the `_private_vars` to `public_vars` or `__private_vars`, depending on rationale.  In python, preceding `_` has no real effect and should not be used without an explanation (which is not provided anywhere in TANGO)
- [ ] remove all hardcoded absolute paths
- [ ] make tests to cover `optimizerr.py`
- [ ] build out unit tests for individual components -- this enables easier debugging when tests fail 
- [ ] modify existing system-level functional tests to compare expected results against live python objects rather than data loaded from a file.  This will make debugging way easier.    
- [ ] make options to change verbosity: no prints, some prints, extensive prints, ...
- [x] setup gitlab pipelines or github actions to automate testing -- [done](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/jobs/1369333)
- [x] [setup pyproject.toml for venv, uv, or pixi](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/issues/37) to make TANGO work as a project or a package (needs to be both)
- [x] `specs` and `_specs` (inconsistent naming!) carry around unrelated specs for some objects -- e.g. `production_well` and `production_well_pump` have different well lengths, as expected, but they both have things like `rock_density`, `thermal_gradient`, and other unrelated parameters.
for example:
```
type(v)
<class 'tango.units.native.well.injection_well.InjectionWellUnitNative'>
[k for k in v.specs if "diameter" in k]
['pipe_diameter', 'diameter', 'well_diameter_seq']
```
has `pipe_diameter` for the surface `diameter` for the injection wellbore, and `well_diameter_seq` for the injection wellbore.  `specs` nested in the injection well should not have surface properties.  This could easily get misused.
- [x] remove star imports.  The [official style guide](https://peps.python.org/pep-0008/#imports) recommends against using them, and the do things like masking where objects actually come from. For example, `dataclass` in `flexible_pp.py` was coming from the `tango.dataclasses` module, but it actually originally came from python's `dataclasses` module, which was also imported it `flexible_pp.py`.  This lack of clarity causes obscures the dependency graph among modules and elevates the risk of accidental circular imports.
- [x] remove code that adds tango by putting it on the path -- this is very bad practice because it subverts any possibility of type and interface checking
- [x] make sure TANGO is runnable via script and interactively, not just via CLI app

## Foundational Improvements for TANGO Long Term Objectives
- [ ] ability to copy and run standalone any submodule within an existing tango simulation (would enable much richer error context and troubleshooting steps)
- [x] make it so that edits in live, interactive TANGO instance have effect on result (show demo of code where this does not happen as expected).  This would enable easier ad hoc parameter sweeps in python scripts.
- [ ] make sure that something like state/history is implemented so that data from inside individual components can be accessed after simulation
    - [ ] `state` for tracking all state variables within an object
    - [ ] `history` for tracking history of `state`
    - [ ] `iter_history` for tracking history of `history` across solver iterations

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
