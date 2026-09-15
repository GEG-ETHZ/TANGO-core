"""Old-tango vs tango_next economic (CAPEX/LCOE) parity test.

Companion to ``test_old_new_parity.py`` (physics), scoped to
``DoubletEconomicComponent`` (``src/tango_next/components/economic/doublet.py``)
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
  (see ``docs/bugs-fixed-in-tango-next.md``'s "DoubletEconomicComponent double-counted
  well mobilization cost across split physics sub-components" entry):
  tango_next originally combined every production-side ``WellComponent``
  by summing each one's INDEPENDENTLY-costed gengeo formula (double/
  triple-counting the formula's fixed `+275300` mobilization term once
  per physics sub-component), instead of combining their lengths into ONE
  total depth and costing that once — the same way old tango's own
  ``production_well.well_length_seq: [5000.]`` (4000 m + 1000 m combined)
  already does it correctly. Fixed in ``DoubletEconomicComponent._compute_well_capex``/
  ``_combined_production_length_and_diameter``.
- **CAPEX_surface_plant / CAPEX_total: close but not exact** (SF: -6.2%/
  -0.9%; DF: -5.1%/-0.9%) — both read RUN-AVERAGED power (mean over
  ``history``, matching old tango's own
  ``create_power_plant_with_averaged_results`` design — see
  ``DoubletEconomicComponent``'s module docstring), so the residual gap
  tracks ordinary old-vs-new physics-trajectory drift over the run, not a
  formula error. Tolerances (0.25 / 0.05) keep generous headroom above
  the measured values rather than being tightened to force agreement.
- **LCOE: closed from +16.1%/+11.5% down to -1.1%/-1.0% (2026-08-10), then
  deliberately reopened to a still-small residual gap (2026-08-14).** The
  original gap's culprit was ``NumericalProductionWellWithPump``'s
  pump-power formula, which used a naive ``mass_rate * ΔP / ρ`` hydraulic
  estimate. Verified against a live old-tango run (``BC_calculator.py``'s
  inline ``-(inlet.H - outlet.H) * mass_rate``, no efficiency term) that
  this overstates old tango's own (isothermal) CoolProp enthalpy rise by
  ~53% at typical wellhead conditions (~400 K). First fix (2026-08-10):
  switch to the SAME isothermal-enthalpy-rise formula old tango uses,
  which closed nearly the entire LCOE gap and confirmed the diagnosis.
  Second fix (2026-08-14, a deliberate divergence from old tango, not a
  bug in the port): old tango's isothermal pump model is itself physically
  wrong — a real pump's inefficiency shows up as heat, not just pressure,
  and holding temperature fixed silently discards that heat (see
  ``docs/bugs-fixed-in-tango-next.md``'s "Old tango's downhole production
  pump is modeled as perfectly isothermal" entry). Switched to a standard
  isentropic-efficiency model (entropy at the true inlet state, isentropic
  enthalpy at the candidate discharge pressure, efficiency-derated, then
  flashed back to a real outlet temperature — see
  ``NumericalProductionWellWithPump.solve()``'s docstring for the full
  derivation). Quantified directly on this DF config's natural-march
  state: 285,318 W isentropic vs. 185,975 W isothermal — a ~53% pump-work
  difference, matching the earlier CoolProp-derivation estimate almost
  exactly. ``pump_efficiency`` defaults to 1.0 (no derating yet) —
  planned to drop to ~0.9 later once a real figure is settled on,
  deliberately deferred.
- **Re-measured 2026-08-28, LCOE now SF +8.1%, DF +5.9%** (rtol 0.08→0.10,
  0.05→0.075) — CAPEX didn't move (CAPEX_total drift is still <1%; the
  ``old_vs_new_rtol`` values above for CAPEX fields are unchanged and
  still hold with headroom). The LCOE gap widened because a real
  convergence-loop bug got fixed in the shared physics engine
  (``LumpedReservoir.state`` wasn't restored across a within-timestep
  re-solve — see ``test_old_new_parity.py``'s module docstring for the
  full mechanism), which changed the reservoir's late-run temperature
  trajectory and, through it, the run-averaged power LCOE's denominator
  depends on. Not a change to any economics formula.
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
            # 0.08 -> 0.10 (2026-08-28): re-measured at 8.08% after fixing a
            # convergence-loop bug in the shared physics engine (see module
            # docstring's LCOE rationale) -- CAPEX itself didn't move.
            "LCOE": 0.10,
        },
        # CAPEX_surface_plant/CAPEX_total/LCOE re-measured (2026-09-15) -- FluidState
        # switched to the BICUBIC-tabulated HEOS backend for speed; interpolation
        # error is ~1e-5 relative, below any physical significance.
        # Re-measured again (2026-09-15): NumericalWell now marches num_cells
        # cells bounded by num_cells + 1 nodes, spanning the well's full
        # declared length -- see that class's module docstring.
        golden={
            "CAPEX_well": 36506133.65678038,
            "CAPEX_permitting": 1478867.3190221873,
            "CAPEX_exploration": 881721.0698689962,
            "CAPEX_surface_pipes": 961560.8286216573,
            "CAPEX_surface_plant": 6356374.5480408855,
            "CAPEX_total": 46184657.422334105,
            "LCOE": 0.8202924495751981,
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
            # 0.05 -> 0.075 (2026-08-28): re-measured at 5.95% after fixing a
            # convergence-loop bug in the shared physics engine (see module
            # docstring's LCOE rationale) -- CAPEX itself didn't move.
            "LCOE": 0.075,
        },
        # CAPEX_surface_plant/CAPEX_total/LCOE re-measured (2026-09-04) --
        # same NumericalWell._compute_derived T_r fix as the SF case above.
        # Re-measured again (2026-09-15): FluidState switched to the
        # BICUBIC-tabulated HEOS backend for speed; interpolation error is
        # ~1e-5 relative, below any physical significance.
        # Re-measured again (2026-09-15): NumericalWell now marches num_cells
        # cells bounded by num_cells + 1 nodes, spanning the well's full
        # declared length -- see that class's module docstring.
        golden={
            "CAPEX_well": 36506133.65678038,
            "CAPEX_permitting": 1478867.3190221873,
            "CAPEX_exploration": 881721.0698689962,
            "CAPEX_surface_pipes": 961560.8286216573,
            "CAPEX_surface_plant": 7827397.221719528,
            "CAPEX_total": 47655680.09601274,
            "LCOE": 0.6303952942501404,
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
    """Run tango_next and return its ``DoubletEconomicComponent`` state as a plain dict."""
    from tango_next.workflows.workflow import Workflow  # noqa: PLC0415

    wf = Workflow.from_file(EXAMPLES_NEW / new_yml)
    wf.run()
    state: dict[str, Any] = wf.to_dict()["economic"]["state"]
    return {field: state[field] for field in _CAPEX_FIELDS}


@pytest.mark.parametrize("case", ECONOMIC_PARITY_CASES, ids=[c.old_yml for c in ECONOMIC_PARITY_CASES])
def test_old_new_economic_parity(case: EconomicParityCase) -> None:
    """Compare tango_next's DoubletEconomicComponent against old tango's economic model."""
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
