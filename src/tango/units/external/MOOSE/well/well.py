from tango.core.abstracts.unit import *
from tango.units.native.common import CommonSpecs, WellSpecsMOOSE
from tango.interfaces.tango_moose_interface import *
import yaml
from jinja2 import Template
import os


class MOOSERunner(Unit):
    """Runner for a MOOSE-based application"""
    def __init__(self, id: str, specs: dict):
        super().__init__(id, specs)
        self._specs = WellSpecsMOOSE.from_dict(specs)

        # To DO: _diameter, _well_length, and _well_type should be received as three separate vectors
        self._diameter = self._specs.diameter
        self._well_length = self._set_well_length()

        yaml_file_path = self._specs.yaml_file_path
        template_file_path = self._specs.template_file_path
        output_directory = self._specs.output_directory
        output_file_name = self._specs.output_file_name

        self.generate_moose_input(yaml_file_path, template_file_path, output_directory, output_file_name)

        self.moose_executable_path = self._specs.moose_executable_path
        self.moose_input_path = self._specs.moose_input_path
        self.post_processor_path = self._specs.post_processor_path
        self.pressure_bc_file = self._specs.pressure_bc_file
        self.flowrate_bc_file = self._specs.flowrate_bc_file
        self.temperature_bc_file = self._specs.temperature_bc_file

        self.interface = TangoMooseInterface(
                self.moose_executable_path,
                self.moose_input_path,
                self.pressure_bc_file,
                self.flowrate_bc_file,
                self.temperature_bc_file)


    def generate_moose_input(self, yaml_file_path, template_file_path, output_directory, output_file_name):

        with open(yaml_file_path, 'r') as yaml_file:
            data = yaml.load(yaml_file, Loader=yaml.FullLoader)

        mapping = {
            'diameter': {'block': 'injection_well', 'var': 'diameter'},
            'epsilon': {'block': 'injection_well', 'var': 'epsilon'},
            'rock_density': {'block': 'props', 'var': 'rock_density'},
            'rock_cp': {'block': 'props', 'var': 'rock_cp'},
            'rock_k': {'block': 'props', 'var': 'rock_k'},
            'thermal_gradient': {'block': 'props', 'var': 'thermal_gradient'},
            'surface_temperature': {'block': 'surface', 'var': 'surface_temperature'},
            'surface_pressure': {'block': 'surface', 'var': 'surface_pressure'},
            'end_time': {'block': 'schedule', 'var': 'end_time'},
        }

        with open(template_file_path, 'r') as template_file:
            moose_template = Template(template_file.read())

        moose_variables = {}
        for yaml_var, mapping_data in mapping.items():
            block = mapping_data['block']
            var = mapping_data['var']
            moose_variables[yaml_var] = data[block][var]

        moose_input = moose_template.render(moose_variables)
        output_file_path = os.path.join(output_directory, output_file_name)
        with open(output_file_path, 'w') as output_file:
            output_file.write(moose_input)


class WellUnitMOOSE(MOOSERunner):
    """MOOSE Well Unit"""
    def __init__(self, id: str, specs: dict):
        MOOSERunner.__init__(self, id, specs=self._process_specs(specs))
        self._well_mass_flow_rate = self._specs.mass_flow_rate
        self._set_mult()
        self.init_state()

    # To Do: Do the same for well type and diameter
    def _set_well_length(self) -> float:
        if self._specs.well_length is None:
            raise RuntimeError(f"Required parameter 'well_length' is not found in specs.")
        else:
            return self._specs.well_length


    def _initialize_state(self) -> None:
        self.fluid_state_init = self.inlet_fluid


#######################################################
    # To Do: These three functions should return three vectors!
    def get_well_length(self) -> float:
        return self._well_length


    def get_well_type(self) -> float:
        pass


    def get_diameter(self) -> float:
        return self._diameter
#######################################################


    def get_probability_of_success(self) -> float:
        return self._specs.probability_of_success


    def process_stream(self) -> None:
        """update dynamic variables along wellbore"""
        self._initialize_state()
        self.interface.pressure_from_TANGO = self.inlet_fluid.P
        self.interface.temperature_from_TANGO = self.inlet_fluid.T
        self.interface.flowrate_from_TANGO = self.mass_rate/self.inlet_fluid.rho
        self.interface.run(self.post_processor_path)
        # self.outlet_fluid.updatePT(self.interface.pressure_from_MOOSE, self.interface.temperature_from_MOOSE)
        self.ppp = self.interface.pressure_from_MOOSE
        self.ttt = self.interface.temperature_from_MOOSE


    def stream_interface(self) -> None:
        self.update_inlet_state()
        self.process_stream()
        self.outlet_fluid.updatePT(self.ppp, self.ttt)
        print("injection_in ", self.inlet_fluid.P, self.inlet_fluid.T)
        print("injection_out ", self.outlet_fluid.P, self.outlet_fluid.T)


    def _process_specs(self, specs) -> dict:
        return specs['common'] | specs['injection_well']


    def _set_mult(self) -> None:
        """
            - m_dot_mult is to convert m_dot (well-pair level mass flow rate) at a producer
              to a pattern level mass flow rate (=injection mass flow rate)
        """
        self._m_dot_mult = 0.25 if self._specs.well_pattern in ['5SPOT'] else 1.0


    def init_state(self, P: float=None, T: float=None) -> None:
        P = self._specs.surface_pressure if P==None else P
        T = self._specs.surface_temperature if T == None else T
        # self.state = UnitState()
        self.mass_rate = self._well_mass_flow_rate
        self.inlet_fluid = FluidState.withPT(self._specs.fluid_name, P, T)
        self.inlet_fluid = FluidState.withPT(self._specs.fluid_name, P, T)
        self.outlet_fluid = FluidState.copy(self.inlet_fluid)


    def update_inlet_state(self) -> None:
        """
         updated inlet state based on inlet streams
                 (mass flow rate weighted average)
        """
        total_mass_rate = 0.
        for sl in self.inlet_streams:
            total_mass_rate += sl.mass_rate
        T_ave, P_ave, H_ave = 0., 0., 0.
        for sl in self.inlet_streams:
            wt = sl.mass_rate / total_mass_rate
            T_ave += wt * sl.fluid_state.T
            P_ave += wt * sl.fluid_state.P
            H_ave += wt * sl.fluid_state.H
        self.mass_rate = self._m_dot_mult * total_mass_rate
        try:
            self.inlet_fluid.updateHP(H=H_ave, P=P_ave)
        except:
            self.inlet_fluid.updatePT(P=P_ave, T=T_ave)
