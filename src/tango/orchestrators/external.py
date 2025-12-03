from tango.core.abstracts.orchestrator import *
from tango.orchestrators.BC_calculator import *
from tango.orchestrators.HotmapsDispatch_runner import process_yaml_and_setup_hotmaps
from tango.units.dataclasses import DistrictHeatingSpecs


class SystemExternal(UnitManager):
    """
    Manages the interaction between subsurface and surface units in a geothermal system, allowing for dynamic
    updates of system variables and flow rate calculations. This class orchestrates the communication and updates
    among different units in the system, particularly focusing on subsurface pressure and flow rate control.

    Attributes:
        flow_rate_calculator (FlowRateCalculator): An instance of the FlowRateCalculator for handling flow rate calculations.
        unit (object): The unit containing injection well, production well, reservoir, surface, and optional production well pump.
    """
    def __init__(self, specs, unit_options):
        """
        Initializes a new instance of the SystemExternal class.

        Args:
            specs (dict): Specifications for the system, including schedule and unit configurations.
            unit_options (dict): Dictionary mapping unit types and names to classes.

        Notes:
            - If the production well pump is not specified, it is set to `None`.
        """
        super().__init__(specs, unit_options)

        if 'district_heating' in specs:
            self.specs2 = DistrictHeatingSpecs.from_dict(self._process_specs2(specs))

        self._results = dict()

        for component in ['injection_well', 'production_well', 'reservoir', 'surface', 'production_well_pump']:
            if not hasattr(self.unit, component) or getattr(self.unit, component) is None:
                setattr(self.unit, component, None)

        if ((self.unit.injection_well.__class__.__name__ == 'WellUnitMOOSE') and (self.unit.surface.__class__.__name__ == 'SurfaceUnitORCNative')):
            self.unit.surface.P_out_constraint = True

        self.specs3 = (self._process_specs3(specs))

        if (self.unit.injection_well.__class__.__name__ != 'WellUnitMOOSE'):
            self.flow_rate_calculator = FlowRateCalculator(self.specs3, self.unit.injection_well, self.unit.production_well, self.unit.production_well_pump, self.unit.reservoir, self.unit.surface)

    def _process_specs2(self, specs) -> dict:
        """
        Processes the reservoir specifications and computes derived parameters.

        This method ensures the effective well diameter is computed if not already specified,
        and merges common and reservoir-specific specifications.

        Args:
            specs (dict): Input specifications for the reservoir.

        Returns:
            dict: Processed specifications with all required parameters.

        Process:
            - If `well_eff_diameter` is not specified:
                - Use the diameter of the injection and production wells to compute an effective diameter.
                - Defaults to 0.41 m if no values are provided.
            - Merge common and reservoir-specific specs.
        """
        return specs['district_heating'] # | specs['schedule']

    def _process_specs3(self, specs) -> dict:

        return specs['schedule'] | specs['common']

    def update(self, funcs, results) -> None:
        """
        Updates the system by adjusting subsurface and surface variables based on the current schedule.

        This method checks the schedule for conditions to determine how the system should be updated.
        It supports both direct reservoir pressure control and pressure back-calculation at the injection well bottom.

        Raises:
            NotImplementedError: If the surface unit or checkpoint type is unsupported.
        """
        if (self.unit.injection_well.__class__.__name__ == 'WellUnitMOOSE'):
            pass # check bc_point here
        else:
            if self.specs['schedule']['bc_iteration_checkpoint'] == 'injection_well_bottom':

                if self.unit.surface.__class__.__name__ in ['SurfaceUnitFlexiblePP', 'SurfaceUnitCPGNative', 'SurfaceUnitORCNative']:

                    if (self.unit.reservoir.__class__.__name__ == 'ReservoirFileReaderUnit'):
                        self.flow_rate_calculator.iterator(
                            self.unit.reservoir.inlet_pressure,
                            self.unit.reservoir.inlet_flow,
                            funcs,
                        )
                    else:
                        self.flow_rate_calculator.iterator(
                            self.unit.reservoir.specs.hydro_static_pressure * (
                                self.unit.reservoir.specs.over_pressure_percentage / 100.0 + 1.0
                            ),
                            None,
                            funcs,
                        )

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
        if (self.unit.injection_well.__class__.__name__ == 'WellUnitMOOSE'):
            pass # check bc_point here
        else:
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

    def hotmapsdispatch_runner(self, eco_results, t_results, dt_list) -> None:
        result = process_yaml_and_setup_hotmaps('/Users/morteza/Documents/projects/TANGO/examples/complete_config.yaml', eco_results, self.specs2, t_results, dt_list)

        if result["status"] == "success":
            print(f"Excel file created at: {result['excel_file']}")
            print(f"Batch file created at: {result['batch_file']}")
            print(f"Trigger file created at: {result['trigger_file']}")
        else:
            print(f"Error: {result['message']}")
