"""``surface_temperature``/``surface_pressure`` must come from ``common:`` only.

Historically the .yaml input file could set ``surface_temperature`` and
``surface_pressure`` both in ``common:`` and in ``components: surface:``, and
when the two disagreed, the surface component silently used its own
block's value while every other component (wells, reservoir) used
``common:``'s value — see ``tests/TemperaturePressureDiscrepancy.md``.

``GraphSurface`` (like every well and the reservoir) no longer declares
``surface_temperature``/``surface_pressure`` as its own fields at all — only
a shared ``common`` reference (see ``core/specs.py``'s ``Common``). So
``examples/tango_next/SF_manual_differing_st.yml`` still declaring them in
``components.surface`` (that's the point of the fixture) is rejected as an
ordinary unknown-key error, structurally, not via a special-cased guard —
see ``tests/TemperaturePressureDiscrepancy.md`` for the divergence bug this
was originally written to demonstrate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tango_next.core.errors import ConfigError
from tango_next.workflows.workflow import Workflow

YAML_PATH = Path(__file__).parent.parent / "examples" / "tango_next" / "SF_manual_differing_st.yml"


def test_differing_surface_temp_pressure_raises() -> None:
    """Loading a file that sets surface_temperature/pressure in both common: and
    components.surface must raise ConfigError, not silently prefer one.
    """
    with pytest.raises(ConfigError, match="surface_temperature"):
        Workflow.from_file(YAML_PATH)
