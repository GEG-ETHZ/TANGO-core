# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Write a completed Workflow's results to disk as three files.

``tango_core run --save-dir DIR`` is the only caller today. Three files,
matching old tango's own summary/economic split, plus one new one tango
didn't have before:

- ``<stem>.results.yml``: the full results, via ``Workflow.to_file()`` -- every
  component's complete config AND final solved state/history, reloadable
  with ``Workflow.from_file()`` for further analysis. This is the
  authoritative, complete record. The ``.results`` part keeps it from
  having the same name as the input file it came from.
- ``<stem>.smry.csv``: one row per step end time, one column per
  ``<component>_<field>`` for every SCALAR (not spatially-resolved)
  ``history`` field across all components -- a flat, spreadsheet-friendly
  view of how the run evolved. Deliberately excludes spatially-resolved
  fields (e.g. ``NumericalWellHistory.T_cells``, one list per timestep)
  since those don't fit a flat per-timestep table; the full ``.yml``
  output above is where that detail lives.
- ``<stem>.econ.csv``: one row, every field of the economic component's
  final ``state`` (CAPEX/LCOE/net power/...) -- omitted entirely if the
  config has no ``economic:`` block, since there's nothing to write.

Every CSV column header ends in its unit, e.g. ``production_well_T_outlet
[K]`` (``[-]`` for a dimensionless quantity), from ``FIELD_UNITS``.

An external simulator's own output files go next to these, in
``<stem>.raft/`` for a RAFT subsurface; ``keep_external_outputs`` sets that
up before the run.
"""

from __future__ import annotations

import csv
import dataclasses
from pathlib import Path
from typing import Any

from tango_core.components.well.grouped_subsurface import (
    SEGMENT_NAMES,
    NumericalGroupedSubsurface,
    RaftGroupedSubsurface,
)
from tango_core.workflows.workflow import Workflow

_TIME_DECIMALS: int = 6
"""Decimal places (of a second) to which step end times are rounded before
two components' rows are matched, so float noise does not split one row in two."""

FIELD_UNITS: dict[str, str] = {
    # Stream and fluid properties
    "T_inlet": "K",
    "T_outlet": "K",
    "T_reservoir_initial": "K",
    "P_inlet": "Pa",
    "P_outlet": "Pa",
    "P_reservoir": "Pa",
    "P_tespy_inlet": "Pa",
    "h_inlet": "J/kg",
    "h_outlet": "J/kg",
    "mass_rate": "kg/s",
    "rho": "kg/m^3",
    "mu": "Pa s",
    "velocity": "m/s",
    # Pressure changes
    "dP_pipe": "Pa",
    "delta_p_darcy": "Pa",
    "delta_p_friction": "Pa",
    "delta_p_hydrostatic": "Pa",
    "pump_delta_p": "Pa",
    # Wells and reservoir
    "Re": "-",
    "friction_factor": "-",
    "t_d": "-",
    "impedance": "Pa s/kg",
    "psi": "-",
    "gamma": "-",
    "p1": "-",
    "p2": "-",
    "p3": "-",
    "energy_extraction_rate": "W",
    "energy_extracted": "J",
    "heat_extracted_watts": "W",
    "mass_rate_inlet": "kg/s",
    "mass_rate_outlet": "kg/s",
    "trial_solves": "-",
    "solve_seconds": "s",
    "accepted_steps": "-",
    "attempts": "-",
    "cut_extrapolation": "-",
    "cut_newton": "-",
    "constraint_switches": "-",
    "dt_min_proceeds": "-",
    "ever_solved": "bool",
    # Power
    "pump_power_watts": "W",
    "net_power_W": "W",
    "net_thermal_W": "W",
    # Economics
    "CAPEX_well": "USD",
    "CAPEX_permitting": "USD",
    "CAPEX_exploration": "USD",
    "CAPEX_surface_pipes": "USD",
    "CAPEX_surface_plant": "USD",
    "CAPEX_total": "USD",
    "LCOE": "USD/kWh",
    "specific_investment_cost": "USD/kW",
    "OPEX": "USD/yr",
}
"""Unit of every field written to the CSVs, keyed by field name (no component prefix).

A field missing here raises ``KeyError`` when the CSVs are written, so a new
history or economic field can't reach a CSV without a unit.
"""


