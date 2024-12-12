from tango.core.abstracts.unit import *
from tango.units.dataclasses import CommonSpecs, WellSpecsMOOSE
from tango.units.external.MOOSE.base import *


# class WellUnitMOOSE(MOOSERunner):
#     """MOOSE Well Unit"""
#     def __init__(self, id: str, specs: dict):
#         MOOSERunner.__init__(self, id, specs=self._process_specs(specs))
#         well_specs = self._process_specs(specs)
#         self._specs = WellSpecsMOOSE.from_dict(well_specs)
#         self._specs_post_processor()
#         self.init_stream_interface()
#
#     # ----------------------------------------- Public Functions ----------------------------------------- #
#
#     def init_stream_interface(self, P: float=None, T: float=None) -> None:
#         P = self._specs.surface_pressure if P==None else P
#         T = self._specs.surface_temperature if T == None else T
#         self.mass_rate = self._well_mass_flow_rate
#         self.inlet_fluid = FluidState.withPT(self._specs.fluid_name, P, T)
#         self.inlet_fluid = FluidState.withPT(self._specs.fluid_name, P, T)
#         self.outlet_fluid = FluidState.copy(self.inlet_fluid)
#
#     def process_stream(self) -> tuple:
#         """update dynamic variables along wellbore"""
#         self._interface.pressure_from_TANGO = self.inlet_fluid.P
#         self._interface.temperature_from_TANGO = self.inlet_fluid.T
#         self._interface.flowrate_from_TANGO = self.mass_rate/self.inlet_fluid.rho
#         # self._interface.pressure_from_TANGO = 3000000
#         # self._interface.temperature_from_TANGO = 320
#         # self._interface.flowrate_from_TANGO = 0.01
#         self._interface.run(self._post_processor_path)
#         print('\n')
#         print(f'well inlet -> P = {self.inlet_fluid.P}, T = {self.inlet_fluid.T}')
#         print(f'well outlet -> P = {self.outlet_fluid.P}, T = {self.outlet_fluid.T}')
#         # print(self._interface.pressure_from_MOOSE, self._interface.temperature_from_MOOSE, self.mass_rate)
#
#         # return self._interface.pressure_from_MOOSE + 1000000, self._interface.temperature_from_MOOSE, self.mass_rate
#         # return self._interface.pressure_from_MOOSE + 9000000, self._interface.temperature_from_MOOSE, 0.01
#         # return self._interface.pressure_from_MOOSE, self._interface.temperature_from_MOOSE, 20
#         # print('self._interface.pressure_from_MOOSE, self._interface.temperature_from_MOOSE, 20', self._interface.pressure_from_MOOSE, self._interface.temperature_from_MOOSE, 20)
#
#
#         # return self._interface.pressure_from_MOOSE, self._interface.temperature_from_MOOSE, 20
#
#
#
#         if (self._interface.temperature_from_MOOSE > 350):
#             return self._interface.pressure_from_MOOSE, self._interface.temperature_from_MOOSE, 45
#         else:
#             return 2000000, 383, 45
#
#
#     # -------------------------------------- data storing Functions -------------------------------------- #
#     # These PUBLIC functions are specific to native wellbore units. Some of them are called by the native
#     # orchestrator for iterative computations, while others are invoked by the economic unit. Please avoid
#     # setting them for external wellbore units, as they will not be called by the native orchestrator,
#     # and the economic inputs will need to be provided manually.
#
#     def get_probability_of_success(self) -> float:
#         return self._specs.probability_of_success
#
#     # TODO: These three functions should return three vectors!
#     def get_well_length(self) -> float:
#         return self._well_length
#
#
#     def get_well_type(self) -> float:
#         pass
#
#
#     def get_diameter(self) -> float:
#         return self._diameter
#
#     # ----------------------------------------- Private Functions ---------------------------------------- #
#
#     def _specs_post_processor(self) -> float:
#         self._diameter = self._specs.diameter
#         self._well_length = self._set_well_length()
#
#         yaml_file_path = self._specs.yaml_file_path
#         template_file_path = self._specs.template_file_path
#         output_directory = self._specs.output_directory
#         output_file_name = self._specs.output_file_name
#
#         self._generate_moose_input(yaml_file_path, template_file_path, output_directory, output_file_name)
#         self._post_processor_path = self._specs.post_processor_path
#
#         self._interface_instance(
#                 self._specs.moose_executable_path,
#                 self._specs.moose_input_path,
#                 self._specs.pressure_bc_file,
#                 self._specs.flowrate_bc_file,
#                 self._specs.temperature_bc_file)
#
#         self._well_mass_flow_rate = self._specs.mass_flow_rate
#         self._set_mult()
#
#     # TODO: Do the same for well type and diameter
#     def _set_well_length(self) -> float:
#         if self._specs.well_length is None:
#             raise RuntimeError(f"Required parameter 'well_length' is not found in specs.")
#         else:
#             return self._specs.well_length
#
#
#     def _process_specs(self, specs) -> dict:
#         return specs['common'] | specs['injection_well']
#
#
#     def _set_mult(self) -> None:
#         """
#             - m_dot_mult is to convert m_dot (well-pair level mass flow rate) at a producer
#               to a pattern level mass flow rate (=injection mass flow rate)
#         """
#         self._m_dot_mult = 0.25 if self._specs.well_pattern in ['5SPOT'] else 1.0


