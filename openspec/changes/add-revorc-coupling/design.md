# Design

## Context

See `proposal.md` for the motivation. The current state that shapes the approach:

- The only concrete surface component is `GraphSurface` (`components/surface/graph.py`), a TESPy network built from the config's `power_plant` nodes and edges and solved in `"design"` mode on every call. The abstract `SurfaceComponent` (`components/surface/base.py`) requires one method, `solve(inlet: Stream) -> Stream`. `Stream` carries `mass_rate`, `P` and `h` only; temperature is derived with `FluidState.with_HP`.
- The surface returns the same mass rate it receives: `SystemBCIteration._check_mass_rate_conserved` raises a `ConfigError` otherwise. `GraphSurface` sets its outlet pressure to `injection_pressure`.
- With `sim_config.injection_mode` set (every shipped example), `SystemBCIteration` re-solves the whole circuit, surface included, several times per step until the injection enthalpy converges. The surface model is therefore called several times per step, not once.
- Time steps are uniform and annual today (`num_tsteps`, `dt_years`); the surface does not use the step length. Ambient temperature is one constant, `common.surface_temperature`. There is no sub-annual profile of any kind.
- #150 (`feat/configurable-time-stepping`) changes `solve(inlet)` to `solve(inlet, step)`, lets subsystems run on their own grids, and makes every run average time-weighted.
- `DoubletEconomicComponent` reads `surface.history.net_power_W` and `net_thermal_W`, and costs the plant from `surface.power_plant["nodes"]` and `history.node_history`. A surface without TESPy nodes gets a plant CAPEX of 0.
- RAFT is the precedent for an external simulator: wrapper in `src/tango_core/external/raft_wrapper.py`, lazy import that turns `ImportError` into a `ConfigError` with install hints, uv dependency group pinned to an upstream git source, mypy override.
- TANGO already depends on `scikit-learn>=1.6,<2.0`, `pandas>=2.1,<3.0`, `numpy<2.5` and `joblib`.

The surrogate package, RevORCHP-SM 1.0.2, as published:

- Four scikit-learn models in `.joblib` files: a design model, a heat-pump off-design model, and one-stage and two-stage ORC off-design models. Three are small `MLPRegressor` networks; the one-stage ORC model is a `HistGradientBoostingRegressor` in a `MultiOutputRegressor`. The files record the scikit-learn version that wrote them (1.8.0) and refer to `numpy._core`, so they need numpy 2.
- Scripts at the repository root, not an installable package; sibling imports by bare module name; exact pins on every dependency.
- Python functions take one operating point as scalar keyword arguments and a required `model_path`, and return nested dicts with warnings as English sentences. The heat-pump model returns zero heat and power outside its supported regime and says so only in a warning sentence.
- Validity bounds (from its README): ORC brine inlet 95 to 115 °C, one-stage flow 3 to 8 kg/s and two-stage 3 to 10 kg/s per module; heat-pump brine inlet 55 to 75 °C, flow 5 to 12 kg/s, heating load 0.05 to 1 MW, sink supply 75 to 100 °C. Each module is nominally 10 kg/s and 1 MW of heat.

What the package should provide (regression tests and CI, packaging with loosened pins, docstrings, a batch interface with status values and bounds, version-free model files) is proposed to its authors in `prepare-for-tango-coupling`, an OpenSpec change in their repository, following `add-external-model-integration`. This design covers only the TANGO side.

## Goals / Non-Goals

**Goals:**

- A config can select a reversible ORC / heat-pump plant as the surface, and a run produces net electric power and delivered heat over the project lifetime that the economics read.
- TANGO owns the interface: what it sends, what it reads back, and the checks on both. Nothing inside the external model is checked or changed.
- The external model can be replaced (surrogate now, detailed model later) without changing the surface component or configs beyond a backend setting.
- The intra-annual resolution is a setting, not a fixed scheme.

**Non-Goals:**

- See `proposal.md`: no detailed-model coupling, no demand-driven dispatch, no geometry sizing, no CO2.

## Decisions

### D1: A new surface variant, with all external calls in one wrapper

`RevOrcSurface(SurfaceComponent)` in `components/surface/revorc.py`, registered as `("surface", "revorc")`. It converts the inlet stream to the model's inputs, asks a backend for results, records them, and returns the outlet stream. All imports of the external package live in `external/revorc_wrapper.py`, which defines:

- `RevOrcBackend`, a protocol: `evaluate(points: OperatingPoints) -> Results`, where both are arrays over operating points (one row per representative hour), and `bounds() -> dict` with the validity bounds per input.
- `SurrogateBackend`, the RevORCHP-SM implementation.

Alternative considered: extending `GraphSurface` with a "surrogate node". Rejected: `GraphSurface` is a TESPy network solver, and a plant whose whole performance comes from an external model shares none of that machinery.

### D2: Depend only on releases the authors publish

The package goes in a uv dependency group, `revorc`, pinned to a tag or commit of the authors' repository, never to a fork branch. The import is lazy; a missing package raises a `ConfigError` naming `uv sync --group revorc`.

