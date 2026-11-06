# Where the TANGO Commandments Come From

Each [TANGO Commandment](https://github.com/GEG-ETHZ/TANGO-core/blob/docs/commandments-provenance/CONTRIBUTING.md#tango-commandments) was written in response to a real problem in the code before the 2026 refactor. This page links each commandment to one place in that older code where you can see the problem.

All links point to [`629eb6b8`](https://github.com/GEG-ETHZ/TANGO-core/tree/629eb6b8d87df0f183c1fa30690e32c9f4066be3), the last `main` commit before the refactor. The refactor itself landed as [`d1dea393`](https://github.com/GEG-ETHZ/TANGO-core/commit/d1dea3938ca6fbbade1c733ac695898d0f12094a) ("refactor to make tango robust"). The package was called `tango` then and lived in `src/tango/`. Longer write-ups of several of these bugs are in [`docs/archive/bugs-fixed-in-tango.md`](archive/bugs-fixed-in-tango.md).

These are examples, not a full audit. Most of the problems showed up in more places than the one linked here.

## 1. object == config

[`parameter_mappings.py#L28-L57`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/parameter_mappings.py#L28-L57): the config, the results, and the code used different names for the same quantities, so the optimizer needed a hand-maintained translation table (`"Net_Electricity_Generated_kWe": "ELECTRIC_POWER_AVE"`, `"CAPEX_total": "TOTAL_CAPEX"`, and so on) to find anything. Every rename had to be repeated in this table, and nothing checked that it was.

## 2. Mutation is guarded

[`reservoir.py#L180-L221`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/units/native/reservoir.py#L180-L221): the reservoir's cumulative `_energy_extracted` is rewritten on every pass of the boundary-condition loop, from an injection temperature that the surface solve left behind on the *previous* pass. The loop's convergence check doesn't look at this value, so a "converged" timestep can commit energy computed from a mix of fresh and stale state. Nothing marked which values were current and which were left over. See [the write-up](archive/bugs-fixed-in-tango.md#convergence-loop-can-commit-a-result-computed-from-mixed-freshstale-state).

## 3. History is recordable

[`utils.py#L969-L1029`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/utils.py#L969-L1029): results were collected by scanning `dir(state)` on each node and keeping whatever happened to be a `float` that wasn't on a skip list. An `int` or NumPy value was dropped without a word, and so was anything whose `getattr` raised (bare `except: continue`). What ended up in the output was a side effect of attribute types, not a decision.

## 4. Single source of truth

[`surface/CPG.py#L268-L278`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/units/native/surface/CPG.py#L268-L278): each unit merged the shared `common` block into its own specs dict (`specs["common"] | specs["surface"]`), giving each one a private copy. The same pattern sits in [`ORC.py#L277`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/units/native/surface/ORC.py#L277). Shared values could then be read from more than one owner: `target_extraction_pressure` is read from the surface in [`BC_calculator.py#L474`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/orchestrators/BC_calculator.py#L474) and from the production well pump in [`native_workflow_utils.py#L260`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/workflows/native_workflow_utils.py#L260).

As far as we know, two copies never actually disagreed, but nothing would have stopped them from doing so. When the refactor added a check that rejects a shared value set in a component's own block ([`workflow.py#L554-L564`](https://github.com/GEG-ETHZ/TANGO-core/blob/d1dea3938ca6fbbade1c733ac695898d0f12094a/src/tango/workflows/workflow.py#L554-L564) in the refactor commit), it immediately found three of the new example files setting `well_spacing` a second time, matching the shared value only because someone had kept them in sync by hand.

## 5. Deterministic quality checks

[`.gitlab-ci.yml#L19-L27`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/.gitlab-ci.yml#L19-L27): CI ran `pytest` and nothing else: no type checker, no linter. A type checker would have caught [`reservoir.py#L51`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/units/native/reservoir.py#L51), where `self.specs.thicness` (sic) raises `AttributeError` the first time the thickness warning fires, so the warning itself crashes the run.

## 6. Docstrings

[`reservoir.py#L34-L39`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/units/native/reservoir.py#L34-L39): the docstring documents an argument `id` that doesn't exist; the parameter is `unit_id`. With no style check on docstrings, they drifted from the signatures they describe, and nothing generated from them could be trusted.

## 7. Schemas defined in code

[`reservoir.py#L34-L47`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/units/native/reservoir.py#L34-L47): a unit took its config as a bare `dict`, and its valid ranges lived in a separate YAML file ([`reservoir_validation.yaml`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/units/native/reservoir_validation.yaml)) read at runtime. The schema was split across two files in two languages, so a field could be added to one and forgotten in the other. Worse, the specs dataclasses' `from_dict` ([`dataclasses.py#L120-L121`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/units/dataclasses.py#L120-L121)) dropped every key it didn't recognize, so a misspelled key in a config was ignored and the default used instead.

## 8. No `eval`

[`optimizerr.py#L133-L134`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/optimizerr.py#L133-L134): optimization targets were evaluated with `eval(target)`, where `target` is a string of Python built from the templates in [`parameter_mappings.py#L6-L11`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/parameter_mappings.py#L6-L11) (`"self.tango_instance.workflow.orchestrator.unit.surface."`). Any rename broke these strings at runtime, invisibly to type checkers and IDEs, and the whole thing executed text derived from user input.

## 9. Unit conversions

[`utils.py#L1072-L1073`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/utils.py#L1072-L1073) and [`economic/surface.py#L1150-L1153`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/units/native/economic/surface.py#L1150-L1153): bare `* 1e5` and `+ 273.15` scattered through the code, even though [`core/constants.py#L18-L19`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/core/constants.py#L18-L19) already defined `C_TO_K`. A literal can't be searched for reliably, and getting the direction of a conversion wrong is one character.

## 10. Enums for finite variants

[`orchestrators/native.py#L127`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/orchestrators/native.py#L127): behavior branched on raw strings such as `self.specs["schedule"]["bc_iteration_checkpoint"] == "production_well_bottom"`. A typo in the config just takes the other branch. A related case: the `check_fracking` flag only controlled one of the two fracking mechanisms its name suggests ([write-up](archive/bugs-fixed-in-tango.md#check_fracking-doesnt-gate-what-its-name-implies)); it was replaced by the `InjectionPolicy` enum.

## 11. No silent base-class methods

[`orchestrators/native.py#L56-L77`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/orchestrators/native.py#L56-L77): the base orchestrator's `balanced()` always returned `True`, and `update_time_dependent_vars()` and `update()` were `pass`. AGS configs were routed to this base class by mistake, so every AGS run repeated the first timestep's solution for every later year, with no error. See [the write-up](archive/bugs-fixed-in-tango.md#ags-configs-never-advance-simulated-time). A `raise NotImplementedError` would have failed on the first run.

## 12. Unit suffixes

[`surface/flexible_pp.py#L602`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/units/native/surface/flexible_pp.py#L602): the TESPy network was built with `p_unit="bar", T_unit="C"`, so every pressure and temperature read from it was in bar and °C, while the rest of the code used Pa and K. Nothing at the read site said so, which is why code like [`economic/surface.py#L1150-L1153`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/units/native/economic/surface.py#L1150-L1153) has to remember to add 273.15 by hand.

## 13. No opaque short names

[`BC_calculator.py#L116-L124`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/orchestrators/BC_calculator.py#L116-L124): `fracking_flow()` sets `re = well_spacing / 2.0` (a radius) and `rw = self.inj_well._specs.diameter` (a diameter), then takes `log(re / rw)`. The docstring a few lines up calls `rw` the "wellbore radius". With names like `wellbore_diameter_m` the mismatch would have been visible on the line itself. See [the write-up](archive/bugs-fixed-in-tango.md#fracking_flow-mixes-a-wellbore-diameter-into-a-term-that-should-be-a-radius).

## 14. Document private attributes

[`economic/exploration.py#L24-L27`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/units/native/economic/exploration.py#L24-L27): `_PPI`, `_X_IC`, and `_X_PC` are set with no comment and then multiplied into every exploration cost (e.g. [L53](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/units/native/economic/exploration.py#L53)). What they stand for (producer price index, and two cost multipliers) has to be reconstructed from the source paper.

## 15. Encapsulated mutation

[`BC_calculator.py#L515-L519`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/orchestrators/BC_calculator.py#L515-L519): the boundary-condition loop assigned the surface's fields directly (`self.surface.mass_rate = ...`, `self.surface.power_plant.iterative_inj_pressure = ...`), branching on the class name to know which nested object to poke. The surface couldn't enforce anything about its own state, and finding every writer of a field meant searching the whole package.

## 16. YAML booleans are `True`/`False`

[`examples/testcase41.yml#L84`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/examples/testcase41.yml#L84) sets `flow_rate_from_csv: 'yes'`, and [`reservoir.py#L58`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/units/native/reservoir.py#L58) checks `== "yes"`. The same goes for `controlled_power_generation` in [`BC_calculator.py#L87`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/src/tango/orchestrators/BC_calculator.py#L87). Writing the natural `True`, or an unquoted `yes` that YAML 1.1 parsers turn into a boolean, silently turns the feature off. See [the write-up](archive/bugs-fixed-in-tango.md#-yes-string-comparison-trap).

## 17. Every `templates/` YAML is regression-tested

The AGS bug under commandment 11 was in the regression test the whole time. [`tests/regtest/test_native.py#L39-L40`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/tests/regtest/test_native.py#L39-L40) ran two AGS configs, [`testcase6.yml`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/examples/testcase6.yml#L104) and `testcase7.yml`, five timesteps each, against golden LCOEs. Those golden values had been recorded from runs that repeated the first year's solution every year, so the test passed while locking in the wrong answer. A golden value only says "same as last time"; nothing had checked the run it came from.

Coverage was thin besides: of the 185 YAML files under `examples/`, 54 appear in the regression test, and a long run of further cases is commented out with no stated reason ([`test_native.py#L216-L225`](https://github.com/GEG-ETHZ/TANGO-core/blob/629eb6b8d87df0f183c1fa30690e32c9f4066be3/tests/regtest/test_native.py#L216-L225)).