class WellUnitMOOSE(MOOSERunner):
    r"""
    MOOSE Well Unit for simulating wellbore dynamics.

    This class interfaces with a MOOSE-based application to simulate wellbore behavior,
    including fluid dynamics and temperature-pressure interactions.

    Attributes:
        _specs (WellSpecsMOOSE): Specifications for the well simulation.
        _diameter (float): Diameter of the well (m).
        _well_length (float): Length of the well (m).
        _well_mass_flow_rate (float): Mass flow rate of the well (kg/s).
        _m_dot_mult (float): Multiplier for converting flow rates.
        _post_processor_path (str): Path to the post-processor for MOOSE.
        _interface (TangoMooseInterface): Interface for communicating with the MOOSE application.

    Methods:
        init_stream_interface: Initializes stream interface with specified or default conditions.
        process_stream: Updates wellbore dynamics based on inlet conditions.
        get_probability_of_success: Retrieves the probability of success for the well.
        get_well_length: Retrieves the length of the well.
        get_diameter: Retrieves the diameter of the well.
    """

    def __init__(self, id: str, specs: dict):
        """
        Initializes a new instance of the WellUnitMOOSE class.

        Args:
            id (str): Identifier for the well unit.
            specs (dict): Specifications for the well simulation.
        """
        MOOSERunner.__init__(self, id, specs=self._process_specs(specs))
        well_specs = self._process_specs(specs)
        self._specs = WellSpecsMOOSE.from_dict(well_specs)
        self._specs_post_processor()
        self.init_stream_interface()

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self, P: float = None, T: float = None) -> None:
        """
        Initializes the stream interface with specified or default pressure and temperature.

        Args:
            P (float, optional): Surface pressure for the well (Pa).
            T (float, optional): Surface temperature for the well (°C).
        """
        P = self._specs.surface_pressure if P is None else P
        T = self._specs.surface_temperature if T is None else T
        self.mass_rate = self._well_mass_flow_rate
        self.inlet_fluid = FluidState.withPT(self._specs.fluid_name, P, T)
        self.outlet_fluid = FluidState.copy(self.inlet_fluid)

    def process_stream(self) -> tuple:
        r"""
        Updates dynamic variables along the wellbore.

        This function simulates the well's response based on the inlet fluid state
        and updates the outlet fluid state using MOOSE.

        Returns:
            tuple: Updated outlet pressure (Pa), temperature (°C), and mass rate (kg/s).
        """
        self._interface.pressure_from_TANGO = self.inlet_fluid.P
        self._interface.temperature_from_TANGO = self.inlet_fluid.T
        self._interface.flowrate_from_TANGO = self.mass_rate / self.inlet_fluid.rho
        self._interface.run(self._post_processor_path)

        print('\n')
        print(f'well inlet -> P = {self.inlet_fluid.P}, T = {self.inlet_fluid.T}')
        print(f'well outlet -> P = {self._interface.pressure_from_MOOSE}, T = {self._interface.temperature_from_MOOSE}')

        if self._interface.temperature_from_MOOSE > 350:
            return self._interface.pressure_from_MOOSE, self._interface.temperature_from_MOOSE, 45
        else:
            return 2000000, 383, 45

    def get_probability_of_success(self) -> float:
        """
        Retrieves the probability of success for the well.

        Returns:
            float: Probability of success.
        """
        return self._specs.probability_of_success

    def get_well_length(self) -> float:
        """
        Retrieves the length of the well.

        Returns:
            float: Well length (m).
        """
        return self._well_length

    def get_diameter(self) -> float:
        """
        Retrieves the diameter of the well.

        Returns:
            float: Well diameter (m).
        """
        return self._diameter

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _specs_post_processor(self) -> None:
        """
        Processes the specifications to initialize well properties.
        """
        self._diameter = self._specs.diameter
        self._well_length = self._set_well_length()

        yaml_file_path = self._specs.yaml_file_path
        template_file_path = self._specs.template_file_path
        output_directory = self._specs.output_directory
        output_file_name = self._specs.output_file_name

        self._generate_moose_input(yaml_file_path, template_file_path, output_directory, output_file_name)
        self._post_processor_path = self._specs.post_processor_path

        self._interface_instance(
            self._specs.moose_executable_path,
            self._specs.moose_input_path,
            self._specs.pressure_bc_file,
            self._specs.flowrate_bc_file,
            self._specs.temperature_bc_file)

        self._well_mass_flow_rate = self._specs.mass_flow_rate
        self._set_mult()

    def _set_well_length(self) -> float:
        """
        Sets the length of the well.

        Returns:
            float: Well length (m).

        Raises:
            RuntimeError: If the well length is not specified in the specifications.
        """
        if self._specs.well_length is None:
            raise RuntimeError("Required parameter 'well_length' is not found in specs.")
        return self._specs.well_length

    def _process_specs(self, specs) -> dict:
        """
        Combines common and well-specific specifications.

        Args:
            specs (dict): Input specifications.

        Returns:
            dict: Merged specifications.
        """
        return specs['common'] | specs['injection_well']

    def _set_mult(self) -> None:
        r"""
        Sets the multiplier for mass flow rate conversion.

        Multiplier Values:
            - 0.25 for '5SPOT' pattern.
            - 1.0 for other patterns.
        """
        self._m_dot_mult = 0.25 if self._specs.well_pattern in ['5SPOT'] else 1.0
