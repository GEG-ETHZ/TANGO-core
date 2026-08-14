"""Old-tango vs tango_next economic (CAPEX/LCOE) parity test.

Companion to ``test_old_new_parity.py`` (physics), scoped to
``NativeEconomicComponent`` (``src/tango_next/components/economic/native.py``)
vs. old tango's ``src/tango/units/native/economic/``.

Two cases, deliberately chosen to separate "is the port correct" from "how
much does old-vs-new physics drift propagate": ``flexible_SF_manual.yml``
is tango_next's TIGHTEST physics-parity case (sub-1 K temperatures, sub-1%
power — see ``test_old_new_parity.py``'s docstring); ``flexible_DF_manual.yml``
is a looser one. If the economic port were wrong, both would show similarly
bad agreement — they don't (see per-field rationale below).

Two independent comparisons per case, same shape as the physics parity file:

1. **old vs. new**, per CAPEX category + LCOE, at documented per-field
   tolerances (see below for why each is what it is — none of these
   differences are bugs in the port; each is investigated and explained).
2. **new vs. golden** (tight) — a hardcoded snapshot of tango_next's own
   prior output, to catch any *unintended* drift in tango_next's own
   computation that would still land inside the loose old-vs-new band.
   Regenerate by rerunning this module's ``_run_tango_next()`` and pasting
   the new numbers in, only after confirming the change is intentional
   (same discipline as ``tools/update_tango_next_golden.py``, just
   self-contained here rather than routed through that shared tool, since
   these are two cases with their own tolerance shapes).

Per-field tolerance rationale (re-measured 2026-08-10, final round — after
fixing the production-well pump-power formula, see below)
-----------------------------------------------------------------------
- **CAPEX_permitting, CAPEX_exploration, CAPEX_surface_pipes, CAPEX_well:
  exact match** in both cases (rtol=1e-6). The first three don't depend on
  any physics state at all (pure functions of config + hardcoded PPI/
  multiplier constants). ``CAPEX_well`` matching exactly took a real fix
  (see ``docs/bugs-fixed-in-tango-next.md``'s "NativeEconomicComponent double-counted
  well mobilization cost across split physics sub-components" entry):
  tango_next originally combined every production-side ``WellComponent``
  by summing each one's INDEPENDENTLY-costed gengeo formula (double/
  triple-counting the formula's fixed `+275300` mobilization term once
  per physics sub-component), instead of combining their lengths into ONE
  total depth and costing that once — the same way old tango's own
  ``production_well.well_length_seq: [5000.]`` (4000 m + 1000 m combined)
  already does it correctly. Fixed in ``NativeEconomicComponent._compute_well_capex``/
  ``_combined_production_length_and_diameter``.
- **CAPEX_surface_plant / CAPEX_total: close but not exact** (SF: -6.2%/
  -0.9%; DF: -5.1%/-0.9%) — both read RUN-AVERAGED power (mean over
  ``history``, matching old tango's own
  ``create_power_plant_with_averaged_results`` design — see
  ``NativeEconomicComponent``'s module docstring), so the residual gap
  tracks ordinary old-vs-new physics-trajectory drift over the run, not a
  formula error. Tolerances (0.25 / 0.05) keep generous headroom above
  the measured values rather than being tightened to force agreement.
- **LCOE: SF -1.1%, DF -1.0%.** This used to be far worse (+16.1%/+11.5%)
  even though CAPEX_total already agreed to within 1% — the culprit was
  ``NumericalProductionWellWithPump``'s pump-power formula, which used a
  naive ``mass_rate * ΔP / ρ`` hydraulic estimate. Verified against a live
  old-tango run (``BC_calculator.py``'s inline
  ``-(inlet.H - outlet.H) * mass_rate``, no efficiency term) that this
  overstates the true ISOTHERMAL CoolProp enthalpy rise by ~53% at
  typical wellhead conditions (~400 K): water is nearly incompressible
  but not thermally inert, and it's the thermal-expansivity term in
  ``dH/dP|_T = V - T*(∂V/∂T)_P`` that matters, not compressibility.
  Fixed by switching to the same isothermal-enthalpy-rise formula old
  tango uses (see ``NumericalProductionWellWithPump.solve()``'s
  docstring for the full derivation) — this alone closed nearly the
  entire LCOE gap without touching CAPEX at all, confirming the
  diagnosis. ``pump_efficiency`` now defaults to 1.0 (matches old tango's
  formula, which applies no efficiency derating) — planned to drop to
  ~0.9 later once a real figure is settled on, deliberately deferred.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

EXAMPLES_OLD = Path(__file__).parents[2] / "examples"
EXAMPLES_NEW = EXAMPLES_OLD / "tango_next"

GOLDEN_RTOL = 1e-9
"""Tight — catches any unintended drift in tango_next's own computation."""

_CAPEX_FIELDS = (
    "CAPEX_well",
    "CAPEX_permitting",
    "CAPEX_exploration",
    "CAPEX_surface_pipes",
    "CAPEX_surface_plant",
    "CAPEX_total",
    "LCOE",
)


@dataclass
class EconomicParityCase:
    """One old-tango-vs-tango_next economic comparison — see module docstring."""

    old_yml: str
    """Filename relative to examples/ (old tango format)."""
    new_yml: str
    """Filename relative to examples/tango_next/."""
    old_vs_new_rtol: dict[str, float]
    """Per-field relative tolerance for the old-vs-new comparison."""
    golden: dict[str, float]
    """tango_next's own prior output, for the tight new-vs-golden regression check."""


