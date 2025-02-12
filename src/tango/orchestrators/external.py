from tango.core.abstracts.orchestrator import *
from tango.orchestrators.pressure_back_calculator import wellbore
import csv
import os
from tango.utils import *
import numpy as np
import inspect
from tango.flow_rate import *

class SystemExternal(UnitManager):
    """
    Manages the interaction between subsurface and surface units in a geothermal system, allowing for dynamic
    updates of system variables and flow rate calculations. This class orchestrates the communication and updates
    among different units in the system, particularly focusing on subsurface pressure and flow rate control.

    Attributes:
        flow_rate_calculator (FlowRateCalculator): An instance of the FlowRateCalculator for handling flow rate calculations.
        unit (object): The unit containing injection well, production well, reservoir, surface, and optional production well pump.
    """
    def __init__(self, specs):
        """
        Initializes a new instance of the SystemExternal class.

        Args:
            specs (dict): Specifications for the system, including schedule and unit configurations.

        Notes:
            - If the production well pump is not specified, it is set to `None`.
        """
        super().__init__(specs)
        if not hasattr(self.unit, 'production_well_pump') or self.unit.production_well_pump is None:
            self.unit.production_well_pump = None

        self.flow_rate_calculator = FlowRateCalculator(self.unit.injection_well, self.unit.production_well, self.unit.production_well_pump, self.unit.reservoir, self.unit.surface)

    def update(self) -> None:
        """
        Updates the system by adjusting subsurface and surface variables based on the current schedule.

        This method checks the schedule for conditions to determine how the system should be updated.
        It supports both direct reservoir pressure control and pressure back-calculation at the injection well bottom.

        Raises:
            NotImplementedError: If the surface unit or checkpoint type is unsupported.
        """
        if 'entire_subsurface_external' in self.specs['schedule'] and self.specs['schedule']['entire_subsurface_external'] == 'yes':
            pass
        else:
            if self.specs['schedule']['bc_iteration_checkpoint'] == 'injection_well_bottom':

                if self.unit.surface.__class__.__name__ in ['SurfaceUnitFlexiblePP', 'SurfaceUnitCPGNative', 'SurfaceUnitORCNative']:

                    if (self.unit.reservoir.__class__.__name__ == 'ReservoirFileReaderUnit'):
                        self.flow_rate_calculator.pressure_finder(self.unit.reservoir.inlet_pressure)
                    else:
                        self.flow_rate_calculator.pressure_finder(self.unit.reservoir.specs.hydro_static_pressure * (self.unit.reservoir.specs.over_pressure_percentage / 100.0 + 1.0))

                else:
                    raise NotImplementedError("Only SurfaceUnitCPGNative and SurfaceUnitORCNative are supported for now")

            else:
                raise NotImplementedError("Only 'injection_well_bottom' is supported as a checkpoint when the external system is used as orchestrator")

    def update_time_dependent_vars(self) -> None:
        """
        Updates time-dependent variables across the injection well, production well, reservoir, and surface units.

        This method increments the time step for each component and updates energy extraction, dimensionless time,
        and row indices for CSV-based data sources (if applicable).

        Raises:
            NotImplementedError: If the surface unit type is unsupported.
        """
        if self.unit.surface.__class__.__name__ in ['SurfaceUnitFlexiblePP', 'SurfaceUnitCPGNative', 'SurfaceUnitORCNative']:
            if self.unit.reservoir.__class__.__name__ != 'ReservoirFileReaderUnit':
                self.unit.reservoir.update_energy_extracted_old()
            self.unit.injection_well.update_dimensionless_time_old()
            self.unit.production_well.update_dimensionless_time_old()
            if (self.unit.production_well_pump != None):
                self.unit.production_well_pump.update_dimensionless_time_old()
            self.unit.surface.current_row += 1
            self.unit.reservoir.current_row += 1
            self.unit.injection_well.current_row += 1
            self.unit.production_well.current_row += 1

        else:
            raise NotImplementedError("Only SurfaceUnitCPGNative and SurfaceUnitORCNative are supported for now")