This needs the package to be installable and its pins compatible with TANGO, which it is not today (see `proposal.md`). For pandas there are two ways to meet: raise TANGO's own range to allow pandas 3, or loosen the package's pin to allow pandas 2 (if its models run on it). Raising TANGO's range is the first choice: on 2026-11-17, TANGO's fast unit tests (`tests/unit`, not slow or perf) passed with pandas 3.0.2, numpy 2.4.6 and scikit-learn 1.8.0, the versions the models need, and the resolver accepts numpy 2 and scikit-learn 1.8.0 within TANGO's current ranges. TANGO's lock file still resolves numpy 1.26.4, which the models cannot load, so the lock moves to numpy 2. The regression tests have not been run on these versions yet. That work goes upstream as pull requests. Until it is merged, the coupling is developed against a stub backend in tests, and a local spike may install a fork branch in a throwaway environment, which is never committed as a dependency.

The `scikit-learn==1.8.0` requirement of the pickled models would pin TANGO's own scikit-learn. Version-free model files (network weights as `.npz`, the boosted model as ONNX) remove it; that is one of the later upstream proposals. Until then, the `revorc` group pins `scikit-learn==1.8.0`. A plain group pin would pin every TANGO user, because uv resolves all dependency groups into one lock file (checked 2026-11-18: adding the group moved the whole lock to 1.8.0). To keep the pin to RevORC users, scikit-learn moves from TANGO's core dependencies into its own group (`surrogate`, for `surrogate_api.py`, which then imports it lazily), declared as conflicting with `revorc` under `[tool.uv] conflicts`; uv then resolves the two separately (checked: 1.9.1 for `surrogate`, 1.8.0 for `revorc`). The cost is that the random-forest surrogate apps and RevORC cannot share one environment until the portable model files exist.

Alternative considered: running the package in a separate environment through a subprocess. Kept as the fallback if the version conflict cannot be resolved upstream; rejected as the default because every BC iteration would pay the process round trip.

### D3: The interface

Per operating point, TANGO sends:

| Input | Source in TANGO |
|---|---|
| Brine inlet temperature | `FluidState.with_HP(inlet.h, inlet.P)`, after the surface-pipe friction drop as in `GraphSurface` |
| Brine pressure | inlet `P` after that drop |
| Brine mass rate per module | inlet `mass_rate / n_modules` |
| Ambient temperature | representative-day profile (D6) |
| Minimum brine outlet temperature | config |
| Mode | schedule (D5) |
| Heating load, temperature lift, sink ΔT (heat-pump mode) | config schedule (D5) |

