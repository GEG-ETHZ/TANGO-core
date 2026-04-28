#TODO: Implement
import logging

from tango.core.config import *
from tango.core import FluidState
from tango.units.dataclasses import CommonSpecs
from tango.units.native.surface.base import *
from dataclasses import dataclass


@dataclass
class SurfaceSpecsAGSNative(CommonSpecs):
    """
    Represents the specifications for the surface unit in AGS native operations.

    This class provides a placeholder for additional specifications that may be needed
    for advanced geothermal systems.

    Attributes:
        place_holder (float): Placeholder value for custom specifications (in meters).
    """
    place_holder: float | None = None  # (m)


class SurfaceStateAGSNative(SurfaceState):
    """
    Represents the state of a surface unit in AGS native operations.

    This class manages the fluid states at the inlet and outlet of the surface unit.

    Attributes:
        inlet_fluid_state (FluidState): Fluid state at the inlet of the surface unit.
        outlet_fluid_state (FluidState): Fluid state at the outlet of the surface unit.
    """

    def __init__(self):
        """
        Initializes the surface state for AGS native operations.

        The initialization sets up the fluid states for the inlet and outlet.
        """
        SurfaceState.__init__(self)
        self.inlet_fluid_state: FluidState
        self.outlet_fluid_state: FluidState


class SurfaceUnitAGSNative(SurfaceUnitNative):
    """
    Represents a surface unit for AGS native operations.

    This class initializes and manages the surface unit's state and specifications,
    providing a foundation for simulation and monitoring of advanced geothermal systems.

    Attributes:
        specs (SurfaceSpecsAGSNative): Specifications for the surface unit.
    """

    def __init__(self, id: str, specs: dict):
        """
        Initializes a new instance of the SurfaceUnitAGSNative class.

        Args:
            id (str): Unique identifier for the surface unit.
            specs (dict): Specifications for the surface unit.
        """
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsAGSNative.from_dict(specs)
        self.init_state()

    def init_state(self) -> None:
        """
        Initializes the state of the surface unit.

        This method can be extended to set up additional initial conditions or
        perform calculations specific to the surface unit's operation.
        """
        pass

