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
- Reservoir T:   ≲ 1 K   — minor integration differences; negligible
- Production T:  ≲ 1 K   — minor integration differences; negligible
- Gross power:   ≲ 5%    — driven by the production-T difference above

ADDING A NEW CASE
-----------------
1. Find the corresponding case in tests/regtest/test_native.py::test_examples.
2. Create examples/tango_next/<stem>.yml using
   examples/tango_next/flexible_SF_manual.yml as the template.
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
  [ ] flexible_SF_doublet.yml       — DOUBLET variant
  [ ] flexible_SF_inverted.yml      — inverted-5-spot layout
  [ ] flexible_SF_cogeneration_e.yml — SF + electrical cogeneration
  [ ] flexible_SF_cogeneration_h.yml — SF + heat cogeneration

Basic test cases (testcase1–7) — older, less documented; audit for logic
flaws before porting; some may not be worth it:
  [ ] testcase1.yml
  [ ] testcase2.yml
  [ ] testcase3.yml
  [ ] testcase4.yml
  [ ] testcase5.yml
  [ ] testcase6.yml
  [ ] testcase7.yml

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
GOLDEN_RTOL = 1e-9
"""Tight — this comparison exists to catch ANY unintended numeric drift in
tango_next itself, not to allow known-deliberate deviation like the
old-vs-new tolerances above do."""


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
        new_yml="flexible_SF_manual.yml",
        res_T_atol=2.0,  # measured max deviation ≲ 0.20 K; 2 K headroom catches regressions
        prod_T_atol=3.0,  # measured max deviation ≲ 0.18 K
        power_rtol=0.08,  # measured max deviation ≲ 0.34%
        notes=(
            "DOUBLET layout, manual mass flow, single-flash surface. "
            "tango_next's reservoir fully participates in T-convergence "
            "(no freezing/refreezing) and uses the same doublet-impedance and "
            "Adams 2015 depletion-curve formulas as old tango, including the "
            "same initial/undepleted reservoir pressure formula "
            "(brine_density * g * depth). The remaining small delta is "
            "concentrated at the steepest part of the depletion transition "
            "(t~5-7 for this case), where the shared nonlinear curve "
            "amplifies minor floating-point-level differences elsewhere "
            "(wellbore integration) — it settles back to <0.01 K agreement "
            "once past the transition (see docs/TANGO_vision_and_roadmap.md "
            "for detail)."
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
    ParityCase(old_yml="testcase6.yml", new_yml=None),
    ParityCase(old_yml="testcase7.yml", new_yml=None),
    # Timestep scheduling variants — same physics as testcase1-3, different dt
    ParityCase(old_yml="timestep_irregular.yml", new_yml=None),
    ParityCase(old_yml="timestep_linear.yml", new_yml=None),
    ParityCase(old_yml="timestep_linear_csv.yml", new_yml=None),
    # Double-Flash — requires DoubleFlash surface component in tango_next
    ParityCase(old_yml="flexible_DF_manual.yml", new_yml=None),
    ParityCase(old_yml="flexible_DF_doublet.yml", new_yml=None),
    ParityCase(old_yml="flexible_DF_inverted.yml", new_yml=None),
    ParityCase(old_yml="flexible_DF_reader.yml", new_yml=None),
    # ORC — requires ORC surface component in tango_next
    ParityCase(old_yml="flexible_ORC_manual.yml", new_yml=None),
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


def _run_old_tango(yml_path: Path) -> dict[str, Any]:
    """Run old tango and return per-timestep history arrays.

    Returns a dict with keys:
      res_T_out    list[float]  reservoir outlet temperature (K) per timestep
      prod_T_out   list[float]  production well upper outlet T (K) per timestep
      gross_W      list[float]  gross power (W) per timestep

    Uses ``workflow.results``, which is a flat dict of per-timestep lists
    keyed as ``<component>_<quantity>``.  Temperatures are in °C in old tango
    results — converted to K here.  Power is in W (``turbine_power_real``).
    """
    import tempfile  # noqa: PLC0415

    logging.disable(logging.WARNING)
    try:
        from tango.runner import Runner  # noqa: PLC0415
    finally:
        logging.disable(logging.NOTSET)

    with tempfile.TemporaryDirectory() as tmp:
        runner = Runner(yml_path, save_dir=tmp)
        runner.start()

    results = runner.tango.workflow.results
    # workflow.results stores temperatures in K (despite °C in printed tables)
    return {
        "res_T_out": list(results["reservoir_T"]),
        "prod_T_out": list(results["production_well_pump_T"]),
        "gross_W": list(results["turbine_power_real"]),
    }


def _run_tango_next(yml_path: Path) -> dict[str, Any]:
    """Run tango_next and return per-timestep history arrays.

    Returns the same key layout as ``_run_old_tango``.
    """
    from tango_next.workflows.workflow import Workflow  # noqa: PLC0415

    wf = Workflow.from_file(yml_path)
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


@pytest.mark.parametrize(
    "case",
    PARITY_CASES,
    ids=[c.old_yml for c in PARITY_CASES],
)
def test_old_new_parity(case: ParityCase) -> None:
    """Compare per-timestep physical history between old tango and tango_next.

    For stub cases (new_yml=None) this calls ``pytest.xfail()`` — create
    the tango_next YAML and fill in the ParityCase to activate the test.
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
