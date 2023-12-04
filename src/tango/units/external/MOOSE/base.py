from tango.core.abstracts.unit import *
from tango.interfaces.tango_moose_interface import *
import yaml
from jinja2 import Template
import os


class MOOSERunner(Unit):
    """Runner for a MOOSE-based application"""
    def __init__(self, id: str, specs: dict):
        super().__init__(id, specs)


    def _interface_instance(self,
                            moose_executable_path,
                            moose_input_path,
                            pressure_bc_file,
                            flowrate_bc_file,
                            temperature_bc_file):

        self._interface = TangoMooseInterface(moose_executable_path,
                                             moose_input_path,
                                             pressure_bc_file,
                                             flowrate_bc_file,
                                             temperature_bc_file)


    def stream_interface(self) -> None:
        outlet_pressure, outlet_temperature, mass_rate = self.process_stream()
        self.mass_rate = mass_rate
        self.outlet_fluid.updatePT(outlet_pressure, outlet_temperature)


    def _generate_moose_input(self, yaml_file_path, template_file_path, output_directory, output_file_name):

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
