"""Regression tests for data leakage in unit specifications.

This module verifies that specifications intended for one unit type (e.g., surface)
do not incorrectly appear in the specifications of other unit types (e.g., common or well units).
This ensures that the `_process_specs` logic correctly filters and assigns parameters.
"""
from tango.runner import Runner


def test_data_leakage_in_common_specs():
    """Test to ensure that surface-specific parameters do not leak into common specs."""
    # Use an example file that is known to exist
    input_file = "examples/flexible_SF_manual.yml"

    # Initialize Tango workflow
    runner = Runner(input_file)
    runner.tango._initialize_workflow()

    # Access common specs
    common_specs = runner.tango.workflow.specs["common"]

    # Check for leakage
    # pipe_diameter is a surface spec, should not be in common
    assert "pipe_diameter" not in common_specs, "pipe_diameter incorrectly found in common specs"

    # epsilon is a surface spec (and others), should not be in common unless explicitly defined in CommonSpecs
    assert "epsilon" not in common_specs, "epsilon incorrectly found in common specs"

    # Check for presence of expected keys
    # surface_temperature IS in CommonSpecs, so it SHOULD be there
    assert "surface_temperature" in common_specs, "surface_temperature missing from common specs"
