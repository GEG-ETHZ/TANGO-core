"""Write a completed Workflow's results to disk as three files.

``tango_cli run --save-dir DIR`` is the only caller today. Three files,
matching old tango's own summary/economic split, plus one new one tango
didn't have before:

- ``<stem>.yml``: the full results, via ``Workflow.to_file()`` -- every
  component's complete config AND final solved state/history, reloadable
  with ``Workflow.from_file()`` for further analysis. This is the
  authoritative, complete record.
- ``<stem>.smry.csv``: one row per timestep, one column per
  ``<component>_<field>`` for every SCALAR (not spatially-resolved)
  ``history`` field across all components -- a flat, spreadsheet-friendly
  view of how the run evolved. Deliberately excludes spatially-resolved
  fields (e.g. ``NumericalWellHistory.T_cells``, one list per timestep)
  since those don't fit a flat per-timestep table; the full ``.yml``
  output above is where that detail lives.
- ``<stem>.econ.csv``: one row, every field of the economic component's
  final ``state`` (CAPEX/LCOE/net power/...) -- omitted entirely if the
  config has no ``economic:`` block, since there's nothing to write.
"""

from __future__ import annotations

import csv
import dataclasses
from pathlib import Path
from typing import Any

from tango.workflows.workflow import Workflow


def write_results(wf: Workflow, save_dir: Path, stem: str) -> list[Path]:
    """Write ``<stem>.yml``/``.smry.csv``/``.econ.csv`` into ``save_dir``.

    Args:
        wf: A Workflow whose ``run()`` has already completed.
        save_dir: Directory to write into; created if it doesn't exist.
        stem: Base filename (no extension) -- typically the input YAML's
            own stem.

    Returns:
        Paths actually written, in the order listed in this module's own
        docstring.
    """
    save_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    yaml_path = save_dir / f"{stem}.yml"
    wf.to_file(yaml_path)
    written.append(yaml_path)

    smry_path = save_dir / f"{stem}.smry.csv"
    _write_timestep_summary_csv(wf, smry_path)
    written.append(smry_path)

    if wf._economic is not None:  # noqa: SLF001
        econ_path = save_dir / f"{stem}.econ.csv"
        _write_economic_summary_csv(wf, econ_path)
        written.append(econ_path)

    return written


def _write_timestep_summary_csv(wf: Workflow, path: Path) -> None:
    """One row per timestep; columns are every component's own scalar history fields."""
    columns: dict[str, list[Any]] = {}
    for name, component in wf._orchestrator.components.items():  # noqa: SLF001
        history = getattr(component, "history", None)
        if history is None:
            continue
        for f in dataclasses.fields(history):
            values = getattr(history, f.name)
            if not isinstance(values, list) or not values or isinstance(values[0], list):
                # Not a plain per-timestep list at all (e.g. GraphSurfaceHistory's
                # node_history, a dict[node][quantity] -> list[value] snapshot --
                # see that class's own docstring for why), empty, or
                # spatially-resolved (e.g. NumericalWellHistory.T_cells, one list
                # per timestep) -- none of these fit a flat per-timestep table.
                continue
            columns[f"{name}_{f.name}"] = values

    n_tsteps = wf._sim_config.num_tsteps  # noqa: SLF001
    dt_years = wf._sim_config.dt_years  # noqa: SLF001
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestep", "year", *columns.keys()])
        for t in range(n_tsteps):
            row: list[Any] = [t, t * dt_years]
            for values in columns.values():
                row.append(values[t] if t < len(values) else "")
            writer.writerow(row)


def _write_economic_summary_csv(wf: Workflow, path: Path) -> None:
    """One row: every field of the economic component's final state.

    Caller (``write_results``) already checked ``wf._economic is not
    None`` -- this assert is for mypy's benefit only, documenting that
    invariant rather than adding a new runtime check.
    """
    assert wf._economic is not None  # noqa: S101, SLF001
    state = wf._economic.state  # noqa: SLF001
    fields = [f.name for f in dataclasses.fields(state)]
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(fields)
        writer.writerow([getattr(state, name).get_fresh() for name in fields])
