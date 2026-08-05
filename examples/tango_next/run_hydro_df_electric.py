from pathlib import Path

from tango_next.workflows.workflow import Workflow

wf = Workflow.from_file(Path(__file__).parent / "hydro_df_electric.yml")
wf.run()
