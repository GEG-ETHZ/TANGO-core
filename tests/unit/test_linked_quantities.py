"""Linked config values across components: one source each, the rest derived and checked.

See ``tango.workflows.linked_quantities`` for the relations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from tango.core.constants import GRAVITY
from tango.core.errors import ConfigError
from tango.workflows.linked_quantities import expunge_linked_quantities, resolve_linked_quantities
from tango.workflows.workflow import Workflow

_CONFIGS = Path(__file__).resolve().parents[2] / "templates"


def _load(name: str) -> dict[str, Any]:
    cfg: dict[str, Any] = yaml.safe_load((_CONFIGS / name).read_text(encoding="utf-8"))
    cfg["sim_config"]["num_tsteps"] = 1
    return cfg


def test_doublet_values_are_derived_from_reservoir_depth_and_pump_depth() -> None:
    """Injection length, lower segment, well_eff_diameter and hydro_static_pressure all follow the two sources."""
    cfg = _load("hydro_sf_electric.yml")
    comps = cfg["components"]
    comps["reservoir"]["reservoir_depth"] = 4000.0
    comps["production_well_upper"]["well_length"] = 800.0
    comps["injection_well"]["diameter"] = 0.3
    comps["production_well_lower"]["diameter"] = 0.5
    comps["production_well_upper"]["diameter"] = 0.5
    out = resolve_linked_quantities(cfg)["components"]
    assert out["injection_well"]["well_length"] == 4000.0
    assert out["production_well_lower"]["wellhead_depth"] == 800.0
    assert out["production_well_lower"]["well_length"] == 3200.0
    assert out["reservoir"]["well_eff_diameter"] == pytest.approx(0.4)
    rho = comps["reservoir"].get("brine_density", 1000.0)
    assert out["reservoir"]["hydro_static_pressure"] == pytest.approx(rho * GRAVITY * 4000.0)


def test_reservoir_depth_can_come_from_the_injection_well() -> None:
    """Either end of an equality may be the one given."""
    cfg = _load("hydro_sf_electric.yml")
    depth = cfg["components"]["reservoir"].pop("reservoir_depth")
    cfg["components"]["injection_well"]["well_length"] = depth
    assert resolve_linked_quantities(cfg)["components"]["reservoir"]["reservoir_depth"] == depth


def test_stale_copy_raises() -> None:
    """A sweep that changes the reservoir depth but leaves an old injection length gets an error, not a wrong run."""
    cfg = _load("hydro_sf_electric.yml")
    cfg["components"]["injection_well"]["well_length"] = (
        cfg["components"]["reservoir"]["reservoir_depth"] + 500
    )
    with pytest.raises(ConfigError, match="injection_well.well_length"):
        Workflow(cfg)


def test_ags_well_spacing_and_depths_are_derived() -> None:
    """The loop's depth and length set the vertical wells, the loop's starting depth and well_spacing."""
    cfg = _load("AGS_direct_heat.yml")
    cfg["components"]["injection_well"]["well_length"] = 4200.0
    cfg["components"]["horizontal_well"]["well_length"] = 1500.0
    out = resolve_linked_quantities(cfg)
    assert out["components"]["production_well"]["well_length"] == 4200.0
    assert out["components"]["horizontal_well"]["wellhead_depth"] == 4200.0
    assert out["layout"]["well_spacing"] == 1500.0


def test_expunge_lets_a_to_dict_copy_be_edited() -> None:
    """to_dict() writes every copy; expunging the derived ones makes the source editable again."""
    wf_cfg = Workflow(_load("hydro_sf_electric.yml")).to_dict()
    wf_cfg["components"]["reservoir"]["reservoir_depth"] = 4000.0
    with pytest.raises(ConfigError):
        Workflow(wf_cfg)
    expunge_linked_quantities(wf_cfg)
    wf = Workflow(wf_cfg)
    assert wf._orchestrator.components["injection_well"].well_length == 4000.0  # noqa: SLF001


def test_reservoir_derived_value_mismatch_raises() -> None:
    """LumpedReservoir's init()-computed values aren't silently replaced when a config supplies them."""
    cfg = _load("hydro_sf_electric.yml")
    cfg["components"]["reservoir"]["T_initial"] = 300.0
    with pytest.raises(ConfigError, match="T_initial"):
        Workflow(cfg)


def test_to_dict_omits_reservoir_derived_values() -> None:
    """Pure outputs aren't serialized, so an edited input reloads without a stale copy."""
    reservoir = Workflow(_load("hydro_sf_electric.yml")).to_dict()["components"]["reservoir"]
    assert not {"T_initial", "P_initial", "rock_volume", "rock_C_v", "wp"} & set(reservoir)