ECONOMIC_PARITY_CASES: list[EconomicParityCase] = [
    EconomicParityCase(
        old_yml="flexible_SF_manual.yml",
        new_yml="hydro_sf_electric.yml",
        old_vs_new_rtol={
            "CAPEX_permitting": 1e-6,
            "CAPEX_exploration": 1e-6,
            "CAPEX_surface_pipes": 1e-6,
            "CAPEX_well": 1e-6,
            "CAPEX_surface_plant": 0.25,
            "CAPEX_total": 0.05,
            "LCOE": 0.08,
        },
        golden={
            "CAPEX_well": 36506133.65678038,
            "CAPEX_permitting": 1478867.3190221873,
            "CAPEX_exploration": 881721.0698689962,
            "CAPEX_surface_pipes": 961560.8286216573,
            "CAPEX_surface_plant": 6341613.475133107,
            "CAPEX_total": 46169896.34942632,
            "LCOE": 0.8240688318863874,
        },
    ),
    EconomicParityCase(
        old_yml="flexible_DF_manual.yml",
        new_yml="hydro_df_electric.yml",
        old_vs_new_rtol={
            "CAPEX_permitting": 1e-6,
            "CAPEX_exploration": 1e-6,
            "CAPEX_surface_pipes": 1e-6,
            "CAPEX_well": 1e-6,
            "CAPEX_surface_plant": 0.25,
            "CAPEX_total": 0.05,
            # 0.03 -> 0.05 (2026-08-14): NumericalProductionWellWithPump's pump
            # work moved from an isothermal CoolProp enthalpy-rise formula to
            # an isentropic-efficiency one (see that class's solve() docstring).
            # For a liquid, dH|_S = V*dP is genuinely larger than
            # dH|_T = [V - T*(dV/dT)_P]*dP -- the isothermal path is missing
            # the PV-work term a real, adiabatic pump stroke actually does on
            # the fluid. Confirmed by direct comparison this is what moved
            # the number (285,318 W isentropic vs. 185,975 W isothermal for
            # this config, evaluated on the SAME natural-march state -- the
            # OTHER part of this fix, re-marching with boosted density,
            # contributes under 0.1% on top). Old tango's own pump model is
            # ALSO isothermal, so this is tango_next deliberately diverging
            # from a known simplification in old tango's physics, not drift.
            "LCOE": 0.05,
        },
        golden={
            "CAPEX_well": 36506133.65678038,
            "CAPEX_permitting": 1478867.3190221873,
            "CAPEX_exploration": 881721.0698689962,
            "CAPEX_surface_pipes": 961560.8286216573,
            "CAPEX_surface_plant": 7810178.483363787,
            "CAPEX_total": 47638461.357657,
            "LCOE": 0.633224098583723,
        },
    ),
]


def _run_old_tango(old_yml: str) -> dict[str, float]:
    """Run old tango and return its economic results dict.

    Must read ``runner.tango.workflow.economic._results`` INSIDE the
    ``tempfile.TemporaryDirectory()`` block — unlike physics results
    (``workflow.results``), economic results live only on the ``.economic``
    unit instance, but old tango's ``Runner`` construction still needs a
    real (if temporary) save directory to run at all.
    """
    logging.disable(logging.WARNING)
    try:
        from tango.runner import Runner  # noqa: PLC0415
    finally:
        logging.disable(logging.NOTSET)

    with tempfile.TemporaryDirectory() as tmp:
        runner = Runner(str(EXAMPLES_OLD / old_yml), save_dir=tmp)
        runner.start()
        results = dict(runner.tango.workflow.economic._results)  # noqa: SLF001

    return {
        "CAPEX_well": results["CAPEX_well"],
        "CAPEX_permitting": results["CAPEX_permitting"],
        "CAPEX_exploration": results["CAPEX_exploration"],
        "CAPEX_surface_pipes": results["CAPEX_surface_gathering_system"],
        "CAPEX_surface_plant": results["CAPEX_surface_plant"],
        "CAPEX_total": results["CAPEX_total"],
        "LCOE": results["LCOE"],
    }


def _run_tango_next(new_yml: str) -> dict[str, float]:
    """Run tango_next and return its ``NativeEconomicComponent`` state as a plain dict."""
    from tango_next.workflows.workflow import Workflow  # noqa: PLC0415

    wf = Workflow.from_file(EXAMPLES_NEW / new_yml)
    wf.run()
    state: dict[str, Any] = wf.to_dict()["economic"]["state"]
    return {field: state[field] for field in _CAPEX_FIELDS}


@pytest.mark.parametrize("case", ECONOMIC_PARITY_CASES, ids=[c.old_yml for c in ECONOMIC_PARITY_CASES])
def test_old_new_economic_parity(case: EconomicParityCase) -> None:
    """Compare tango_next's NativeEconomicComponent against old tango's economic model."""
    old = _run_old_tango(case.old_yml)
    new = _run_tango_next(case.new_yml)

    for field, rtol in case.old_vs_new_rtol.items():
        assert new[field] == pytest.approx(old[field], rel=rtol), (
            f"{field} mismatch: old={old[field]!r}, new={new[field]!r}, rtol={rtol}"
        )


@pytest.mark.parametrize("case", ECONOMIC_PARITY_CASES, ids=[c.old_yml for c in ECONOMIC_PARITY_CASES])
def test_new_vs_golden_economic(case: EconomicParityCase) -> None:
    """Regression check: tango_next's own output vs. a committed snapshot (see module docstring)."""
    new = _run_tango_next(case.new_yml)

    for field, golden_value in case.golden.items():
        assert new[field] == pytest.approx(golden_value, rel=GOLDEN_RTOL), (
            f"{field} drifted from golden: golden={golden_value!r}, new={new[field]!r}. "
            "If this is an intentional change, update ECONOMIC_PARITY_CASES's golden dict "
            "in this file after reviewing the diff."
        )
