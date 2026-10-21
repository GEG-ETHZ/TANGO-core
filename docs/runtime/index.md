# How a run iterates

One optimization nests six loops. This is the picture to have in mind when a run is slow or fails to converge: the innermost sweep runs once per temperature iteration, per boundary-condition iteration, per timestep, per candidate.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#FFFFFF","primaryTextColor":"#202124","primaryBorderColor":"#DADCE0","lineColor":"#5F6368","secondaryColor":"#F8F9FA","tertiaryColor":"#F8F9FA","clusterBkg":"#F8F9FA","clusterBorder":"#DADCE0","edgeLabelBackground":"#FFFFFF"},"flowchart":{"curve":"basis","nodeSpacing":40,"rankSpacing":64,"useMaxWidth":true}} }%%
flowchart TB
  L1("1 · Optimizer, sweep<br/>Minimization.run<br/>run_lhs_sweep")
  L2("2 · One run<br/>Workflow(cfg).run<br/>finalize → LCOE")
  L3("3 · One timestep<br/>run_timestep(t)<br/>record(t)")
  L4("4 · BC loop<br/>auto modes only<br/>≤ 200 iterations<br/>tol 1e-3")
  L5("5 · Injection-T loop<br/>≤ 20 iterations<br/>|ΔT| < 0.5 K<br/>Aitken")
  L6("6 · Component sweep<br/>idx 0 → N<br/>solve(inlet)")
  w1("NumericalWell<br/>one pass, cells")
  w2("Pump well<br/>secant ≤ 20")
  r1("LumpedReservoir<br/>closed form")
  s1("GraphSurface<br/>TESPy Newton")

  L1 -- "each candidate, in a pool" --> L2
  L2 -- "for each timestep" --> L3
  L3 -- "for each BC iteration" --> L4
  L4 -- "for each T iteration" --> L5
  L5 -- "every iteration" --> L6
  L6 --> w1 & w2 & r1 & s1

  class L1 code
  class L2,L3,L4,L5,L6 code
  class w1,w2 well
  class r1 res
  class s1 surf
  classDef well  fill:#F3EDF9,stroke:#7D4FB0,color:#7D4FB0,font-size:15px
  classDef res   fill:#FBEAE7,stroke:#D2402C,color:#D2402C,font-size:15px
  classDef surf  fill:#E8F0FA,stroke:#2F6FBF,color:#2F6FBF,font-size:15px
  classDef econ  fill:#E0F2F1,stroke:#007B83,color:#007B83,font-size:15px
  classDef code  fill:#FFFFFF,stroke:#DADCE0,color:#202124,font-size:15px
  classDef err   fill:#FCE8E6,stroke:#D93025,color:#D93025,font-size:15px
  classDef out   fill:#FFFFFF,stroke:#9AA0A6,color:#5F6368,stroke-dasharray:4 3,font-size:15px
  classDef human fill:#202124,stroke:#9AA0A6,color:#FFFFFF,font-size:15px
```

| Level | Loop | Code | Limit |
|---|---|---|---|
| 1 | Optimizer generations or sweep rows | `Minimization.run` (`pymoo_api.py`), `run_lhs_sweep` (`surrogate_api.py`), `applications/*/dvc.yaml` | Set by the app |
| 2 | One full run per candidate, in a process pool | `_Problem._evaluate` → `Workflow(cfg).run()` | — |
| 3 | Timesteps | `SystemDirect.run` | `sim_config.num_tsteps` |
| 4 | Boundary-condition loop, `auto-pressure` and `auto-flow` only | `_converge_injection_pressure`, `_converge_injection_flow` | 200 iterations, relative tolerance 1e-3 |
| 5 | Injection-temperature loop with Aitken relaxation | `_converge_injection_T` | 20 iterations, \|ΔT\| < 0.5 K |
| 6 | Component sweep in `component_idx` order | `component.solve(inlet)` | One pass |

Inside a component, only two solvers iterate: the pump well's secant search on discharge pressure (`secant_solve`, at most 20 steps, each re-marching the well) and TESPy's Newton solve in `GraphSurface`. The numerical well is a single explicit pass over its cells, and the lumped reservoir is closed form.

Details: [the boundary-condition iteration](bc-iteration.md) and [one run end to end](one-run.md).
