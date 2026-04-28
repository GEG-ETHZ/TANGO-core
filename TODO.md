# TODO Items

## Refactor
This section provides a high level overview of Chad's vision for making TANGO
more robust for long-term maintainability and extensibility.
- [State Management](#state-management)
- Architecture -- the following concepts will make it easier to understand the code structure and flow
    - [ ] perfect congruence between input files and code objects
    - [ ] strong congruence between code objects and module structure
    - [ ] strong congruence with actual physical system
    - [ ] [Graph Network Architecture](#graph-network-architecture)
- Code Quality
    - [ ] Implement [.gitlab-ci.yml](
        https://gitlab.ethz.ch/geg/templates/python-template/-/blob/main/%7B%7Bcookiecutter.project_slug%7D%7D/.gitlab-ci.yml?ref_type=heads)

## Misc.
- [ ] fix and beef up license manager.  See https://gitlab.ethz.ch/geg/computing-guide/-/wikis/Understanding-Software-Licenses
- [ ] restore and update [GUIDELINES.md](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/blob/main/GUIDELINES.md?ref_type=heads)
- [ ] `SimplePressureDrop` looks more like a mixin interface than a core unit abstraction. Consider moving it to a separate file for clarity.
- [ ] src/tango/runner.py has 3 class definitions that aren't consistent and needs some architectural tweaking
- [ ] Clean up src/tango/units/native/surface/flexible_pp.py::get_surface_diagnostics to better address separation of concerns
- [ ] get_dp_simple, get_flow_res_per_dx and some other methods have overlapping logic, you might want to refactor to avoid repetition.
- [ ] Investigate what it would take to have round trip symmetry in writing
      `tango.specs` to a yaml file.  Right now, merged defaults would be expanded (the
      common dict gets merged with unit-specific dicts), and it may be worth trying to
      change the way this works so that specs doesn't have any preprocessing relative
      to what comes in for the original file
- [ ] cleanup how `addons_manager` works.
    - [ ] make it ok with arbitrary tango directory names other than just `TANGO`
    - [ ] make it import as a subpackage

- [ ] make it so that `TANGO` can store all state variables and results in ArangoDB,
      along with specs and specs_hash


## Testing
- [x] get the pytest tests working on all relevant platforms
  - [ ] make sure all paths are relative
- [ ] figure out how to get the optimizer tests fast enough to run for MRs
- [ ] build out more/better unit tests
- [ ] reduce number of routine tests of examples by gating with environment variables after more robust unit testing is implemented
- [x] make tests to cover `optimizerr.py`
- [ ] build out unit tests for individual components -- this enables easier
    debugging when tests fail
- [ ] modify existing system-level functional tests to compare expected results
    against live python objects rather than data loaded from a file.  This will make
    debugging way easier.
- [x] setup gitlab pipelines or github actions to automate testing --
    [done](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/jobs/1369333)


## Artifact Locations
- [x] make it so that the *_log (e.g. CPG_hot_opt_log) and *.png (e.g.
    CPG_hot_opt_log) files get saved in a user-specified location
- [x] make sure users have control over where output and artifact files end up
- [x] and that it's never under `src/tango/`.  Additionally, it should be possible
    for the user to not save any files at all.  This is important because full
    factorial HPC runs will generate a ton of files (storage usage!) if this is
    not fixed.

## Separation of Concerns
- [ ] eliminate dueling parameters, e.g. `specs`, `parameter_overrides`, and
    `params_json` in src/tango/utils.py.  It's really easy to accidentally and
    silently set conflicting parameters without any awareness.
    This is partially complete, but the following still needs attention:
    ```py
    if specs is None:
        self.specs = load_from_yaml_with_overrides(input_file, parameter_overrides)
    else:
        from tango.utils import apply_parameter_overrides

        self.specs = apply_parameter_overrides(specs, parameter_overrides)
    ```
- [ ] `specs` and `_specs` (inconsistent naming!) attributes should
    contain only specs for the containing object.  Currently, they carry
    around unrelated specs for some objects -- e.g. `production_well`
    and `production_well_pump` have different well lengths, as expected,
    but they both have things like `rock_density`, `thermal_gradient`,
    and other unrelated parameters. for example:   ``` type(v) <class
    'tango.units.native.well.injection_well.InjectionWellUnitNative'> [k
    for k in v.specs if "diameter" in k] ['pipe_diameter', 'diameter',
    'well_diameter_seq'] ``` has `pipe_diameter` for the surface `diameter` for
    the injection wellbore, and `well_diameter_seq` for the injection wellbore.
    `specs` nested in the injection well should not have surface properties.
    This could easily get misused.

## Environment
- [x] [setup pyproject.toml for venv, uv, or
    pixi](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/issues/37)
    to make TANGO work as a project or a package (needs to be both) to enable
    deterministic environment management
- [x] remove code that adds tango by putting it on the path -- this is very bad
    practice because it subverts any possibility of type and interface checking

## Linting and Type Checking
- [ ] setup `mypy`
- [x] remove `eval` functions because they are masking circular imports and
    generally make it more difficult to reason about what TANGO is doing. They
    also create security risks.
- [x] get rid of circular imports masked by `eval` functions by creating
    registry modules
- [ ] remove all star imports.  The [official style
    guide](https://peps.python.org/pep-0008/#imports) recommends against using them,
    and the do things like masking where objects actually come from. For example,
    `dataclass` in `flexible_pp.py` was coming from the `tango.dataclasses` module,
    but it actually originally came from python's `dataclasses` module, which was
    also imported it `flexible_pp.py`.  This lack of clarity causes obscures the
    dependency graph among modules and elevates the risk of accidental circular
    imports.

## State Management
- [ ] make state variables lockable so it's easier to trace where they get updated
- [ ] make atttributes/classes:
    - [ ] `state` to track all state variables
    - [ ] optionally store state variables in `history` attributes at
        user-specified interval of time steps
    - [ ] optionally store state variables in `iter_history` attributes, which
        represent history of solver iterations at user-specified interval of
        time steps
    - [ ] ensure that each variable is updated once and only once per time step,
        with optional (discouraged!) override

## Error handling and solver robustness
- [ ] Run massive Latin Hypercube Sampling (LHS) paramater sweeps on Euler for
    various tango simulations to better understand:
    - [ ] parameter sets that cause expected errors and implement more robust
        error handling
    - [ ] parameter sets that cause errors related to problems with solvers that
        should be addressed
- [ ] use these sweeps to enhance error handling and/or fix simulations that the
    solver should actually be able to handle

## Agentic TANGO
- [ ] Run massive Latin Hypercube Sampling (LHS) paramater sweeps on Euler for
    various tango simulations to train AI LLM agent to:
    - [ ] set up TANGO runs based on user description
    - [ ] interpret results of successful TANGO runs
    - [ ] troubleshoot failed TANGO runs

## Readability/Maintainability/Usability Improvements
- [ ] lots of places where there are hardcoded values (e.g. `100_000` for the
    bar to Pa conversion, `1_000_000` for MPa to Pa conversion) without any
    local context explaining the value that could be using constants defined in
    the constants module (e.g. BAR_TO_PA), which would make their purpose clear
    to other devs/users.  Having unexplained float numbers for unit conversions
    in the code is exactly how NASA + ESA crashed a spacecraft into Mars at
    50,000 kph.  Any variables with non standard units should have units in the
    name, e.g. `P_outet_MPa`.
- [ ] append units of measure (e.g. `pressure_MPa`) to variable names for
    variables with non-MKS SI units
- [ ] change all the `_private_vars` to `public_vars` or `__private_vars`,
    depending on rationale.  In python, preceding `_` has no real effect and should
    not be used without an explanation (which is not provided anywhere in TANGO)
- [ ] remove _**all**_ hardcoded absolute paths
- [x] make options to change verbosity: no prints, some prints, extensive prints, ... —
    [implementation (`set_logger` / `--log-level`)](src/tango/utils.py),
    [example script usage (`log_level="NONE"`)](examples/run_flexible_SF_manual.py)
- [x] make sure TANGO is runnable via script and interactively, not just via
    CLI app

## Physics
- [ ] wellbore flow and heat transfer calculations assume turbulent flow.  We
    should check `Re` and maybe adjust accordingly


## Foundational Improvements for TANGO Long Term Objectives
- [ ] ability to copy and run standalone any submodule within an existing tango
    simulation (would enable much richer error context and troubleshooting steps)
- [x] make it so that edits in live, interactive TANGO instance have effect on
    result (show demo of code where this does not happen as expected).  This
    would enable easier ad hoc parameter sweeps in python scripts. --
    See [example](./applications/run_flexible_DF_manual_sweep)
    - [ ] make this approach part of the pipeline for Morteza's sweeps that
        are defined in config files

## Graph Network Architecture
Graph network should define node connections _and_ contain node parameter data,
rather than having this information stored in completely separate locations.

### Compact Format

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

### Implementation

Add two static methods to `PowerPlant` or `SurfaceUnitFlexiblePP`:

1. **`from_compact_format(specs)`** - Transpose compact format → internal format
2. **`to_compact_format(specs)`** - Convert internal → compact (for export/debug)

This keeps existing parsing code unchanged while offering cleaner YAML.
