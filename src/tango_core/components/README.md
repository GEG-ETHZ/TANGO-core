# `tango_core.components`

`components` is where the physics and the money live. Each physical part of a geothermal system (an injection well, the reservoir, a production well, the surface plant) is one class here. So is the economics that prices them. The config picks the parts. This package makes them interchangeable: any well can sit in any circuit, as long as it speaks the same interface.

## The ideas you need

**What a component must do.** Subclass the base for its kind (`WellComponent`, `ReservoirComponent`, `SurfaceComponent` or `EconomicComponent`). Then implement `solve(inlet)`: read the inlet `Stream` and write `self.outlet` and `self.state`. The base classes hold the fields every component of that kind shares. One example is `injection_pressure` on the surface plant, which the `auto-pressure` loop adjusts.

**Inlet and outlet are `Stream`s.** A component never calls its neighbor. It sees one inlet `Stream` (T, P, ṁ) and produces one outlet `Stream`. The orchestrator wires each outlet to the component named by `next`.

**State and history.** Values that change during a run live in a `*State` dataclass, each one a `LockedState`. Every `*State` field has a `list` twin in a `*History` class that is appended after each timestep. `LumpedReservoirState` and `LumpedReservoirHistory` in `reservoir/lumped.py` are the simplest pair to read.

**The registry.** `registry.py` maps each YAML `(type, variant)` pair to a class. One example is `("production_well_with_pump", "numerical")` → `NumericalProductionWellWithPump`. A new class appears in configs only after it gets an entry here.

**Economics is one central component.** The wells, reservoir and plant hold no cost logic. `DoubletEconomicComponent` runs once, after the last timestep. It reads the solved components and their histories and prices them by category:

- wells: one drilling-cost formula per well section;
- surface plant nodes: turbine and generator, injection pump, cooler/condenser;
- surface pipes;
- fixed permitting and exploration costs.

It then computes OPEX and LCOE from the run-averaged net power. The reservoir is not costed. A direct-heat exchanger is not costed either, so a pure direct-heat plant reports a surface-plant CAPEX of 0.

External simulators (CMG, MOOSE and others) would enter as new `ReservoirComponent` or `WellComponent` implementations. None exists yet.

## Read these first

1. `reservoir/lumped.py`, `LumpedReservoir`: a complete component in one file; start with its `solve`.
2. `well/numerical.py`, `NumericalWell`: a marched well. `_march` is one explicit pass over the cells.
3. `surface/graph.py`, `GraphSurface`: the plant as a TESPy network built from the config's `power_plant` nodes and edges.
4. `economic/doublet.py`, `DoubletEconomicComponent.solve`: the cost categories, in order.

## Reference

| Subpackage | Base class | Implementations |
|---|---|---|
| `well/` | `WellComponent` (`base.py`) | `lumped.py`: `LumpedInjectionWell`, `LumpedProductionWell`, `LumpedProductionWellWithPump`. `numerical.py`: `NumericalWell`, `NumericalInjectionWell`, `NumericalProductionWell`, `NumericalProductionWellWithPump` |
| `reservoir/` | `ReservoirComponent` (`base.py`) | `lumped.py`: `LumpedReservoir`. `wellpattern_impedance.py`: `WellPattern` |
| `surface/` | `SurfaceComponent` (`base.py`) | `graph.py`: `GraphSurface` |
| `economic/` | `EconomicComponent` (`base.py`) | `doublet.py`: `DoubletEconomicComponent` |
| `registry.py` | — | `COMPONENT_REGISTRY` |

To add a component, follow [`components/AGENTS.md`](https://github.com/GEG-ETHZ/TANGO-core/blob/main/src/tango_core/components/AGENTS.md).
