# From config to objects

TANGO follows *object == config* (the first commandment in `CONTRIBUTING.md`): every block in the YAML file becomes one validated object. `Workflow.__init__` (`src/tango/workflows/workflow.py`) does the mapping; a validation failure raises `ConfigError` before anything runs.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#FFFFFF","primaryTextColor":"#202124","primaryBorderColor":"#DADCE0","lineColor":"#5F6368","secondaryColor":"#F8F9FA","tertiaryColor":"#F8F9FA","clusterBkg":"#F8F9FA","clusterBorder":"#DADCE0","edgeLabelBackground":"#FFFFFF"},"flowchart":{"curve":"basis","nodeSpacing":40,"rankSpacing":64,"useMaxWidth":true}} }%%
flowchart TB
  subgraph yml ["config.yml, written by the user"]
    direction LR
    k1("common")
    k2("layout")
    k3("sim_config")
    k4("components")
    k5("economic")
  end
  subgraph val ["Validated by pydantic, else ConfigError"]
    direction LR
    s1("Common")
    s2("Layout")
    s3("SimConfig")
    reg("COMPONENT_REGISTRY")
    eco("DoubletEconomic<br/>Component")
  end
  cmp("Component.from_dict<br/>one object per entry")
  bc("SystemBCIteration<br/>injection_mode set")
  dir("SystemDirect<br/>injection_mode absent")

  k1 --> s1
  k2 --> s2
  k3 --> s3
  k4 --> reg
  k5 --> reg
  reg --> eco
  s1 -. by reference .-> cmp
  s2 -.-> cmp
  reg --> cmp
  s3 --> bc
  s3 --> dir

  class k1,k2,k3,k4,k5 human
  class s1,s2,s3 code
  class reg,cmp code
  class eco econ
  class bc,dir code
  classDef well  fill:#F3EDF9,stroke:#7D4FB0,color:#7D4FB0,font-size:15px
  classDef res   fill:#FBEAE7,stroke:#D2402C,color:#D2402C,font-size:15px
  classDef surf  fill:#E8F0FA,stroke:#2F6FBF,color:#2F6FBF,font-size:15px
  classDef econ  fill:#E0F2F1,stroke:#007B83,color:#007B83,font-size:15px
  classDef code  fill:#FFFFFF,stroke:#DADCE0,color:#202124,font-size:15px
  classDef err   fill:#FCE8E6,stroke:#D93025,color:#D93025,font-size:15px
  classDef out   fill:#FFFFFF,stroke:#9AA0A6,color:#5F6368,stroke-dasharray:4 3,font-size:15px
  classDef human fill:#202124,stroke:#9AA0A6,color:#FFFFFF,font-size:15px
```

| YAML block | Becomes | Defined in |
|---|---|---|
| `common` | `Common`, one instance shared by reference with every component | `src/tango/core/specs.py` |
| `layout` | `Layout`; `well_spacing` and `well_pattern` are copied into components that declare them | `src/tango/core/specs.py` |
| `sim_config` | `SimConfig`: `num_tsteps`, `dt_years`, `injection_mode`, `mass_rate`, `max_mass_rate`, `target_extraction_pressure`, `bc_checkpoint_idx` | `src/tango/core/specs.py` |
| `components.<name>` | `COMPONENT_REGISTRY[(type, variant)].from_dict(...)` | `src/tango/components/registry.py` |
| `economic` | `COMPONENT_REGISTRY[("economic", type)]`, today `DoubletEconomicComponent` | `src/tango/components/registry.py`, `src/tango/components/economic/doublet.py` |
| `title`, `description` | `Description` (optional) | `src/tango/core/specs.py` |

The orchestrator follows from one key: if `sim_config.injection_mode` is set, the run uses `SystemBCIteration`; if it is absent, `SystemDirect` (one pass per timestep). Every config in `example_configs/` sets it.

A component block may not set `common` or the layout-derived keys itself; the workflow threads those in from the single source above. See [config validation](../CONFIG_VALIDATION.md) for the full set of checks.
