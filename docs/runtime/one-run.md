# One run, end to end

What happens between `tango_cli run config.yml` and the results files. The user's two decisions, the config and where the results go (`--save-dir DIR`, or `--no-save` for none; one is required), are the only inputs; the exit code tells a script which stage failed.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#FFFFFF","primaryTextColor":"#202124","primaryBorderColor":"#DADCE0","lineColor":"#5F6368","secondaryColor":"#F8F9FA","tertiaryColor":"#F8F9FA","clusterBkg":"#F8F9FA","clusterBorder":"#DADCE0","edgeLabelBackground":"#FFFFFF"},"flowchart":{"curve":"basis","nodeSpacing":40,"rankSpacing":64,"useMaxWidth":true}} }%%
sequenceDiagram
  autonumber
  actor U as User
  participant CLI as tango_cli
  participant WF as Workflow
  participant OR as Orchestrator
  participant C as Components

  U->>CLI: run config.yml
  CLI->>WF: from_file: validate, build
  Note over CLI,WF: ConfigError → exit 1
  CLI->>WF: run()
  WF->>OR: run()
  loop each timestep
    OR->>C: solve(inlet) in order
    C-->>OR: outlet Stream
    OR->>C: record(t)
  end
  OR->>C: finalize: economics, LCOE
  Note over CLI,C: TangoError → exit 2
  opt --save-dir (not --no-save)
    CLI->>U: write_results: .yml, .csv
  end
```

| Step | Code |
|---|---|
| Parse arguments, call `_cmd_run` | `src/tango/tango_cli.py` |
| Load and validate, build components and orchestrator | `Workflow.from_file` → `Workflow.__init__` (`src/tango/workflows/workflow.py`) |
| Timestep loop | `SystemDirect.run` (`src/tango/orchestrators/system_direct.py`) |
| Economics, once | `SystemDirect.finalize` → `DoubletEconomicComponent.solve` (`src/tango/components/economic/doublet.py`) |
| Write files | `write_results` (`src/tango/results_export.py`) |

Exit codes and the files `--save-dir` writes are listed in [Run a simulation](../guides/run.md#3-run-it).
