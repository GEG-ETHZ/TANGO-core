# The component circuit

![System key: surface plant blue, wells purple, reservoir red, economics teal](../diagrams/system-key.drawio.svg){ align=right width="260" }

A TANGO system is a closed loop of components. Each component's `solve(inlet)` turns an inlet `Stream` (temperature, pressure, mass rate, each held in a `LockedState`) into an outlet `Stream`, which the orchestrator passes to the component named by `next`. Components are solved in `component_idx` order; the loop is cut at the injection well, so the surface plant's outlet feeds the injection well on the next pass. Economics (`components/economic`) is not part of the loop: it runs once after the last timestep and prices the wells (geometry, pump power) and the surface plant (turbine, pump, condenser). It does not price the reservoir and never feeds back into the physics.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#FFFFFF","primaryTextColor":"#202124","primaryBorderColor":"#DADCE0","lineColor":"#5F6368","secondaryColor":"#F8F9FA","tertiaryColor":"#F8F9FA","clusterBkg":"#F8F9FA","clusterBorder":"#DADCE0","edgeLabelBackground":"#FFFFFF"},"flowchart":{"curve":"basis","nodeSpacing":40,"rankSpacing":64,"useMaxWidth":true}} }%%
flowchart TB
  surf("4 · Surface plant<br/>graph, TESPy")
  inj("0 · Injection well<br/>numerical | lumped")
  res("1 · Reservoir<br/>lumped")
  pl("2 · Production well<br/>numerical | lumped")
  pu("3 · Production well + pump<br/>numerical | lumped")
  eco("Economics · doublet<br/>after the last timestep")

  surf -- "Stream, next pass" --> inj
  inj -- "Stream: T · P · ṁ" --> res
  res -- Stream --> pl
  pl -- Stream --> pu
  pu -- Stream --> surf
  pu -. "geometry, pump power" .-> eco
  surf -. "turbine, pump, condenser" .-> eco

  class inj,pl,pu well
  class res res
  class surf surf
  class eco econ
  classDef well  fill:#F3EDF9,stroke:#7D4FB0,color:#7D4FB0,font-size:15px
  classDef res   fill:#FBEAE7,stroke:#D2402C,color:#D2402C,font-size:15px
  classDef surf  fill:#E8F0FA,stroke:#2F6FBF,color:#2F6FBF,font-size:15px
  classDef econ  fill:#E0F2F1,stroke:#007B83,color:#007B83,font-size:15px
  classDef code  fill:#FFFFFF,stroke:#DADCE0,color:#202124,font-size:15px
  classDef err   fill:#FCE8E6,stroke:#D93025,color:#D93025,font-size:15px
  classDef out   fill:#FFFFFF,stroke:#9AA0A6,color:#5F6368,stroke-dasharray:4 3,font-size:15px
  classDef human fill:#202124,stroke:#9AA0A6,color:#FFFFFF,font-size:15px
```

The circuit above is `templates/hydro_sf_electric.yml`. The four system types reuse the same building blocks:

| System | Example config | Fluid | What differs |
|---|---|---|---|
| Hydrothermal | `hydro_sf_electric.yml`, `hydro_df_electric.yml`, `hydro_orc_electric.yml` | H₂O | Flash or ORC surface graph |
| EGS | `EGS_electric.yml`, `EGS_direct_heat.yml` | H₂O | Stimulated (high-permeability) reservoir, pumped production well |
| CPG | `CPG_electric.yml` | CO₂ | sCO₂ turbine and condenser, no pump |
| AGS | `AGS_direct_heat.yml` | H₂O | Closed loop with no reservoir: injection well → `horizontal_well` → production well → surface |

Electricity versus direct heat is set by `economic.main_product` and the surface graph.

| `type` | `variant` | Class |
|---|---|---|
| `injection_well` | `lumped`, `numerical` | `LumpedInjectionWell`, `NumericalInjectionWell` |
| `production_well` | `lumped`, `numerical` | `LumpedProductionWell`, `NumericalProductionWell` |
| `production_well_with_pump` | `lumped`, `numerical` | `LumpedProductionWellWithPump`, `NumericalProductionWellWithPump` |
| `horizontal_well` | `numerical` | `NumericalWell` |
| `reservoir` | `lumped` | `LumpedReservoir` |
| `surface` | `graph` | `GraphSurface` |
| `economic` | `doublet` | `DoubletEconomicComponent` |

To add a component, see `src/tango/components/AGENTS.md`.