def _with_unit(column: str, field_name: str) -> str:
    """``column`` with ``field_name``'s unit appended, e.g. ``"surface_T_outlet [K]"``."""
    return f"{column} [{FIELD_UNITS[field_name]}]"


def keep_external_outputs(wf: Workflow, save_dir: Path, stem: str) -> list[Path]:
    """Have each RAFT subsurface keep its own output files (VTKs, flow logs) in ``save_dir``.

    Call before ``wf.run()``. With one RAFT component the directory is
    ``<stem>.raft/``; with several, ``<stem>.<component>.raft/``.

    Returns:
        The directories RAFT will write into.
    """
    rafts = [
        (name, component)
        for name, component in wf._orchestrator.components.items()  # noqa: SLF001
        if isinstance(component, RaftGroupedSubsurface)
    ]
    directories = []
    for name, component in rafts:
        directory = save_dir / (f"{stem}.raft" if len(rafts) == 1 else f"{stem}.{name}.raft")
        component.raft.set_output_dir(directory)
        directories.append(directory)
    return directories


def write_results(wf: Workflow, save_dir: Path, stem: str) -> list[Path]:
    """Write ``<stem>.results.yml``/``.smry.csv``/``.econ.csv`` into ``save_dir``.

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

    yaml_path = save_dir / f"{stem}.results.yml"
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


def _named_histories(wf: Workflow) -> list[tuple[str, Any, list[float]]]:
    """``(name, history, step end times)`` for every component, plus a ``grouped_subsurface``'s segments or RAFT.

    A segment or RAFT is named ``"<name>.<part>"`` and shares its
    component's step end times, since it records whenever the component does.
    """
    named: list[tuple[str, Any, list[float]]] = []
    for name, component in wf._orchestrator.components.items():  # noqa: SLF001
        t_end = component.time_history.t_end
        named.append((name, getattr(component, "history", None), t_end))
        if isinstance(component, NumericalGroupedSubsurface):
            named += [
                (f"{name}.{segment_name}", segment.history, t_end)
                for segment_name, segment in zip(SEGMENT_NAMES, component.segments(), strict=True)
            ]
        elif isinstance(component, RaftGroupedSubsurface):
            named.append((f"{name}.raft", component.raft.history, t_end))
    return named


def _write_timestep_summary_csv(wf: Workflow, path: Path) -> None:
    """One row per recorded step end time (s); columns are every component's own scalar history fields.

    Components on different grids, or with different ``save_interval``s,
    record at different times; each value sits in the row of its own
    step's end time, and a component with no step ending at a row's time
    leaves that cell empty.
    """
    columns: dict[str, dict[float, Any]] = {}
    for name, history, t_end in _named_histories(wf):
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
            columns[_with_unit(f"{name}_{f.name}", f.name)] = {
                round(time, _TIME_DECIMALS): value for time, value in zip(t_end, values, strict=True)
            }

    times = sorted({time for by_time in columns.values() for time in by_time})
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["time [s]", *columns.keys()])
        for time in times:
            writer.writerow([time, *(by_time.get(time, "") for by_time in columns.values())])


def _write_economic_summary_csv(wf: Workflow, path: Path) -> None:
    """One row: every field of the economic component's final state.

    Caller (``write_results``) already checked ``wf._economic is not
    None`` -- this assert is for mypy's benefit only, documenting that
    invariant rather than adding a new runtime check.
    """
    assert wf._economic is not None  # noqa: S101, SLF001
    state = wf._economic.state  # noqa: SLF001
    fields = [f.name for f in dataclasses.fields(state)]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([_with_unit(name, name) for name in fields])
        writer.writerow([getattr(state, name).get_fresh() for name in fields])