TANGO reads back, per module: net electric power (signed, including the model's own auxiliaries), delivered heat, and brine outlet temperature, plus the model's warnings and status flags.

The outlet stream keeps the inlet mass rate, sets `P = injection_pressure` as `GraphSurface` does, and sets `h` from the flow-weighted mean brine outlet temperature over the step at that pressure. The model's brine property approximations and TANGO's fluid model may differ slightly; that difference is reported at the interface (D7), not corrected.

### D4: N identical modules

The plant is `n_modules` identical nominal modules, the flow split equally between them. Extensive results (heat, power) are summed; temperatures are the same for every module. `n_modules` is a config value, or derived as the smallest count that keeps the per-module flow within the model's flow bound. Plant sizing in an optimization is the choice of `n_modules`: the off-design models describe fixed nominal hardware, and a geometry from the design model cannot be passed to them.

### D5: Mode and heat-pump load come from a schedule in the config

Each representative hour has a mode (`orc`, `hp`, or `off`) and, for `hp`, a heating load and sink temperatures. The default schedule is ORC in every hour. Deciding the mode from district-heating demand and dispatch is the job of the DH Profile Modelling and dispatch models and comes with their coupling.

### D6: Representative days inside each step

For each step, the component evaluates the representative hours that fall in that step: by default 12 representative days (one per month) of 24 hours, about 288 operating points per simulated year, from a monthly-hourly ambient temperature profile in the config. Results are weighted by the time each representative hour stands for (days in its month). The inlet stream is held over the step, matching the `hold` sync rule of #150.

This is one way of resolving the year, local to the component, chosen because it works on today's annual steps and on #150's grids alike. With #150, the step's `TimeStep` tells the component which representative hours the step covers. Sub-annual time stepping is being built in #150. If #150 (or a follow-up) adds a grid scheme for representative periods that every component can use, the surface uses that scheme instead of resolving the year itself, and this decision is reduced to the ambient profile and the mode schedule.

All points of a step go to the backend in one `evaluate` call. Until the package has a batch API, `SurrogateBackend` loops over single-point calls. Each BC iteration re-evaluates the step, so run time is measured in the spike (task 1.2) before deciding on caching.

### D7: Checks at the interface only

Before calling the backend, the wrapper checks every input against the backend's bounds. `out_of_range: error` (the default) raises a `SurfaceModelDomainError` naming the input, its value and the bound; in an optimization that marks the candidate infeasible. `out_of_range: warn` records the point and calls the model anyway, for exploratory runs. `out_of_range: fallback` evaluates the point with the detailed model instead (D10), as the authors suggested on 2026-11-18; the point is recorded as evaluated by the fallback. Inputs are never clipped.

After the call, the wrapper checks only what TANGO relies on: finite numbers, a brine outlet temperature not below the minimum TANGO sent, and the heat-pump status flag. A heat-pump point that the model reports as outside its supported regime is an error under `error`, never a silent zero. The model's warning sentences are recorded in the history as they are.

### D8: The plant is costed per module, by the surface component itself

The surrogate gives no equipment breakdown, so the plant is costed from a per-module CAPEX and fixed O&M in the config, times `n_modules`.

Where that cost is computed depends on #17, which proposes that each component report its own costs (start-up capital, yearly cost, cost per period) instead of one economic component reading every other component's internals after the run. Today `DoubletEconomicComponent` reaches into `GraphSurface`'s TESPy nodes and node history, and gives any other surface a plant CAPEX of 0. Adding a `RevOrcSurface` branch to that reader would add a second surface type to the code #17 wants to remove.

So `RevOrcSurface` reports its own plant cost through the per-component cost interface that #17 defines (planned in the `add-component-costs` change: `cost_items(basis)` returning `CostItem`s), and `DoubletEconomicComponent` sums what components report. If #17 is not ready in time for MS4.2, the stopgap is a narrow hook: the economic component asks the surface for its plant CAPEX through one method that `GraphSurface` implements with today's node-based costing, so neither surface's internals leak into the economics. The related questions of sizing over time (#78, #55) and costing two products (#96) are owned by those issues; this change uses whatever they decide.

### D9: Water and brine only

The surrogate was trained on brine. A config whose geofluid is not water or brine raises a `ConfigError`.

### D10: The detailed model verifies; the surrogate iterates

The authors' answers of 2026-11-18: the detailed model is Python, uses CoolProp, accepts batches of hourly inputs, and can size the hardware for given conditions within the machine limits. Indicative timings on the author's PC: about 50 s for the design procedure, 0.04 to 0.6 s per hourly heat-pump point, 1.2 to 4.5 s per hourly ORC point. Linux compatibility is not yet verified.

At 288 representative hours per step, one ORC evaluation of a step takes 6 to 22 minutes. Inside the BC iteration (several evaluations per step) a 25-year run would take roughly 12 to 45 hours, too slow for an optimizer. Called once per step it takes 2.4 to 9 hours, or about 0.3 to 1.1 hours spread over 8 cores; with the surface on a 5-year grid (#150), 0.5 to 1.8 hours.

So both backends have a role: the surrogate converges the BC iteration and runs inside optimizations; the detailed model re-evaluates a converged run once per step (or per surface step on a coarser grid) to verify a chosen design, and evaluates points outside the surrogate's training domain (D7). Whether the detailed model's sizing replaces the identical-module assumption (D4) for final designs is decided with the authors.

TANGO pins `coolprop==6.8.0`; the detailed model's CoolProp version must be agreed with the authors along with its other pins.

## Risks / Trade-offs

- **Run time.** About 288 points per step, times the BC iterations per step, times 25 steps, times an optimizer's evaluations. Single-point calls build a pandas frame each time. Mitigation: measure in the spike; batch API upstream; cache on exact inputs if iterations repeat them.
- **Domain coverage.** TANGO's wells can deliver brine outside 95 to 115 °C (ORC) or 55 to 75 °C (heat pump), or more than 8 kg/s per one-stage module. Under the default policy those runs fail rather than extrapolate. That is intended; the open questions ask the authors whether the domain can be widened.
- **Dependency drift.** The models are tied to scikit-learn 1.8.0 until version-free files exist.
- **Upstream timing.** Installability depends on the authors merging pull requests. If they are not merged in time for MS4.2, the subprocess fallback (D2) is the plan.

## Open Questions

For the model's authors:

1. Partly answered 2026-11-18: Python with CoolProp, batch input, timings in D10, updated version to be shared by the meeting of 2026-11-20. Still open: licence, Linux support, pinned versions (CoolProp against TANGO's 6.8.0).
2. Do the models work with pandas 2.x and earlier numpy 2 releases, so the pins can be loosened?
3. Who decides between ORC and heat-pump operation at each hour: the plant model, TANGO, or a dispatch model?
4. Answered 2026-11-18: flag, do not clip; use the detailed model as fallback where possible (D7, D10). Still open: can the domain be widened (for example, lower brine temperatures)?
5. Is summing identical modules valid for plants of several MW?
6. Are there cost data per module (CAPEX, O&M) consistent with the model?
7. Which brine property basis do the models use, so the interface difference with TANGO's fluid model can be bounded?

For TANGO:

8. Land this before or after #150? The design follows #150's `solve(inlet, step)`; before it lands, the step is the annual step. Do representative periods belong in #150's grid schemes (D6)?
9. With both electricity and heat as products, which `MainProduct` applies, or does a reversible plant need a combined metric? Decided in #96.
10. Where does the monthly-hourly ambient profile come from for each FlexGEO site?
11. Does #17 (component-owned costs) land before this change, or does this change use the stopgap hook (D8)?
