# Boundary-condition iteration

`SystemBCIteration.run_timestep` (`src/tango/orchestrators/system_bc_iteration.py`) decides how one timestep converges. The injection enthalpy is unknown until the surface plant has been solved, so both modes iterate it; `manual-fracking-check` then checks the converged timestep against the fracking limit.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#FFFFFF","primaryTextColor":"#202124","primaryBorderColor":"#DADCE0","lineColor":"#5F6368","secondaryColor":"#F8F9FA","tertiaryColor":"#F8F9FA","clusterBkg":"#F8F9FA","clusterBorder":"#DADCE0","edgeLabelBackground":"#FFFFFF"},"flowchart":{"curve":"basis","nodeSpacing":40,"rankSpacing":64,"useMaxWidth":true}} }%%
flowchart TB
  start(["run_timestep(t)"])
  tl("Injection-enthalpy loop<br/>restore snapshot, solve all")
  conv("|Δh| < 1 kJ/kg ?")
  ce("ConvergenceError")
  frk("Fracking check<br/>manual-fracking-check only")
  done(["record(t)"])
  fve("FrackingViolationError")

  start --> tl
  tl --> conv
  conv -- "no: Aitken guess" --> tl
  conv -- yes --> frk
  conv -. "after 20" .-> ce
  frk -- ok --> done
  frk -- exceeded --> fve

  class start,done code
  class tl,conv,frk code
  class fve,ce err
  classDef well  fill:#F3EDF9,stroke:#7D4FB0,color:#7D4FB0,font-size:15px
  classDef res   fill:#FBEAE7,stroke:#D2402C,color:#D2402C,font-size:15px
  classDef surf  fill:#E8F0FA,stroke:#2F6FBF,color:#2F6FBF,font-size:15px
  classDef econ  fill:#E0F2F1,stroke:#007B83,color:#007B83,font-size:15px
  classDef code  fill:#FFFFFF,stroke:#DADCE0,color:#202124,font-size:15px
  classDef err   fill:#FCE8E6,stroke:#D93025,color:#D93025,font-size:15px
  classDef out   fill:#FFFFFF,stroke:#9AA0A6,color:#5F6368,stroke-dasharray:4 3,font-size:15px
  classDef human fill:#202124,stroke:#9AA0A6,color:#FFFFFF,font-size:15px
```

| `injection_mode` | After the loop | Converged when |
|---|---|---|
| `manual` | nothing | \|Δh\| < 1 kJ/kg |
| `manual-fracking-check` | fracking check | \|Δh\| < 1 kJ/kg and no threshold exceeded |

The `auto-pressure`, `auto-flow`, and `auto-both` modes, which adjusted wellhead pressure or mass rate toward the fracking limit, were removed; the `applications/opt_*/` searches find such operating points instead.

Every iteration of the enthalpy loop first restores each component from a snapshot of its `state` (`Component.snapshot_convergence_state`), so each attempt starts from the end of the previous timestep. If a guess drives the fluid below its melting point, CoolProp raises a `Tmelt` error and the loop retries from 275 K.

| Exit | Raised by |
|---|---|
| `ConvergenceError` | 20 enthalpy iterations used up |
| `FrackingViolationError` | `_check_fracking`, in `manual-fracking-check` |
| `ConfigError` | no injection well |

Deep dive: [how injection-enthalpy convergence works](../tango_t_convergence.md).
