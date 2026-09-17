"""Old-tango vs tango_next physical parity tests.

PURPOSE
-------
Verify that tango_next produces physically consistent per-timestep results
compared to the original src/tango/ implementation, within documented
tolerances that reflect known deliberate deviations.

This file runs TWO independent comparisons per case:

1. **old vs. new** (``ParityCase`` tolerances) — physical sanity check
   against ``src/tango/``. Tolerances are deliberately loose (see below)
   since exact agreement between two independent implementations is
   neither expected nor desired.
2. **new vs. golden** (tight, ``GOLDEN_RTOL``) — regression check against a
   committed snapshot of tango_next's own prior output
   (``golden_tango_next/<stem>.json``). This is the one that actually
   catches accidental tango_next regressions: a change could easily shift
   tango_next's numbers while staying inside the loose old-vs-new band
   (e.g. drifting from -0.05 K away from old-tango to +0.05 K, still well
   inside a 2 K tolerance) and comparison (1) alone would never notice.
   Regenerate the golden file with ``tools/update_tango_next_golden.py``
   only after confirming a change is an *intentional* physics change —
   review the JSON diff as you would review any other test-value change.

Known deliberate deviations (flexible_SF_manual baseline)
----------------------------------------------------------
Re-measured 2026-08-28 after fixing a real convergence-loop bug: within a
timestep's injection-temperature re-solve, ``LumpedReservoir.state`` used
to leak the PREVIOUS re-solve attempt's outlet into the next attempt's
"previous timestep" read (``restore_convergence_state()`` didn't restore
``state`` at all — see git history), contaminating
``energy_extracted``/``T_out_prev`` every inner iteration. Fixing it
changed real physics numbers — mostly at the steepest part of the
depletion transition (t~4-7 for this case) — moving tango_next FURTHER
from old tango on this specific case, not closer (old tango has no
equivalent inner re-solve loop to have the same bug in the first place, so
there was no reason to expect the fix to track it more closely). Was
≲1 K / ≲1 K / ≲5%; now:
- Reservoir T:   ≲ 5 K   — concentrated at 2 of 20 timesteps (t~4-5)
- Production T:  ≲ 4 K   — same transition, propagated downstream
- Gross power:   ≲ 6.5%  — driven by the production-T difference above

WHAT ACTUALLY CAUSES THIS GAP (proven exactly, 2026-08-29)
------------------------------------------------------------
Old tango's reservoir reads `self.outlet_fluid` (its own previous output)
to compute both impedance (pressure) and depletion coefficients
(temperature) — but within a timestep's Gauss-Seidel loop,
`process_stream()` reads that value *before* the same iteration's
`stream_interface()` overwrites it. Every iteration, including the
final/"converged" one, therefore computes its result from the *previous*
iteration's outlet, never from a true fixed point of its own formula.
Confirmed exactly (not approximately): feeding tango_next's standalone
`LumpedReservoir` old tango's actual previous-iteration `outlet_fluid`
state (from live instrumentation — one Gauss-Seidel iteration before old
tango's own final/committed iteration each timestep), together with that
same final iteration's `(T_inj, P_inj, mass_rate)`, reproduces old
tango's committed T_out AND P_out to displayed precision at all 8
timesteps:
```
 t      old_T_out       tn_T_out      diffT        old_P_out       tn_P_out      diffP
 1     463.000000     463.000000   0.000000     47969025.083   47969025.083      0.000
 4     461.888600     461.888600   0.000000     47960768.568   47960768.568      0.000
 6     424.074284     424.074284   0.000000     47814886.130   47814886.130     -0.000
 8     409.351072     409.351072   0.000000     47733781.525   47733781.525      0.000
```
This is complete and exact: the reservoir formulas themselves
(`_compute_depletion_curve_coeffs`/`_depletion_curve` in both
`src/tango/units/native/reservoir.py` and
`src/tango_next/components/reservoir/lumped.py`, plus the CoolProp
backend/call convention) are bit-identical between the two codebases —
confirmed directly, including a side-by-side CoolProp property
comparison at matched (P, T) returning zero difference to full float64
precision. Once fed the exact state old tango's own formula actually
used, there is nothing left to diverge. This is the entire gap; it is
NOT primarily the isothermal-pump issue documented in
`docs/bugs-fixed-in-tango-next.md` (initially suspected, but a direct
isolated test — monkeypatching tango_next's pump back to old tango's
isothermal formula and re-running end-to-end — found its effect on
reservoir temperature is real but ~2 orders of magnitude too small
(≲0.02 K) to explain this, and runs in the opposite direction from the
naive story: a warmer isentropic-pump outlet lets the surface plant
extract MORE energy, so the reinjection stream ends up colder, not
warmer). That bug's larger, genuine effect is on pump power / LCOE (see
that doc entry), not reservoir depletion.

WHY THE DIVERGENCE IS CONCENTRATED AT t~4-7 AND NOWHERE ELSE
--------------------------------------------------------------
``T_out = gamma(psi)*dT + T_inj``, where ``psi`` (cumulative fractional
energy extraction) is exactly the accumulator this staleness perturbs
every timestep, and ``gamma(psi)`` (``LumpedReservoir._depletion_curve``)
is a sigmoid: flat near 1.0 before depletion, a steep "breakthrough"
transition, then a flat lower plateau. Computing ``dgamma/dpsi`` directly
from tango_next's own reservoir at the actual ``psi`` this 8-timestep run
traces through:
```
 t      psi      gamma    dgamma/dpsi   diff(T_out, tango_next vs old tango)
 1    0.0366    1.0000      -0.0000        -0.000000
 2    0.0732    1.0000      -0.0001        -0.000000
 3    0.1097    0.9998      -0.0212        -0.000123
 4    0.1462    0.9899      -0.9233        -0.026586
 5    0.1837    0.8647      -6.4985        -1.558634
 6    0.2184    0.6019      -4.7430        -4.770431
 7    0.2416    0.5151      -1.8772        -3.551869
 8    0.2609    0.4882      -0.9485        -1.971310
```
``|dgamma/dpsi|`` is near-zero at t=1-2, peaks (~6.5, a
65,000x-larger sensitivity than at t=1-2) around t=5, then decays — the
same shape as the observed divergence, one step ahead of it (``psi`` at
timestep t sets T_out at t, so a sensitivity peak at t=5 shows up as
maximal divergence once compounded through one more step, at t=6). Away
from breakthrough, the one-iteration-stale ``outlet_fluid`` this bug
introduces every timestep gets multiplied by ~zero and is invisible;
during breakthrough, the identical per-timestep staleness gets
multiplied by a derivative orders of magnitude larger, purely from where
on the curve the run sits — not because the underlying staleness itself
grew. This staleness is present from the very first timestep's pressure
channel onward (a ~250 Pa impedance-driven seed at t=1, traced to a
~1 MPa gap between the reservoir's cold-start pressure and its own
first-Gauss-Seidel-iteration output — not any config or CoolProp
discrepancy), which is why the divergence is fully seeded well before it
becomes visible at the depletion curve's steep transition.

ADDING A NEW CASE
-----------------
1. Find the corresponding case in tests/regtest/test_native.py::test_examples.
2. Create examples/tango_next/<stem>.yml using
   examples/tango_next/hydro_sf_electric.yml as the template.
   Key structural changes from old → new format:
     - props: → common:
     - graph: nodes/edges → per-component component_idx/prev/next
     - schedule: → sim_config: + layout:
     - All component parameters live under components.<name>.*
     - power_plant_graph: → nested power_plant: block inside surface
     - epsilon: → pipe_roughness:
3. Change the ParityCase stub:
     - Set new_yml to the path (relative to examples/tango_next/)
     - Set the tolerance fields
     - Remove the ``implemented=False`` flag
4. Run ``uv run python tools/update_tango_next_golden.py`` to generate
   ``golden_tango_next/<stem>.json`` for the new case (the golden-comparison
   step fails loudly if this file is missing).
5. Run and verify the test passes.  Adjust tolerances if needed, but
   document WHY each tolerance is what it is.

TARGET CASES (all cases from test_native.py::test_examples)
-----------------------------------------------------------
Not every case is necessarily worth porting — some old-tango examples
contain known logic flaws or represent physics that tango_next hasn't
implemented yet.  Evaluate each one before investing in a new YAML.

Single-Flash (SF) — highest priority; shares the existing surface component:
  [x] flexible_SF_manual.yml        — DOUBLET, manual flow — working baseline
                                       (tango_next port: hydro_sf_electric.yml)
  [ ] flexible_SF_doublet.yml       — DOUBLET variant
  [ ] flexible_SF_inverted.yml      — inverted-5-spot layout
  [ ] flexible_SF_cogeneration_e.yml — SF + electrical cogeneration
  [ ] flexible_SF_cogeneration_h.yml — SF + heat cogeneration

Basic test cases (testcase1–5) — older, less documented; audit for logic
flaws before porting; some may not be worth it. testcase6.yml/testcase7.yml
removed 2026-08-05 (never actually time-marched in old tango; see
tests/regtest/test_native.py):
  [ ] testcase1.yml
  [ ] testcase2.yml
  [ ] testcase3.yml
  [ ] testcase4.yml
  [ ] testcase5.yml

Timestep scheduling variants — same physics as testcase1–3, different dt:
  [ ] timestep_irregular.yml        — may not be worth a separate port
  [ ] timestep_linear.yml
  [ ] timestep_linear_csv.yml

Double-Flash (DF) — requires a DoubleFlash surface component in tango_next:
  [ ] flexible_DF_manual.yml
  [ ] flexible_DF_doublet.yml
  [ ] flexible_DF_inverted.yml
  [ ] flexible_DF_reader.yml        — reads mass-flow schedule from file

ORC — requires an ORC surface component in tango_next:
  [ ] flexible_ORC_manual.yml
  [ ] flexible_ORC_doublet.yml
  [ ] flexible_ORC_inverted.yml
  [ ] ORC_user_defined_cost.yml
  [ ] ORC_multiple_5spot.yml
  [ ] ORC_num_pp.yml
  [ ] file_reader_ORC.yml

CPG (CO₂ Plume Geothermal) — requires CPG fluid/component support:
  [ ] flexible_CPG_manual.yml
  [ ] flexible_CPG_doublet.yml
  [ ] flexible_CPG_inverted.yml
  [ ] flexible_CPG_hot.yml
  [ ] CPG_user_defined_cost.yml
  [ ] CPG_num_pp.yml
  [ ] file_reader_CPG.yml
  [ ] file_reader_kang.yml
  [ ] file_reader_kang2.yml

Direct heat / cost variants — may need separate surface component or economic model:
  [ ] flexible_heat.yml
  [ ] flexible_pp_cost_entire.yml
  [ ] flexible_pp_cost_breakdown.yml

External simulator interface — requires CMG/DWSIM/MOOSE integration:
  [ ] testcase1_external.yml        — probably not worth porting until external
  [ ] testcase5_external.yml          interface is redesigned in tango_next
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

EXAMPLES_OLD = Path(__file__).parents[2] / "examples"
EXAMPLES_NEW = EXAMPLES_OLD / "tango_next"
GOLDEN_DIR = Path(__file__).parent / "golden_tango_next"
"""Committed known-good tango_next snapshots, keyed by ``<stem>.json`` —
see ``tools/update_tango_next_golden.py`` and the module docstring's
"new vs. golden" comparison for why this exists alongside old-vs-new."""
GOLDEN_RTOL = 50e-6
"""This comparison exists to catch unintended numeric drift in tango_next
itself, not to allow known-deliberate deviation like the old-vs-new
tolerances above do. Was 1e-9 (bit-exact) until GraphSurface's TESPy
connections switched to the BICUBIC-tabulated HEOS CoolProp backend (see
COOLPROP_BACKEND in fluid_state.py) for a ~2x wall-clock speedup on any run
touching the power plant -- that backend builds its interpolation tables
adaptively around whatever P/T range a solve happens to hit, so identical
code run in two separate processes can land on visibly different (though
physically insignificant) answers. 50e-6 covers the observed jitter (up to
~3.2e-5 relative, in the economic parity golden check) with margin, without
hiding a real regression."""


# ---------------------------------------------------------------------------
# Case registry
# ---------------------------------------------------------------------------


@dataclass
class ParityCase:
    """Describes one old-vs-new parity comparison.

    Set ``new_yml=None`` to mark the case as a stub — the test will call
    ``pytest.xfail()`` and show as ``xfailed``, so it doesn't block CI
    while signalling that a new YAML file needs to be created.

    Tolerances are per-variable, applied to the full per-timestep history
    array via ``numpy.testing.assert_allclose``.
    """

    old_yml: str
    """Filename relative to examples/ (old tango format)."""
    new_yml: str | None
    """Filename relative to examples/tango_next/ — None = stub, not yet ported."""
    res_T_atol: float = 0.0  # noqa: N815
    """Absolute tolerance (K) on reservoir outlet temperature history."""
    prod_T_atol: float = 0.0  # noqa: N815
    """Absolute tolerance (K) on production well outlet temperature history."""
    power_rtol: float = 0.0
    """Relative tolerance on gross power history."""
    notes: str = ""
    """Human-readable notes on why tolerances are set as they are."""


PARITY_CASES: list[ParityCase] = [
    # ------------------------------------------------------------------
    # IMPLEMENTED
    # ------------------------------------------------------------------
    ParityCase(
        old_yml="flexible_SF_manual.yml",
        new_yml="hydro_sf_electric.yml",
        res_T_atol=6.0,  # measured max deviation ≲ 4.89 K (2026-08-28); headroom over that
        prod_T_atol=5.0,  # measured max deviation ≲ 3.98 K (2026-08-28)
        power_rtol=0.08,  # measured max deviation ≲ 6.45% (2026-08-28)
        notes=(
            "DOUBLET layout, manual mass flow, single-flash surface. "
            "tango_next's reservoir fully participates in T-convergence "
            "(no freezing/refreezing) and uses the same doublet-impedance and "
            "Adams 2015 depletion-curve formulas as old tango, including the "
            "same initial/undepleted reservoir pressure formula "
            "(brine_density * g * depth). "
            "Re-measured 2026-08-28 (was ≲0.20 K/≲0.18 K/≲0.34%): fixing a "
            "real convergence-loop bug (LumpedReservoir.state wasn't "
            "restored across a within-timestep re-solve, contaminating "
            "energy_extracted/T_out_prev with the previous re-solve "
            "attempt's output instead of the last converged timestep's — "
            "see module docstring) changed real physics numbers. The "
            "remaining delta is concentrated at the steepest part of the "
            "depletion transition (t~4-5 for this case, 2/20 timesteps) — "
            "it settles back to <0.01 K agreement once past the transition "
            "(see docs/TANGO_vision_and_roadmap.md for detail)."
        ),
    ),
    ParityCase(
        old_yml="flexible_ORC_manual.yml",
        new_yml="hydro_orc_electric.yml",
        res_T_atol=4.0,  # measured max deviation ≲ 3.83 K (2026-09-17)
        prod_T_atol=3.0,  # measured max deviation ≲ 2.57 K (2026-09-17)
        power_rtol=0.06,  # measured max deviation ≲ 4.78% (2026-09-17)
        notes=(
            "DOUBLET layout, manual mass flow, binary (ORC) surface plant. "
            "Subsurface identical to the SF/DF cases (same site numbers) — "
            "only the surface plant differs: a two-stage HeatExchanger boiler/"
            "preheater transferring heat from the geofluid loop to a separate "
            "closed R245fa secondary loop (turbine/cooler/condenser/pump, "
            "closed via a CycleCloser node), never mixing with the geofluid. "
            "hydro_orc_electric.yml runs injection_mode: manual, not "
            "manual-fracking-check like the SF/DF cases: at these inputs "
            "old tango's injection well outlet sits at 54.48 MPa (just under "
            "the 55 MPa fracking-safety threshold) while tango_next's "
            "numerical wellbore model puts the same inputs at ~55.44-55.97 MPa "
            "(just over it) — the same well-model deviation class measured "
            "here for T/power, but happening to straddle this site's tight "
            "safety margin; manual-fracking-check has no self-correction by "
            "design (see SystemBCIteration's module docstring) so it would "
            "hard-fail on a difference of the same size the other tolerances "
            "here already accept."
        ),
    ),
    # ------------------------------------------------------------------
    # STUBS — new YAML files need to be created (see ADDING A NEW CASE)
    # Evaluate each case before investing in a port — some old-tango
    # examples have known logic flaws or represent unimplemented physics.
    # ------------------------------------------------------------------
    # Single-Flash variants (same surface component, highest priority)
    ParityCase(old_yml="flexible_SF_doublet.yml", new_yml=None),
    ParityCase(old_yml="flexible_SF_inverted.yml", new_yml=None),
    ParityCase(old_yml="flexible_SF_cogeneration_e.yml", new_yml=None),
    ParityCase(old_yml="flexible_SF_cogeneration_h.yml", new_yml=None),
    # Basic test cases — audit for logic flaws before porting
    ParityCase(old_yml="testcase1.yml", new_yml=None),
    ParityCase(old_yml="testcase2.yml", new_yml=None),
    ParityCase(old_yml="testcase3.yml", new_yml=None),
    ParityCase(old_yml="testcase4.yml", new_yml=None),
    ParityCase(old_yml="testcase5.yml", new_yml=None),
    # testcase6.yml, testcase7.yml removed (2026-08-05): AGS configs that old
    # tango never actually time-marches (see tests/regtest/test_native.py's
    # comment at the same date). Equivalent tango_next coverage tracked as
    # the CO2-AGS/AGS-power cells in docs/TANGO_vision_and_roadmap.md's
    # example coverage matrix instead.
    # Timestep scheduling variants — same physics as testcase1-3, different dt
    ParityCase(old_yml="timestep_irregular.yml", new_yml=None),
    ParityCase(old_yml="timestep_linear.yml", new_yml=None),
    ParityCase(old_yml="timestep_linear_csv.yml", new_yml=None),
    # Double-Flash — requires DoubleFlash surface component in tango_next
    ParityCase(old_yml="flexible_DF_manual.yml", new_yml=None),
    ParityCase(old_yml="flexible_DF_doublet.yml", new_yml=None),
    ParityCase(old_yml="flexible_DF_inverted.yml", new_yml=None),
    ParityCase(old_yml="flexible_DF_reader.yml", new_yml=None),
    # ORC — flexible_ORC_manual.yml is now IMPLEMENTED (see above); the rest
    # are still stubs (doublet/inverted layouts, custom-cost variants, etc.)
    ParityCase(old_yml="flexible_ORC_doublet.yml", new_yml=None),
    ParityCase(old_yml="flexible_ORC_inverted.yml", new_yml=None),
    ParityCase(old_yml="ORC_user_defined_cost.yml", new_yml=None),
    ParityCase(old_yml="ORC_multiple_5spot.yml", new_yml=None),
    ParityCase(old_yml="ORC_num_pp.yml", new_yml=None),
    ParityCase(old_yml="file_reader_ORC.yml", new_yml=None),
    # CPG — requires CPG fluid/component support in tango_next
    ParityCase(old_yml="flexible_CPG_manual.yml", new_yml=None),
    ParityCase(old_yml="flexible_CPG_doublet.yml", new_yml=None),
    ParityCase(old_yml="flexible_CPG_inverted.yml", new_yml=None),
    ParityCase(old_yml="flexible_CPG_hot.yml", new_yml=None),
    ParityCase(old_yml="CPG_user_defined_cost.yml", new_yml=None),
    ParityCase(old_yml="CPG_num_pp.yml", new_yml=None),
    ParityCase(old_yml="file_reader_CPG.yml", new_yml=None),
    ParityCase(old_yml="file_reader_kang.yml", new_yml=None),
    ParityCase(old_yml="file_reader_kang2.yml", new_yml=None),
    # Direct heat / cost variants
    ParityCase(old_yml="flexible_heat.yml", new_yml=None),
    ParityCase(old_yml="flexible_pp_cost_entire.yml", new_yml=None),
    ParityCase(old_yml="flexible_pp_cost_breakdown.yml", new_yml=None),
    # External simulator interface — probably not worth porting until
    # the external interface is redesigned in tango_next
    ParityCase(old_yml="testcase1_external.yml", new_yml=None),
    ParityCase(old_yml="testcase5_external.yml", new_yml=None),
]


# ---------------------------------------------------------------------------
# Helpers: run each system and extract comparable history
# ---------------------------------------------------------------------------


def _run_old_tango(yml_path: Path, num_tsteps: int | None = None) -> dict[str, Any]:
    """Run old tango and return per-timestep history arrays.

    Returns a dict with keys:
      res_T_out    list[float]  reservoir outlet temperature (K) per timestep
      prod_T_out   list[float]  production well upper outlet T (K) per timestep
      gross_W      list[float]  gross power (W) per timestep

    Uses ``workflow.results``, which is a flat dict of per-timestep lists
    keyed as ``<component>_<quantity>``.  Temperatures are in °C in old tango
    results — converted to K here.  Power is in W (``turbine_power_real``).

    ``num_tsteps``, if given, overrides ``schedule.time.num_tsteps`` via
    ``Runner``'s own ``parameter_overrides`` mechanism (dot-path
    ``"section.parameter=value"`` strings) — used by the FAST parity case
    below, without touching the YAML file on disk.
    """
    import tempfile  # noqa: PLC0415

    logging.disable(logging.WARNING)
    try:
        from tango.runner import Runner  # noqa: PLC0415
    finally:
        logging.disable(logging.NOTSET)

    overrides = [f"schedule.time.num_tsteps={num_tsteps}"] if num_tsteps is not None else None
    with tempfile.TemporaryDirectory() as tmp:
        runner = Runner(yml_path, save_dir=tmp, parameter_overrides=overrides)
        runner.start()

    results = runner.tango.workflow.results
    # workflow.results stores temperatures in K (despite °C in printed tables)
    return {
        "res_T_out": list(results["reservoir_T"]),
        "prod_T_out": list(results["production_well_pump_T"]),
        "gross_W": list(results["turbine_power_real"]),
    }


def _run_tango_next(yml_path: Path, num_tsteps: int | None = None) -> dict[str, Any]:
    """Run tango_next and return per-timestep history arrays.

    Returns the same key layout as ``_run_old_tango``. ``num_tsteps``, if
    given, overrides ``sim_config.num_tsteps`` without touching the YAML
    file on disk.
    """
    import yaml  # noqa: PLC0415

    from tango_next.workflows.workflow import Workflow  # noqa: PLC0415

    if num_tsteps is None:
        wf = Workflow.from_file(yml_path)
    else:
        cfg = yaml.safe_load(Path(yml_path).read_text())
        cfg["sim_config"]["num_tsteps"] = num_tsteps
        wf = Workflow(cfg)
    wf.run()
    c = wf._orchestrator.components
    surface = c["surface"]
    prod_upper = c["production_well_upper"]
    res = c["reservoir"]
    # Old tango's "turbine_power_real" is gross turbine power only (-P.val,
    # no pump/pump2 parasitic subtraction) — GraphSurface.state.net_power_W
    # is the *net* total across every role=net_electric node, so for an
    # apples-to-apples gross comparison read the turbine's own raw P.val out
    # of the generic per-node history instead (node_detail stores TESPy's
    # raw sign convention: negative P.val = production).
    turbine_P = surface.history.node_history["turbine"]["P"]
    return {
        "res_T_out": list(res.history.T_outlet),
        "prod_T_out": list(prod_upper.history.T_outlet),
        "gross_W": [-p for p in turbine_P],
    }


def _load_golden(new_yml: str) -> dict[str, list[float]]:
    """Load the committed golden snapshot for a tango_next case.

    Raises with a message pointing at the update script rather than
    silently skipping — a missing golden file means the regression check
    isn't actually running, which should fail loudly, not quietly pass.
    """
    path = GOLDEN_DIR / f"{Path(new_yml).stem}.json"
    if not path.exists():
        pytest.fail(
            f"No golden file at {path}. Run "
            "`uv run python tools/update_tango_next_golden.py` to generate it "
            "(after confirming any resulting diff is an intentional change).",
        )
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Parametrized test
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize(
    "case",
    PARITY_CASES,
    ids=[c.old_yml for c in PARITY_CASES],
)
def test_old_new_parity(case: ParityCase) -> None:
    """Compare per-timestep physical history between old tango and tango_next.

    For stub cases (new_yml=None) this calls ``pytest.xfail()`` — create
    the tango_next YAML and fill in the ParityCase to activate the test.

    Full-length (20-timestep) run — see ``test_old_new_parity_fast`` below
    for the 8-timestep companion that actually runs by default (deselected
    via ``-m "not slow"``, see pytest.ini).
    """
    if case.new_yml is None:
        pytest.xfail(
            f"tango_next YAML for '{case.old_yml}' has not been created yet. "
            "See the ADDING A NEW CASE instructions at the top of this file.",
        )

    old = _run_old_tango(EXAMPLES_OLD / case.old_yml)
    new = _run_tango_next(EXAMPLES_NEW / case.new_yml)

    n = len(old["res_T_out"])
    assert len(new["res_T_out"]) == n, f"Timestep count mismatch: old={n}, new={len(new['res_T_out'])}"

    np.testing.assert_allclose(
        new["res_T_out"],
        old["res_T_out"],
        atol=case.res_T_atol,
        rtol=0,
        err_msg=f"Reservoir outlet T mismatch ({case.notes})",
    )
    np.testing.assert_allclose(
        new["prod_T_out"],
        old["prod_T_out"],
        atol=case.prod_T_atol,
        rtol=0,
        err_msg=f"Production well outlet T mismatch ({case.notes})",
    )
    np.testing.assert_allclose(
        new["gross_W"],
        old["gross_W"],
        atol=0,
        rtol=case.power_rtol,
        err_msg=f"Gross power mismatch ({case.notes})",
    )

    # Regression check: tango_next vs. its own last-known-good snapshot, at
    # much tighter tolerance than the old-vs-new comparisons above — see the
    # module docstring's "new vs. golden" section for why this is necessary.
    golden = _load_golden(case.new_yml)
    for key in ("res_T_out", "prod_T_out", "gross_W"):
        np.testing.assert_allclose(
            new[key],
            golden[key],
            rtol=GOLDEN_RTOL,
            atol=0,
            err_msg=(
                f"tango_next '{key}' drifted from its golden snapshot ({case.notes}). "
                "If this drift is intentional, review the diff and regenerate with "
                "tools/update_tango_next_golden.py."
            ),
        )


N_TSTEPS_FAST = 8
"""See test_tango_next.py's N_TSTEPS_FAST docstring for the general
rationale. Specific to THIS case: the SF case's documented worst-deviation
region is "the steepest part of the depletion transition (t~4-5)" — 8
timesteps fully captures that region, so the fast case below measures
essentially the SAME max deviations as the full 20-timestep run (confirmed
empirically, 2026-08-28: res_T 4.890 K vs 4.890 K, prod_T 3.985 K vs
3.985 K, power 6.45% vs 6.45%) — hence reusing the exact same tolerances,
not looser ones."""


def test_old_new_parity_fast() -> None:
    """8-timestep companion to ``test_old_new_parity`` — runs by default.

    Only covers the SF case (the one real implemented ``ParityCase`` today;
    the rest are stubs) since that's the only one with anything to check.
    Tolerances are the SAME as the slow (20-timestep) version's SF case —
    see ``N_TSTEPS_FAST``'s docstring for why that's correct here, not an
    oversight.
    """
    old = _run_old_tango(EXAMPLES_OLD / "flexible_SF_manual.yml", num_tsteps=N_TSTEPS_FAST)
    new = _run_tango_next(EXAMPLES_NEW / "hydro_sf_electric.yml", num_tsteps=N_TSTEPS_FAST)

    n = len(old["res_T_out"])
    assert len(new["res_T_out"]) == n == N_TSTEPS_FAST

    np.testing.assert_allclose(
        new["res_T_out"],
        old["res_T_out"],
        atol=6.0,
        rtol=0,
        err_msg="Reservoir outlet T mismatch (fast/8yr SF)",
    )
    np.testing.assert_allclose(
        new["prod_T_out"],
        old["prod_T_out"],
        atol=5.0,
        rtol=0,
        err_msg="Production well outlet T mismatch (fast/8yr SF)",
    )
    np.testing.assert_allclose(
        new["gross_W"],
        old["gross_W"],
        atol=0,
        rtol=0.08,
        err_msg="Gross power mismatch (fast/8yr SF)",
    )

    golden = _load_golden("hydro_sf_electric_8yr")  # stem-only; no such YAML file, just the golden JSON key
    for key in ("res_T_out", "prod_T_out", "gross_W"):
        np.testing.assert_allclose(
            new[key],
            golden[key],
            rtol=GOLDEN_RTOL,
            atol=0,
            err_msg=(
                f"tango_next '{key}' drifted from its golden snapshot (fast/8yr SF). "
                "If this drift is intentional, regenerate golden_tango_next/hydro_sf_electric_8yr.json."
            ),
        )
