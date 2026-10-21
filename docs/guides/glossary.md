# Glossary

Terms used across the TANGO documentation and code. Code names are given where a term maps to one.

## System types

| Term | Meaning | Example config |
|---|---|---|
| Hydrothermal | A natural aquifer is produced through wells and reinjected | `hydro_sf_electric.yml` |
| EGS | Enhanced geothermal system: a stimulated, low-permeability reservoir | `EGS_electric.yml`, `EGS_direct_heat.yml` |
| CPG | CO₂ plume geothermal: CO₂ instead of water as the working fluid | `CPG_electric.yml` |
| AGS | Advanced (closed-loop) geothermal system: fluid circulates in a sealed well loop with no reservoir flow | `AGS_direct_heat.yml` |
| Doublet | One injection and one production well (`layout.well_pattern: DOUBLET`) | most configs |
| Five-spot | Four injection wells around one production well, or the inverse | `hydro_sf_electric_5spot.yml` |

## Surface plant

| Term | Meaning |
|---|---|
| SF | Single-flash power plant: produced brine is flashed once to steam that drives a turbine |
| DF | Double-flash power plant: a second, lower-pressure flash adds a second steam stage |
| ORC | Organic Rankine cycle: a secondary working fluid, heated by the brine, drives the turbine |
| Direct heat | The heat is delivered through a heat exchanger, without power generation |
| TESPy | The open-source thermal-engineering library that solves the surface plant (`components/surface`) |
| CoolProp | The open-source fluid-property library used for every thermodynamic state (`core/fluid_state.py`) |

## Simulation

| Term | Meaning | Code |
|---|---|---|
| Component | One part of the system (a well, the reservoir, the surface plant, the economics) that turns an inlet into an outlet | `core/component.py` · `Component` |
| Type, variant | The config key pair that selects a component class, for example `reservoir` / `lumped` | `components/registry.py` |
| Lumped, numerical | Variants of a well: one closed-form calculation, or a march over many cells | `components/well/` |
| Connector | TANGO's adapter class through which an external simulator ([RAFT](https://github.com/GEG-ETHZ/RAFT), CMG, MOOSE, Aspen, …) would stand in for a component; the base classes define the interface, no simulator connector ships today | `components/*/base.py` |
| Stream | The temperature, pressure and mass flow rate passed between components | `core/stream.py` |
| Circuit | The components wired as a loop by `component_idx`, `prev` and `next` | config `components:` |
| Timestep | One step of the project's life, `sim_config.dt_years` long | `SystemDirect.run` |
| Orchestrator | The object that runs the circuit through time | `orchestrators/` |
| BC iteration | Boundary-condition iteration: repeating a timestep until the circuit closes | `SystemBCIteration` |
| `injection_mode` | How a timestep is converged: `manual`, `manual-fracking-check`, `auto-pressure`, `auto-flow` (`auto-both` raises `NotImplementedError`) | `core/policies.py` · `InjectionPolicy` |
| Fracking limit | The highest allowed injection pressure: hydrostatic pressure plus the configured overpressure percentage | `SystemBCIteration._check_fracking` |
| Aitken relaxation | A correction that speeds up the injection-temperature iteration | `core/accelerators.py` · `aitken_relax` |
| `LockedState` | A value that may be written once per solve; reading it stale raises an error | `core/locked_state.py` |
| History | The per-timestep record of a component's state | `*History` classes |

## Economics

| Term | Meaning |
|---|---|
| CAPEX | Capital expenditure: wells, surface plant, surface pipes, permitting, exploration |
| OPEX | Operating expenditure per year |
| LCOE | Levelized cost of electricity: lifetime cost divided by lifetime electricity, per MWh |
| LCOH | Levelized cost of heat, the same for heat |
| Specific investment cost | CAPEX per kW of the main product |
| Main product | Electricity or heat; the other output counts as a by-product (`economic.main_product`) |

## Running many simulations

| Term | Meaning | Code |
|---|---|---|
| Sweep | Many runs over a grid or sample of parameters | `applications/run_*` |
| NSGA-II | The multi-objective genetic algorithm used for optimization | `pymoo_api.py` · `Minimization` |
| Surrogate | A machine-learning model trained on runs, used to optimize faster | `surrogate_api.py` |
| DVC | Data Version Control: caches each pipeline stage and reruns only stale ones | `applications/*/dvc.yaml` |
| SLURM | The job scheduler on HPC clusters such as ETH Euler | `applications/*/*_job.sh` |
