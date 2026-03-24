# Refactor TANGO to achieve congruency between input files, code ojects, package/module structure, and actual physical systems

## Steps
### Convert example input file to desired structure
- [ ] consolidate code object data and graph connection so that, e.g. injection_wellbore stores all of it's attributes, a link idx, and previous and next link id for graph network
- [ ] ensure that no data is stored at root level
- [ ] make hierarchy of data approximately match hierarchy of physical systems
- [ ] make a conversion tool for going back and forth between old and new format

### Establish baseline before refractoring
- [ ] write characterization tests that run current TANGO on representative input files and capture reference outputs as reference for refractored code
- [ ] capture performance baselines on representative inputs using the existing codes so that improvements or regressions from the refractored code can be qualified

### Build out parallel code module structure
#### Rules
- in new code structure, `mypy --strict` and `ruff` must pass
- all classes must be `dataclass` or preferably `pydantic` `BaseModel` so that structure can be directly shown from code without additional structure imposed or modified during runtime
- evaluate `pydantic` as the input validation framework 

#### Congruency Steps
- [ ] make new parallel module structure that caputures approximate model structure
- [ ] bring in classes, methods, and functions to make it functional
- [ ] formalize state structure and methods
    - [ ] make sure that transient state variables are stored in a class-specific `state` object instance
    - [ ] make a corresponding `history` object that saves state at some user-specified interval that includes the possibility of `None` (i.e. no saving temporal results at all!)
    - [ ] make a class called `LockedState` that ensures that each state value can be updated once and only once per time step
- [ ] (de)serialization
    - [ ] build out generic (i.e. compatible with e.g. json, yaml, pickle, messagepack) approach for serializing and deserializing data such that any tango-specific code object has (de)serialization methods, e.g.
        - `to_file`
        - `from_file`
        - `to_str`
        - `from_str`
- [ ] implement modularity improvements
    - [ ] `solve` methods such that any tango-specific code object representing a physical component can be triggered by a test harness and run independently of the whole system
- [ ] run it
- [ ] verify that results match original configuration
- [ ] compare performance against baselines captured before refactoring
  - [ ] if results diverge, check for bugs in both the original and new code

### Scale out to all other TANGO input files
- [ ] on-board Janna or other employee who can help
- [ ] work through [Congruency Steps](#congruency-steps) one input file at a time until it's all converted
