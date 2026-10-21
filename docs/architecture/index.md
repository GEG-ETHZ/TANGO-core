# Architecture

![System key: surface plant blue, wells purple, reservoir red, economics teal](../diagrams/system-key.drawio.svg){ align=right width="260" }

TANGO is one Python package, `src/tango/`, built in layers. A user writes a YAML config and starts a run; everything below that line is validated code. Each layer imports only the layers beneath it, with one exception: `core/specs.py` uses the well-pattern helper from `components/reservoir/`. The third-party engines run in-process: TESPy is called from `components/surface/`, CoolProp from `core/` (fluid properties).

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#FFFFFF","primaryTextColor":"#202124","primaryBorderColor":"#DADCE0","lineColor":"#5F6368","secondaryColor":"#F8F9FA","tertiaryColor":"#F8F9FA","clusterBkg":"#F8F9FA","clusterBorder":"#DADCE0","edgeLabelBackground":"#FFFFFF"},"flowchart":{"curve":"basis","nodeSpacing":40,"rankSpacing":64,"useMaxWidth":true}} }%%
flowchart TB
  user("User<br/>config.yml, starts a run")
  subgraph pkg ["src/tango"]
    cli("tango_cli<br/>run · validate")
    pymoo("pymoo_api<br/>NSGA-II")
    surr("surrogate_api<br/>ML surrogates")
    wf("workflows<br/>Workflow")
    orchs("orchestrators<br/>timestep loop")
    reg("registry<br/>(type, variant)")
    comps("components<br/>well · reservoir<br/>surface · economic")
    core("core<br/>Component · Stream<br/>schemas · errors")
  end
  ext("TESPy · CoolProp")

  user --> cli
  user --> pymoo
  surr --> pymoo
  cli --> wf
  pymoo --> wf
  wf --> orchs
  wf --> reg
  reg --> comps
  orchs --> core
  comps --> core
  comps --> ext

  class cli,wf,orchs code
  class pymoo,surr code
  class reg,comps code
  class core code
  class ext code
  class user human
  classDef well  fill:#F3EDF9,stroke:#7D4FB0,color:#7D4FB0,font-size:15px
  classDef res   fill:#FBEAE7,stroke:#D2402C,color:#D2402C,font-size:15px
  classDef surf  fill:#E8F0FA,stroke:#2F6FBF,color:#2F6FBF,font-size:15px
  classDef econ  fill:#E0F2F1,stroke:#007B83,color:#007B83,font-size:15px
  classDef code  fill:#FFFFFF,stroke:#DADCE0,color:#202124,font-size:15px
  classDef err   fill:#FCE8E6,stroke:#D93025,color:#D93025,font-size:15px
  classDef out   fill:#FFFFFF,stroke:#9AA0A6,color:#5F6368,stroke-dasharray:4 3,font-size:15px
  classDef human fill:#202124,stroke:#9AA0A6,color:#FFFFFF,font-size:15px
```

## Where is what

| Layer | Path | Holds |
|---|---|---|
| Entry points | `src/tango/tango_cli.py` | `tango_cli run`, `validate`, `init` |
| | `src/tango/pymoo_api.py` | NSGA-II optimization over full runs |
| | `src/tango/surrogate_api.py` | ML surrogate sampling, training and search |
| | `src/tango/results_export.py` | `write_results`: YAML plus CSV files |
| Workflow | `src/tango/workflows/` | `Workflow`: config in, orchestrator out |
| Orchestration | `src/tango/orchestrators/` | `SystemDirect`, `SystemBCIteration` |
| Components | `src/tango/components/` | wells, reservoir, surface plant, economics, `COMPONENT_REGISTRY` |
| Core | `src/tango/core/` | `Component`, `Stream`, `LockedState`, specs, policies, errors, numerics |

Around the package:

| Path | Role |
|---|---|
| `example_configs/` | The maintained configs; each backs a test or an application |
| `applications/` | Multi-run pipelines (sweeps, optimizations) built on those configs |
| `tests/` | `unit/` and `regtest/` |

Next: [how a config becomes objects](config.md) and [what flows between components](components.md). For how a run iterates, see [Runtime](../runtime/index.md).
