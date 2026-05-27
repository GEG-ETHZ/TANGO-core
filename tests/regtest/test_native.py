"""Run TANGO tests with native TANGO components."""

# TODO: replace "unit" with "component" in most places.  In multi-physics
# modeling, "component" is more commonly used because "unit" often can be
# conflated with "units of measure"

import os
from pathlib import Path

import pandas as pd
import pytest

from tango.core.errors import (
    ComponentError,
    SubzeroPressureError,
    TESPyExcessSMolarError,
    ValidationError,
)
from tango.runner import Runner

EXAMPLES_DIR = Path(__file__).parents[2] / "examples"


# Test cases


def files_and_values() -> list[tuple[Path, float, float]]:
    """Return list of tuples of (path, reference_value, tolerance)"""
    # To enable tests gated by this boolean, run
    # `ENABLE_ALL_TESTS=true uv run pytest -v`
    enable_all_tests = os.environ.get("ENABLE_ALL_TESTS", "false").lower() == "true"

    filenames_and_vals = [
        ("testcase1.yml", 1.0476074181749977),
        ("testcase2.yml", 1.5316080111875296),
        ("testcase3.yml", 0.6920357140009343),
        ("testcase4.yml", 38.00773371474072),
        ("testcase5.yml", 6.2710133224835936),
        ("testcase6.yml", 65.30175787016593),
        ("testcase7.yml", 149.38633520084258),
        ("timestep_irregular.yml", 1.0476074181749977),
        ("timestep_linear.yml", 1.5316080111875296),
        ("timestep_linear_csv.yml", 0.6920357140009343),
        ("ORC_user_defined_cost.yml", 6.102323462825363),
        ("CPG_user_defined_cost.yml", 0.7098350204265998),
        ("ORC_multiple_5spot.yml", 32.58734200864573),
        ("ORC_num_pp.yml", 32.9153949938164),
        ("CPG_num_pp.yml", 0.78560019688079),
        ("flexible_CPG_manual.yml", 1.04167999932123),
        ("flexible_CPG_doublet.yml", 0.4400429200104828),
        ("flexible_CPG_inverted.yml", 0.8005693425320747),
        ("flexible_SF_manual.yml", 0.7740618821220107),
        ("flexible_SF_doublet.yml", 0.4925022354672546),
        ("flexible_SF_inverted.yml", 0.3981123953350526),
        ("flexible_DF_manual.yml", 0.6067863453819408),
        ("flexible_DF_doublet.yml", 0.4103679536682589),
        ("flexible_DF_inverted.yml", 0.3313490796606219),
        ("flexible_ORC_manual.yml", 0.5584699269163268),
        ("flexible_ORC_doublet.yml", 0.341555465917678),
        ("flexible_ORC_inverted.yml", 0.4347270222156839),
        ("flexible_pp_cost_entire.yml", 0.3889104022928901),
        ("flexible_pp_cost_breakdown.yml", 0.6035188654231337),
        ("testcase1_external.yml", 0.7578952498432321),
        ("testcase5_external.yml", 1.125718131336158),
        ("flexible_SF_cogeneration_e.yml", 0.4413798576886871),
        ("flexible_SF_cogeneration_h.yml", 0.0849757761111585),
        ("file_reader_CPG.yml", 0.5559391063230937),
        ("file_reader_ORC.yml", 0.3297975707323086),
        ("flexible_DF_reader.yml", 0.2278856925744952),
        ("flexible_CPG_hot.yml", 0.418689367029366),
        ("flexible_heat.yml", 0.0464719141105572),
        ("file_reader_kang.yml", 2.050293870015362),
        ("file_reader_kang2.yml", 0.8841888808490465),
        # Optimization tests (SO = Single Objective, MO = Multi Objective)
        ("SO1.yml", 0.799, 0.002) if enable_all_tests else None,
        ("SO2.yml", 0.799, 0.002) if enable_all_tests else None,
        ("SO3.yml", 0.799, 0.002) if enable_all_tests else None,
        ("SO4.yml", 0.798, 0.002) if enable_all_tests else None,
        ("SO5.yml", 0.615, 0.002) if enable_all_tests else None,
        ("SO6.yml", 0.870, 0.002) if enable_all_tests else None,
        ("SO7.yml", 0.813, 0.002) if enable_all_tests else None,
        ("MO1.yml", 0.806, 0.002) if enable_all_tests else None,
        ("MO2.yml", 0.814, 0.002) if enable_all_tests else None,
        ("MO3.yml", 0.797, 0.002) if enable_all_tests else None,
        # flexible_DF_opt_valves.yml is sufficiently similar that this can be skipped
        ("flexible_SF_opt_valve.yml", 0.6672682394033819, 0.001) if enable_all_tests else None,
        ("flexible_DF_opt_valves.yml", 0.5781967722329104, 0.002) if enable_all_tests else None,
        ("flexible_CPG_hot_opt.yml", 0.3874588709391597, 0.001) if enable_all_tests else None,
    ]

    result = []
    for fv in filenames_and_vals:
        if fv is None:
            continue
        filepath = Path(EXAMPLES_DIR) / fv[0]
        val = fv[1]
        tol = fv[2] if len(fv) > 2 else 1e-6  # default tolerance
        result.append((filepath, val, tol))
    return result


