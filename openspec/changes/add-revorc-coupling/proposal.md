# Proposal

## Why

FlexGEO milestone MS4.2 (end of January 2027) needs a first coupled run in which the surface plant is the reversible ORC / heat pump developed in FlexGEO task T2.2, not TANGO's own TESPy ORC. TANGO's ORC is one fixed design point today (#123): only the working-fluid flow changes over the years, it has no off-design behaviour, and it cannot run as a heat pump.

The T2.2 authors at NTUA (Laboratory of Applied Thermodynamics) have published surrogate models of their system, [RevORCHP-SM](https://github.com/trx09009/RevORCHP-SM-1.0.2) 1.0.2: scikit-learn models of the design and off-design performance of a 0.5 to 1 MW reversible module, for both ORC and heat-pump operation. Their detailed thermodynamic model is slower and has not been shared yet.

The preferred long-term coupling is the detailed model, if it runs fast enough at hourly resolution. To meet MS4.2, this change couples the surrogate first, behind an interface that the detailed model can later implement.

The surrogate package cannot be used from TANGO as published: it is a set of scripts rather than an installable package, it pins exact versions that conflict with TANGO's (`pandas==3.0.2` against TANGO's `pandas<3.0`; `scikit-learn==1.8.0`, which the pickled models need), and it evaluates one operating point per call. Following the external-coupling rules (`.agent/rules/external-coupling.md`), TANGO does not patch or vendor it: those problems are proposed to the authors as pull requests to their repository, and TANGO depends only on releases they publish.

## What Changes

- Add a surface variant, `type: surface` / `variant: revorc`, whose plant performance comes from an external reversible ORC / heat-pump model instead of a TESPy network.
- Add `src/tango_core/external/revorc_wrapper.py`, the only module that imports the external package. It maps TANGO's stream and settings to the model's inputs, calls it, and maps the results back. A small backend protocol lets the detailed model replace the surrogate later without changing the surface component.
- Model the plant as N identical nominal modules sharing the flow equally, the scaling the surrogate's authors document.
- Evaluate the plant on representative days inside each TANGO step (one day per month at hourly resolution by default, about 288 evaluations per simulated year), using a monthly-hourly ambient temperature profile and an ORC/heat-pump mode schedule from the config, and return time-weighted results.
- Check every value that crosses the interface against the model's validity bounds, with a configurable policy (`error` by default, or `warn`), and record the model's own warnings without judging them.
- Record net electric power and delivered heat in the surface history so the economics read them, and have the surface report its own plant cost per module from config (the surrogate gives no equipment detail), in line with component-owned costs (#17).
- Add the external package as an optional uv dependency group, `revorc`, imported lazily, with a `ConfigError` naming the install command when it is missing.

### Non-goals

- Coupling the detailed model. Its availability, language and run time are open (see `design.md`); the backend protocol leaves room for it.
- Deciding the ORC/heat-pump mode from district-heating demand or dispatch (DH Profile Modelling, Hotmaps, METRO). This change takes the schedule as an input.
- Sizing the plant geometry. The off-design surrogates describe fixed nominal hardware; sizing here is the number of modules.
- Changing the published surrogate package. Every change to it goes to its authors as a pull request.
- Geofluids other than water/brine. CO2 configs are rejected.

## Capabilities

### New Capabilities

- `revorc-surface`: running a reversible ORC / heat-pump plant, given by an external model, as TANGO's surface component, at representative-day resolution, with checked inputs and results that the economics can read.

### Modified Capabilities

None. No specs exist yet in `openspec/specs/`.

## Impact

- New `src/tango_core/components/surface/revorc.py` (`RevOrcSurface`, its `State`/`History`) and registry entry `("surface", "revorc")`.
- New `src/tango_core/external/revorc_wrapper.py` (backend protocol, surrogate backend, lazy import).
- Plant costing: the surface reports its own plant cost, through the per-component cost interface of #17 or, if that is not ready, a one-method stopgap in `components/economic/doublet.py` that `GraphSurface` also implements (today any surface without TESPy nodes gets a plant CAPEX of 0).
- `pyproject.toml`: `revorc` dependency group, pinned to an upstream release; mypy override for the package.
- New template `templates/hydro_RevORC.yml`; unit tests with a stub backend in `tests/unit/`, and one test against the real package that is skipped when the group is not installed.
- `src/tango_core/components/README.md`, `docs/architecture/`, generated config reference, `CHANGELOG.md`.
- Builds on #149 (circuit API, port kinds on the surface base class) and #150 (`solve(inlet, step)` and per-subsystem time grids). Whichever lands first, this change follows its interface.
