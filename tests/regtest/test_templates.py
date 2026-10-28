"""Full-length regression coverage for every ``templates/*.yml`` file.

Companion to ``test_lcoe_regression.py``: that file owns detailed,
topology-specific injection-well/reservoir/surface physics checks for
``hydro_sf_electric.yml`` (the flagship config other apps/tests build on)
plus smoke-level/structural checks of ``AGS_direct_heat.yml``. This file's
job is the golden-value regression check for EVERY ``templates/``
YAML, including those two -- one consistent pattern, run for each config's
own real ``sim_config.num_tsteps`` (never a reduced smoke count):

- Injection well heats the fluid going down (``T_outlet > T_inlet``) and
  hydrostatic gain dominates friction loss (``P_outlet > P_inlet``).
- The surface plant's relevant net output (``net_power_W`` for
  ``main_product: electricity``, ``net_thermal_W`` for ``main_product: heat``)
  is positive at every timestep past the known t=0 cold-start transient
  (see ``SystemBCIteration._seed_circuit_inlet``'s docstring).
- ``economic.state.LCOE`` matches a committed golden snapshot (``rel=1e-6``:
  with the exact ``HEOS`` CoolProp backend, reruns agree to within 2e-11
  relative, so this leaves room for platform differences while still
  catching any real change). This is a self-consistency check against
  tango's own prior output, not a comparison against any other
  implementation.

Marked ``@pytest.mark.slow`` (full-length runs) -- run explicitly with
``just test --templates`` or ``just test --all``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tango_core.components.well.grouped_subsurface import NumericalGroupedSubsurface
from tango_core.workflows.workflow import Workflow

TEMPLATES_DIR = Path(__file__).parents[2] / "templates"

# (filename, golden LCOE)
# Values captured by actually running each config at its own
# sim_config.num_tsteps -- see this module's own docstring for how/why.
_CONFIGS: list[tuple[str, float]] = [
    ("AGS_direct_heat.yml", 0.7191321530423379),
    ("AGS_ORC_electric.yml", 2.061905093287347),
    ("AGS_ORC_electric_grouped_subsurface.yml", 3.421900718151467),
    ("AGS_ORC_electric_raft.yml", 2.1193281005233104),
    ("CO2_AGS_direct_heat.yml", 0.38844042532415946),
    ("CO2_AGS_electric.yml", 1.6625122145149076),
    ("CO2_AGS_ORC_electric.yml", 4.15796052520762),
    ("CO2_EGS_direct_heat.yml", 0.276817357495942),
    ("CO2_EGS_electric.yml", 0.3651397411220982),
    ("CO2_EGS_ORC_electric.yml", 1.304986099286206),
    ("CPG_direct_heat.yml", 0.056466163448062386),
    ("CPG_electric.yml", 0.3038099358259784),
    ("EGS_direct_heat.yml", 0.09220403151106003),
    ("EGS_electric.yml", 1.0196783884745808),
    ("hydro_df_electric.yml", 0.4236438278706548),
    ("hydro_direct_heat.yml", 0.03600456578455728),
    ("hydro_ORC_electric.yml", 0.32694303779297584),
    ("hydro_sf_electric.yml", 0.47191635645469593),
    ("hydro_sf_electric_5spot.yml", 0.8108358034934499),
]


def test_every_template_is_covered() -> None:
    """Every templates/*.yml is in _CONFIGS above."""
    on_disk = {p.name for p in TEMPLATES_DIR.glob("*.yml")}
    covered = {name for name, _ in _CONFIGS}
    missing = on_disk - covered
    assert not missing, (
        f"templates/ has file(s) with no regression coverage: {sorted(missing)} -- "
        "add each to test_templates.py's _CONFIGS."
    )


def _components(wf: Workflow) -> dict[str, Any]:
    return wf._orchestrator.components  # noqa: SLF001


def _injection_well(comps: dict[str, Any]) -> Any:
    """The injection well: its own component, the first segment of a numerical ``grouped_subsurface``, or
    (for a ``grouped_subsurface`` an external simulator models as a whole) the loop itself.
    """
    entry = next(c for c in comps.values() if c.component_idx == 0)
    return entry.injection_well if isinstance(entry, NumericalGroupedSubsurface) else entry


# Templates whose subsurface needs the optional RAFT extra; skipped without it.
_NEEDS_RAFT = {"AGS_ORC_electric_raft.yml"}


@pytest.mark.slow
@pytest.mark.parametrize(("filename", "reference_lcoe"), _CONFIGS, ids=[c[0] for c in _CONFIGS])
def test_template_full_run(
    filename: str,
    reference_lcoe: float,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run one templates/*.yml at its own full sim_config.num_tsteps and check it."""
    if filename in _NEEDS_RAFT:
        pytest.importorskip("geg_raft")
    # RAFT's config template is given relative to the repository root.
    monkeypatch.chdir(TEMPLATES_DIR.parent)
    path = TEMPLATES_DIR / filename
    wf = Workflow.from_file(path)
    wf.run()

    comps = _components(wf)
    inj = _injection_well(comps)
    assert inj.state.T_outlet.get_fresh() > inj.state.T_inlet.get_fresh(), (
        f"{filename}: injection well outlet T should exceed inlet T (geothermal gradient heats downward flow)"
    )
    assert inj.state.P_outlet.get_fresh() > inj.state.P_inlet.get_fresh(), (
        f"{filename}: injection well outlet P should exceed inlet P (hydrostatic gain "
        "dominates friction loss)"
    )

    surface = comps["surface"]
    main_product = wf.to_dict()["economic"]["main_product"]
    history = surface.history.net_power_W if main_product == "electricity" else surface.history.net_thermal_W
    # t=0 is a known cold-start transient (circuit seeded at surface_temperature
    # rather than the steady re-injection temperature -- see
    # SystemBCIteration._seed_circuit_inlet's docstring), so check steady-state
    # behavior from t=1 on, same as test_ags_direct_heat_smoke.
    steady_state = history[1:]
    assert all(v > 0 for v in steady_state), (
        f"{filename}: {'net_power_W' if main_product == 'electricity' else 'net_thermal_W'} "
        f"should stay positive past the t=0 cold-start transient: {steady_state}"
    )

    assert wf._economic is not None, f"{filename}: expected an economic: block"  # noqa: SLF001
    lcoe = wf._economic.state.LCOE.get_fresh()  # noqa: SLF001
    assert lcoe == pytest.approx(reference_lcoe, rel=1e-6), (
        f"{filename}: LCOE {lcoe} is more than 1e-6 relative off the golden value {reference_lcoe}"
    )
