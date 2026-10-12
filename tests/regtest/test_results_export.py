"""Regression tests for ``results_export.write_results``.

Uses a reduced timestep count (fast) rather than any example config's own
full length -- this is about the file-writing mechanism, not physics, so
there's no reason to pay for a full-length run.
"""

from __future__ import annotations

import csv
import dataclasses
import re
from pathlib import Path

import pytest

from tango import results_export
from tango.workflows.workflow import Workflow

_EXAMPLE_CONFIGS_DIR = Path(__file__).parents[2] / "example_configs"
_N_TSTEPS_FAST = 3


def _run_fast(filename: str) -> Workflow:
    cfg = Workflow.from_file(_EXAMPLE_CONFIGS_DIR / filename).to_dict()
    cfg["sim_config"]["num_tsteps"] = _N_TSTEPS_FAST
    wf = Workflow(cfg)
    wf.run()
    return wf


def test_write_results_writes_three_files(tmp_path: Path) -> None:
    """write_results() writes exactly the .results.yml/.smry.csv/.econ.csv paths it returns."""
    wf = _run_fast("hydro_sf_electric.yml")
    written = results_export.write_results(wf, tmp_path, "hydro_sf_electric")

    assert written == [
        tmp_path / "hydro_sf_electric.results.yml",
        tmp_path / "hydro_sf_electric.smry.csv",
        tmp_path / "hydro_sf_electric.econ.csv",
    ]
    for path in written:
        assert path.exists()


def test_full_yaml_is_reloadable(tmp_path: Path) -> None:
    """The .results.yml file round-trips through Workflow.from_file with state intact."""
    wf = _run_fast("hydro_sf_electric.yml")
    results_export.write_results(wf, tmp_path, "hydro_sf_electric")

    reloaded = Workflow.from_file(tmp_path / "hydro_sf_electric.results.yml")
    assert reloaded.title == wf.title
    assert reloaded._economic is not None  # noqa: SLF001
    assert wf._economic is not None  # noqa: SLF001
    assert reloaded._economic.state.LCOE.get_fresh() == wf._economic.state.LCOE.get_fresh()  # noqa: SLF001


def test_smry_csv_has_one_row_per_timestep(tmp_path: Path) -> None:
    """.smry.csv has one row per timestep and skips spatially-resolved fields."""
    wf = _run_fast("hydro_sf_electric.yml")
    results_export.write_results(wf, tmp_path, "hydro_sf_electric")

    with (tmp_path / "hydro_sf_electric.smry.csv").open() as f:
        rows = list(csv.reader(f))

    header, data_rows = rows[0], rows[1:]
    assert len(data_rows) == _N_TSTEPS_FAST
    assert header[:2] == ["timestep [-]", "year [yr]"]
    # Every component's own scalar history fields should show up as columns,
    # with units, e.g. the injection well's inlet/outlet temperature.
    assert "injection_well_T_inlet [K]" in header
    assert "injection_well_T_outlet [K]" in header
    # Spatially-resolved fields (one list per timestep) must NOT show up --
    # they don't fit a flat per-timestep table (see this module's own
    # docstring / _write_timestep_summary_csv's comment for why).
    assert not any(column.startswith("injection_well_T_cells") for column in header)


def test_econ_csv_matches_economic_state(tmp_path: Path) -> None:
    """.econ.csv's single row matches every field of the economic component's state."""
    wf = _run_fast("hydro_sf_electric.yml")
    results_export.write_results(wf, tmp_path, "hydro_sf_electric")

    with (tmp_path / "hydro_sf_electric.econ.csv").open() as f:
        header, row = list(csv.reader(f))

    assert wf._economic is not None  # noqa: SLF001
    state = wf._economic.state  # noqa: SLF001
    names = [column.split(" [")[0] for column in header]
    for name, value in zip(names, row, strict=True):
        assert float(value) == getattr(state, name).get_fresh()
    assert {f.name for f in dataclasses.fields(state)} == set(names)
    assert "LCOE [USD/kWh]" in header


def test_econ_csv_omitted_without_economic_block(tmp_path: Path) -> None:
    """No economic: block -> no .econ.csv, but the other two files still land."""
    cfg = Workflow.from_file(_EXAMPLE_CONFIGS_DIR / "hydro_sf_electric.yml").to_dict()
    cfg["sim_config"]["num_tsteps"] = _N_TSTEPS_FAST
    del cfg["economic"]
    wf = Workflow(cfg)
    wf.run()

    written = results_export.write_results(wf, tmp_path, "no_economic")

    assert written == [
        tmp_path / "no_economic.results.yml",
        tmp_path / "no_economic.smry.csv",
    ]
    assert not (tmp_path / "no_economic.econ.csv").exists()


@pytest.mark.parametrize("filename", sorted(p.name for p in _EXAMPLE_CONFIGS_DIR.glob("*.yml")))
def test_every_csv_column_has_a_unit(filename: str, tmp_path: Path) -> None:
    """Every example config's CSV headers all end in ``[unit]``; a field missing from FIELD_UNITS raises."""
    wf = _run_fast(filename)
    for path in results_export.write_results(wf, tmp_path, "out"):
        if path.suffix != ".csv":
            continue
        with path.open() as f:
            header = next(csv.reader(f))
        assert all(re.fullmatch(r".+ \[[^\]]+\]", column) for column in header), path.name