@pytest.mark.parametrize(
    "file_and_value",
    files_and_values(),
    ids=[fv[0].name for fv in files_and_values()],
)
def test_examples(file_and_value: tuple[Path, float, float], tmp_path: Path):
    """Test that examples produce expected LCOE value

    Arguments:
    file_and_value (tuple[Path, float, float]): path to example file, expected value, and tolerance
    tmp_path (Path): temporary directory created by pytest

    """
    input_file = file_and_value[0]
    value = file_and_value[1]
    tol = file_and_value[2]

    runner = Runner(input_file, save_dir=tmp_path)
    runner.start()
    econ_file = runner.tango.workflow.run_dir / (input_file.stem + ".econ.csv")
    df = pd.read_csv(econ_file)
    lcoe = df["LCOE"].iloc[0]

    # TODO: make sure that lcoe is the same in the file and the live runner
    assert lcoe == pytest.approx(value, abs=tol), f"LCOE calulated: {lcoe}, LCOE expected: {value}"


def files_and_err_types_failing() -> list[tuple[Path, type]]:
    """Return list paths to examples that should fail"""
    files_and_errors = [
        (
            "flexible_DF_manual_0p1_inj.yml",
            ComponentError,
        ),
        (
            "flexible_DF_manual_0p1_pro.yml",
            ComponentError,
        ),
        (
            "flexible_DF_manual_narrow_inj.yml",
            ComponentError,
        ),
        (
            "flexible_SF_manual_0p1_inj.yml",
            ComponentError,
        ),
        (
            "flexible_SF_manual_0p1_pro.yml",
            ComponentError,
        ),
        (
            "flexible_SF_manual_0p1_pump.yml",
            ComponentError,
        ),
        (
            "flexible_SF_manual_narrow_inj.yml",
            ComponentError,
        ),
        (
            "flexible_SF_manual_narrow_pro.yml",
            ComponentError,
        ),
        (
            "flexible_SF_manual_narrow_pump.yml",
            ComponentError,
        ),
        (
            "flexible_SF_manual_excess_mflow.yml",
            SubzeroPressureError,
        ),
        (
            "flexible_DF_manual_small_spacing.yml",
            TESPyExcessSMolarError,
        ),
        (
            "flexible_DF_manual_vlv2_p_out_high.yml",
            ValidationError,  # Transitive check: valve2.p_out > valve1.p_out is not allowed
        ),
        (
            "flexible_DF_manual_cond2_xgt0.yml",
            TESPyExcessSMolarError,  # vapor_mass_fraction_out=0.9 prevents condensation
        ),
    ]
    filepaths_and_err_types = [
        ((EXAMPLES_DIR / "failing" / fv[0]).resolve(), fv[1]) for fv in files_and_errors
    ]

    return filepaths_and_err_types


