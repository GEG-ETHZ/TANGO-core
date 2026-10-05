"""Full-length regression coverage for every ``example_configs/*.yml`` file.

Companion to ``test_lcoe_regression.py``: that file owns detailed,
topology-specific injection-well/reservoir/surface physics checks for
``hydro_sf_electric.yml`` (the flagship config other apps/tests build on)
plus smoke-level/structural checks of ``AGS_direct_heat.yml``. This file's
job is the golden-value regression check for EVERY ``example_configs/``
YAML, including those two -- one consistent pattern, run for each config's
own real ``sim_config.num_tsteps`` (never a reduced smoke count):

- Injection well heats the fluid going down (``T_outlet > T_inlet``) and
  hydrostatic gain dominates friction loss (``P_outlet > P_inlet``).
- The surface plant's relevant net output (``net_power_W`` for
  ``main_product: electricity``, ``net_thermal_W`` for ``main_product: heat``)
  is positive at every timestep past the known t=0 cold-start transient
  (see ``SystemBCIteration._seed_circuit_inlet``'s docstring).
- ``economic.state.LCOE`` matches a committed golden snapshot (``rel=2e-3``,
  sized off directly-measured run-to-run solver jitter -- up to ~4.5e-4
  relative observed on ``EGS_electric.yml`` -- with margin). This is a
  self-consistency check against tango's own prior output, not a
  comparison against any other implementation.

Marked ``@pytest.mark.slow`` (full-length runs) -- run explicitly with
``just test --example-configs`` or ``just test --all``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tango.workflows.workflow import Workflow

EXAMPLE_CONFIGS_DIR = Path(__file__).parents[2] / "example_configs"

# (filename, golden LCOE)
# Values captured by actually running each config at its own
# sim_config.num_tsteps -- see this module's own docstring for how/why.
_CONFIGS: list[tuple[str, float]] = [
    ("AGS_direct_heat.yml", 1.347554525584351),
    ("AGS_ORC_electric.yml", 3.189468907637825),
    ("CO2_AGS_direct_heat.yml", 3.430560824840202),
    ("CO2_AGS_electric.yml", 2.894305692588767),
    ("CO2_AGS_ORC_electric.yml", 10.858518773583747),
    ("CO2_EGS_direct_heat.yml", 0.37081623810556097),
    ("CO2_EGS_electric.yml", 0.39591097194615527),
    ("CO2_EGS_ORC_electric.yml", 1.5521956606601846),
    ("CPG_direct_heat.yml", 0.07724845121928584),
    ("CPG_electric.yml", 0.3144985475945345),
    ("EGS_direct_heat.yml", 0.09835620317948932),
    ("EGS_electric.yml", 1.5503718832532005),
    ("hydro_df_electric.yml", 0.9803072013606611),
    ("hydro_direct_heat.yml", 0.05386014520503487),
    ("hydro_ORC_electric.yml", 0.481298499943199),
    ("hydro_sf_electric.yml", 1.456149720517969),
    ("hydro_sf_electric_5spot.yml", 0.8111606891042009),
    ("hydro_sf_electric_autoflow.yml", 1.3571990756178616),
    ("hydro_sf_electric_autopressure.yml", 1.2939627476272397),
]


def test_every_example_config_is_covered() -> None:
    """Every example_configs/*.yml is in _CONFIGS above."""
    on_disk = {p.name for p in EXAMPLE_CONFIGS_DIR.glob("*.yml")}
    covered = {name for name, _ in _CONFIGS}
    missing = on_disk - covered
    assert not missing, (
        f"example_configs/ has file(s) with no regression coverage: {sorted(missing)} -- "
        "add each to test_example_configs.py's _CONFIGS."
    )


def _components(wf: Workflow) -> dict[str, Any]:
    return wf._orchestrator.components  # noqa: SLF001


@pytest.mark.slow
@pytest.mark.parametrize(("filename", "reference_lcoe"), _CONFIGS, ids=[c[0] for c in _CONFIGS])
def test_example_config_full_run(filename: str, reference_lcoe: float) -> None:
    """Run one example_configs/*.yml at its own full sim_config.num_tsteps and check it."""
    path = EXAMPLE_CONFIGS_DIR / filename
    wf = Workflow.from_file(path)
    wf.run()

    comps = _components(wf)
    inj = comps["injection_well"]
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
    assert lcoe == pytest.approx(reference_lcoe, rel=2e-3), (
        f"{filename}: LCOE {lcoe} is more than 0.2% off the golden value {reference_lcoe}"
    )
