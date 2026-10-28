# `tango_core.workflows`

`Workflow` is the one object a caller needs. It takes a YAML config, turns it into validated components and the right orchestrator, and runs them. It can also write the config back out with every solved value. The command-line tool, the optimizers and every script in `applications/` go through it. Nothing outside it builds components or orchestrators by hand.

## The ideas you need

**All validation happens before anything runs.** `Workflow.__init__` validates `common`, `layout`, `sim_config` and `description` against the pydantic schemas in `core/specs.py`. It builds the `economic` block, then every entry under `components:` through `COMPONENT_REGISTRY`. Any failure is raised as a `ConfigError` before the first timestep. For a closed loop, it also requires at least one pressure source (a pumped well or a pump node in the plant), because a pump-less loop has nothing to drive circulation.

**Shared values have one source.** `common` is built once and handed to every component by reference. A final identity check (`is`, not `==`) proves they all hold the same object. `well_spacing`, `well_pattern`, `dt_years` and `target_extraction_pressure` are copied from their single source into each component that declares them. A component's own YAML block may not set any of these.

**One key chooses the orchestrator.** If `sim_config.injection_mode` is set, the workflow uses `SystemBCIteration`, which iterates each timestep until the circuit closes. If it is absent, it uses `SystemDirect`, which makes one pass.

**The config goes both ways.** `to_dict`, `to_str` and `to_file` rebuild the config from the live objects, including solved state. The output can be loaded again. This is how `results_export.write_results` saves a run.

## Read these first

1. `workflow.py`, `Workflow.__init__`: load, validate, build, choose.
2. `workflow.py`, `_build_components`: the registry lookup and the shared-value threading.
3. `workflow.py`, `_check_loop_has_pressure_source`: the closed-loop check.

## Reference

| Name | Does |
|---|---|
| `Workflow` | The class. Its docstring has a usage example |
| `from_file`, `from_str` | Parse YAML (`yaml.safe_load`), then construct |
| `to_dict`, `to_str`, `to_file` | Write the live config back out |
| `run` | Delegate to the orchestrator |
| `_check_common_identity` | Every component shares the one `Common` |
| `_build_economic_component` | The `economic:` block |
| `_build_components` | The `components:` block |

How the config maps to objects, as a diagram: [config to objects](https://github.com/GEG-ETHZ/TANGO-core/blob/main/docs/architecture/config.md).
