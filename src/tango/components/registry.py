"""Component registry for tango.

Maps (type, variant) string pairs from the input YAML to concrete Component
classes.  Workflow.from_file() uses this to instantiate components without
hard-coding class names.

To add a new component type:
  1. Implement the Component subclass with a ``from_dict(config: dict)``
     classmethod.
  2. Add a ``(type_str, variant_str): ClassName`` entry here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tango.components.economic.doublet import DoubletEconomicComponent
from tango.components.reservoir.lumped import LumpedReservoir
from tango.components.surface.graph import GraphSurface
from tango.components.well.lumped import (
    LumpedInjectionWell,
    LumpedProductionWell,
    LumpedProductionWellWithPump,
)
from tango.components.well.numerical import (
    NumericalInjectionWell,
    NumericalProductionWell,
    NumericalProductionWellWithPump,
    NumericalWell,
)

if TYPE_CHECKING:
    from tango.core.component import Component

# (component_type, variant) → concrete class with a from_dict() classmethod
COMPONENT_REGISTRY: dict[tuple[str, str], type[Component]] = {
    ("injection_well", "lumped"): LumpedInjectionWell,
    ("injection_well", "numerical"): NumericalInjectionWell,
    ("reservoir", "lumped"): LumpedReservoir,
    ("production_well", "lumped"): LumpedProductionWell,
    ("production_well", "numerical"): NumericalProductionWell,
    ("production_well_with_pump", "lumped"): LumpedProductionWellWithPump,
    ("production_well_with_pump", "numerical"): NumericalProductionWellWithPump,
    ("horizontal_well", "numerical"): NumericalWell,
    ("surface", "graph"): GraphSurface,
    ("economic", "doublet"): DoubletEconomicComponent,
}
