# Boundary-condition iteration

`SystemBCIteration.run_timestep` (`src/tango_core/orchestrators/system_bc_iteration.py`) decides how one timestep converges. The injection temperature is unknown until the surface plant has been solved, so every mode iterates it; the `auto-*` modes add an outer loop on wellhead pressure or mass rate, to stay at the fracking limit.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#FFFFFF","primaryTextColor":"#202124","primaryBorderColor":"#DADCE0","lineColor":"#5F6368","secondaryColor":"#F8F9FA","tertiaryColor":"#F8F9FA","clusterBkg":"#F8F9FA","clusterBorder":"#DADCE0","edgeLabelBackground":"#FFFFFF"},"flowchart":{"curve":"basis","nodeSpacing":40,"rankSpacing":64,"useMaxWidth":true}} }%%
flowchart TB
  start(["run_timestep(t)"])
  pol("Dispatch on injection_mode")
  nie("NotImplementedError")
  bc("BC update<br/>pressure or mass rate")
  tl("Injection-T loop<br/>restore snapshot, solve all")
  conv("|ΔT| < 0.5 K ?")
  bcok("BC converged ?<br/>always yes in manual modes")
  ce("ConvergenceError")
  frk("Fracking check<br/>skipped in manual")
  done(["record(t)"])
  fve("FrackingViolationError")

  start --> pol
  pol -- "auto-both" --> nie
  pol -- "auto-pressure, auto-flow" --> bc
  pol -- "manual modes" --> tl
  bc --> tl
  tl --> conv
  conv -- "no: Aitken guess" --> tl
  conv -- yes --> bcok
  conv -. "after 20" .-> ce
  bcok -- "no: next BC iteration" --> bc
  bcok -. "after 200" .-> ce
  bcok -- yes --> frk
  frk -- ok --> done
  frk -- exceeded --> fve

  class start,done,pol code
  class tl,bc,conv,bcok,frk code
  class nie,fve,ce err
  classDef well  fill:#F3EDF9,stroke:#7D4FB0,color:#7D4FB0,font-size:15px
  classDef res   fill:#FBEAE7,stroke:#D2402C,color:#D2402C,font-size:15px
  classDef surf  fill:#E8F0FA,stroke:#2F6FBF,color:#2F6FBF,font-size:15px
  classDef econ  fill:#E0F2F1,stroke:#007B83,color:#007B83,font-size:15px
  classDef code  fill:#FFFFFF,stroke:#DADCE0,color:#202124,font-size:15px
  classDef err   fill:#FCE8E6,stroke:#D93025,color:#D93025,font-size:15px
  classDef out   fill:#FFFFFF,stroke:#9AA0A6,color:#5F6368,stroke-dasharray:4 3,font-size:15px
  classDef human fill:#202124,stroke:#9AA0A6,color:#FFFFFF,font-size:15px
```

| `injection_mode` | Outer loop | Converged when |
|---|---|---|
| `manual` | none | \|ΔT\| < 0.5 K |
| `manual-fracking-check` | none, then fracking check | \|ΔT\| < 0.5 K and no threshold exceeded |
| `auto-pressure` | Newton step: `p += target_P − P_inj,out` | relative change < 1e-3 and `P_inj,out < target_P` |
| `auto-flow` | Picard step: `ṁ ← min(fracking_flow(μ, ρ), max_mass_rate)` | relative change < 1e-3 |
| `auto-both` | raises `NotImplementedError` | — |

Every iteration of the temperature loop first restores each component from a snapshot of its `state` (`Component.snapshot_convergence_state`), so each attempt starts from the end of the previous timestep. If a guess drives the fluid below its melting point, CoolProp raises a `Tmelt` error and the loop retries from 275 K.

| Exit | Raised by |
|---|---|
| `ConvergenceError` | 20 temperature or 200 boundary-condition iterations used up |
| `FrackingViolationError` | `_check_fracking`, in every mode except `manual` |
| `ConfigError` | no injection well, in every mode; an `auto-*` mode without a surface or reservoir |

Deep dive: [how injection-enthalpy convergence works](../tango_t_convergence.md).
