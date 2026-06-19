"""Component registry for tango_next.

Maps (type, unit) string pairs from the input YAML to concrete Component
classes.  Workflow.from_file() uses this to instantiate components without
hard-coding class names.

To add a new component type:
  1. Implement the Component subclass with a ``from_config(config: dict)``
     classmethod.
  2. Add a ``(type_str, unit_str): ClassName`` entry here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tango_next.components.reservoir.lumped import LumpedReservoir
from tango_next.components.surface.single_flash import SingleFlashSurface
from tango_next.components.well.lumped import (
    LumpedInjectionWell,
    LumpedProductionWell,
    LumpedProductionWellPump,
)
from tango_next.components.well.numerical import (
    NumericalInjectionWell,
    NumericalProductionWell,
    NumericalProductionWellPump,
)

if TYPE_CHECKING:
    from tango_next.core.component import Component

# (component_type, unit) → concrete class with a from_config() classmethod
COMPONENT_REGISTRY: dict[tuple[str, str], type[Component]] = {
    ("injection_well", "native"): LumpedInjectionWell,
    ("injection_well", "numerical"): NumericalInjectionWell,
    ("reservoir", "native"): LumpedReservoir,
    ("production_well", "native"): LumpedProductionWell,
    ("production_well", "numerical"): NumericalProductionWell,
    ("production_well_pump", "native"): LumpedProductionWellPump,
    ("production_well_pump", "numerical"): NumericalProductionWellPump,
    ("surface", "single_flash"): SingleFlashSurface,
}