@pytest.mark.parametrize(
    "file_and_err_type_failing",
    files_and_err_types_failing(),
    ids=[fv[0].name for fv in files_and_err_types_failing()],
)
def test_failing_examples(file_and_err_type_failing: tuple[Path, type], tmp_path: Path):
    """Test that examples that should fail

    Arguments:
    file_and_err_type_failing(tuple[Path, Exception]): path to example file and expected error type
    tmp_path (Path): temporary directory created by pytest

    """
    input_file = file_and_err_type_failing[0]
    err_type = file_and_err_type_failing[1]

    try:
        runner = Runner(input_file, save_dir=tmp_path)
        runner.start()
        raise Exception("Should be unreachable")
    except Exception as err:
        assert isinstance(err, err_type), f"error raised: {type(err)}, error expected: {err_type}"


# NOTE: these were commented when Chad first started working on TANGO with no explanation
# def test_case17():
#     fname = os.path.join(examples_dir, 'SO1.yml')
#     run(fname)
#     assert get_lcoe_from_file(fname) == pytest.approx(0.799, abs=0.001)
#     rm_output_files(fname)

# def test_case18():
#     fname = os.path.join(examples_dir, 'SO2.yml')
#     run(fname)
#     assert get_lcoe_from_file(fname) == pytest.approx(0.799, abs=0.001)
#     rm_output_files(fname)

# def test_case19():
#     fname = os.path.join(examples_dir, 'SO3.yml')
#     run(fname)
#     assert get_lcoe_from_file(fname) == pytest.approx(0.799, abs=0.001)
#     rm_output_files(fname)

# def test_case20():
#     fname = os.path.join(examples_dir, 'SO4.yml')
#     run(fname)
#     assert get_lcoe_from_file(fname) == pytest.approx(0.796, abs=0.001)
#     rm_output_files(fname)

# def test_case21():
#     fname = os.path.join(examples_dir, 'SO5.yml')
#     run(fname)
#     assert get_lcoe_from_file(fname) == pytest.approx(0.615, abs=0.001)
#     rm_output_files(fname)

# def test_case22():
#     fname = os.path.join(examples_dir, 'SO6.yml')
#     run(fname)
#     assert get_lcoe_from_file(fname) == pytest.approx(0.867, abs=0.001)
#     rm_output_files(fname)

# def test_case23():
#     fname = os.path.join(examples_dir, 'SO7.yml')
#     run(fname)
#     assert get_lcoe_from_file(fname) == pytest.approx(0.811, abs=0.002)
#     rm_output_files(fname)

# def test_case24():
#     fname = os.path.join(examples_dir, 'SO8.yml')
#     run(fname)
#     assert get_lcoe_from_file(fname) == pytest.approx(0.561, abs=0.001)
#     rm_output_files(fname)

# def test_case25():
#     fname = os.path.join(examples_dir, 'MO1.yml')
#     run(fname)
#     assert get_lcoe_from_file(fname) == pytest.approx(0.804, abs=0.002)
#     rm_output_files(fname)

# def test_case26():
#     fname = os.path.join(examples_dir, 'MO2.yml')
#     run(fname)
#     assert get_lcoe_from_file(fname) == pytest.approx(0.814, abs=0.002)
#     rm_output_files(fname)

# def test_case27():
#     fname = os.path.join(examples_dir, 'MO3.yml')
#     run(fname)
#     assert get_lcoe_from_file(fname) == pytest.approx(0.797, abs=0.002)
#     rm_output_files(fname)

# def test_case49():
#     fname = os.path.join(examples_dir, 'flexible_SF_opt.yml')
#     run(fname)
#     assert get_lcoe_from_file(fname) == pytest.approx(0.6047041512786223, abs=0.001)
#     rm_output_files(fname)

# def test_case50():
#     fname = os.path.join(examples_dir, 'flexible_SF_opt_valve.yml')
#     run(fname)
#     assert get_lcoe_from_file(fname) == pytest.approx(0.6672682394033819, abs=0.001)
#     rm_output_files(fname)

# def test_case51():
#     fname = os.path.join(examples_dir, 'flexible_DF_opt_valves.yml')
#     run(fname)
#     assert get_lcoe_from_file(fname) == pytest.approx(0.5781967722329104, abs=0.002)
#     rm_output_files(fname)

# def test_case52():
#     fname = os.path.join(examples_dir, 'flexible_CPG_hot_opt.yml')
#     run(fname)
#     assert get_lcoe_from_file(fname) == pytest.approx(0.3874588709391597, abs=0.001)
#     rm_output_files(fname)
