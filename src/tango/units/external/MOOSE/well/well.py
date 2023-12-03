from tango.core.abstracts.unit import *
from tango.units.native.common import CommonSpecs, WellSpecsMOOSE
from tango.units.external.MOOSE.base import *


class WellUnitMOOSE(MOOSERunner):
    """MOOSE Well Unit"""
    def __init__(self, id: str, specs: dict):
        MOOSERunner.__init__(self, id, specs=self._process_specs(specs))
        well_specs = self._process_specs(specs)
        self._specs = WellSpecsMOOSE.from_dict(well_specs)
        self._specs_post_processor()
        self.init_stream_interface()

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self, P: float=None, T: float=None) -> None:
        P = self._specs.surface_pressure if P==None else P
        T = self._specs.surface_temperature if T == None else T
        self.mass_rate = self._well_mass_flow_rate
        self.inlet_fluid = FluidState.withPT(self._specs.fluid_name, P, T)
        self.inlet_fluid = FluidState.withPT(self._specs.fluid_name, P, T)
        self.outlet_fluid = FluidState.copy(self.inlet_fluid)

    def process_stream(self) -> None:
        """update dynamic variables along wellbore"""
        self.interface.pressure_from_TANGO = self.inlet_fluid.P
        self.interface.temperature_from_TANGO = self.inlet_fluid.T
        self.interface.flowrate_from_TANGO = self.mass_rate/self.inlet_fluid.rho
        self.interface.run(self.post_processor_path)
        self.ppp = self.interface.pressure_from_MOOSE
        self.ttt = self.interface.temperature_from_MOOSE


    def stream_interface(self) -> None:
        self.process_stream()
        self.outlet_fluid.updatePT(self.ppp, self.ttt)

    # -------------------------------------- data storing Functions -------------------------------------- #
    # These PUBLIC functions are specific to native wellbore units. Some of them are called by the native
    # orchestrator for iterative computations, while others are invoked by the economic unit. Please avoid
    # setting them for external wellbore units, as they will not be called by the native orchestrator,
    # and the economic inputs will need to be provided manually.

    def get_probability_of_success(self) -> float:
        return self._specs.probability_of_success

    # To Do: These three functions should return three vectors!
    def get_well_length(self) -> float:
        return self._well_length


    def get_well_type(self) -> float:
        pass


    def get_diameter(self) -> float:
        return self._diameter

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _specs_post_processor(self) -> float:
        self._diameter = self._specs.diameter
        self._well_length = self._set_well_length()

        yaml_file_path = self._specs.yaml_file_path
        template_file_path = self._specs.template_file_path
        output_directory = self._specs.output_directory
        output_file_name = self._specs.output_file_name

        self._generate_moose_input(yaml_file_path, template_file_path, output_directory, output_file_name)
        self.post_processor_path = self._specs.post_processor_path

        self._interface_instance(
                self._specs.moose_executable_path,
                self._specs.moose_input_path,
                self._specs.pressure_bc_file,
                self._specs.flowrate_bc_file,
                self._specs.temperature_bc_file)

        self._well_mass_flow_rate = self._specs.mass_flow_rate
        self._set_mult()

    # To Do: Do the same for well type and diameter
    def _set_well_length(self) -> float:
        if self._specs.well_length is None:
            raise RuntimeError(f"Required parameter 'well_length' is not found in specs.")
        else:
            return self._specs.well_length


    def _process_specs(self, specs) -> dict:
        return specs['common'] | specs['injection_well']


    def _set_mult(self) -> None:
        """
            - m_dot_mult is to convert m_dot (well-pair level mass flow rate) at a producer
              to a pattern level mass flow rate (=injection mass flow rate)
        """
        self._m_dot_mult = 0.25 if self._specs.well_pattern in ['5SPOT'] else 1.0
