from tango.core.abstracts.unit import *
from tango.interfaces.tango_moose_interface import *
import yaml
from jinja2 import Template
import os


class MOOSERunner(Unit):
    r"""
    Runner for a MOOSE-based application..

    This class provides functionality to interface with a MOOSE application,
    including preparing input files and managing streams.

    Attributes:
        _interface (TangoMooseInterface): Interface for communicating with the MOOSE application.
        mass_rate (float): Mass flow rate through the unit (kg/s).
        outlet_fluid (object): Represents the state of the outlet fluid.

    Methods:
        stream_interface: Updates the stream interface for the MOOSE application.
        _interface_instance: Initializes the MOOSE application interface with specified paths.
        _generate_moose_input: Generates a MOOSE input file from a YAML file and template.
    """

    def __init__(self, id: str, specs: dict):
        """
        Initializes a new instance of the MOOSERunner class.

        Args:
            id (str): Identifier for the unit.
            specs (dict): Specifications for the unit.
        """
        super().__init__(id, specs)
        self.specs = specs

    def _interface_instance(self,
                            moose_executable_path: str,
                            moose_input_path: str,
                            pressure_bc_file: str,
                            flowrate_bc_file: str,
                            temperature_bc_file: str):
        """
        Initializes the MOOSE application interface.

        Args:
            moose_executable_path (str): Path to the MOOSE executable.
            moose_input_path (str): Path to the MOOSE input file.
            pressure_bc_file (str): Path to the pressure boundary condition file.
            flowrate_bc_file (str): Path to the flowrate boundary condition file.
            temperature_bc_file (str): Path to the temperature boundary condition file.
        """
        self._interface = TangoMooseInterface(moose_executable_path,
                                              moose_input_path,
                                              pressure_bc_file,
                                              flowrate_bc_file,
                                              temperature_bc_file,
                                              self.specs)

    def stream_interface(self) -> None:
        """
        Updates the stream interface based on the MOOSE application's outputs.

        This function retrieves the outlet pressure, outlet temperature, and mass rate
        from the process stream and updates the outlet fluid state.
        """
        outlet_pressure, outlet_temperature, mass_rate = self.process_stream()
        self.mass_rate = mass_rate
        self.outlet_fluid.updatePT(outlet_pressure, outlet_temperature)

    def _generate_moose_input(self, yaml_file_path: str, template_file_path: str, output_directory: str, output_file_name: str):
        """
        Generates a MOOSE input file using a YAML configuration file and a template.

        Args:
            yaml_file_path (str): Path to the YAML configuration file.
            template_file_path (str): Path to the MOOSE input template file.
            output_directory (str): Directory to save the generated input file.
            output_file_name (str): Name of the output MOOSE input file.

        Raises:
            FileNotFoundError: If any input files are not found.
            KeyError: If required variables are missing from the YAML configuration.
        """
        import yaml
        from jinja2 import Template

        # Load the YAML configuration file
        with open(yaml_file_path, 'r') as yaml_file:
            data = yaml.load(yaml_file, Loader=yaml.FullLoader)

        # Define variable mapping
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

        # Load the MOOSE input template
        with open(template_file_path, 'r') as template_file:
            moose_template = Template(template_file.read())

        # Extract variables for the template
        moose_variables = {}
        for yaml_var, mapping_data in mapping.items():
            block = mapping_data['block']
            var = mapping_data['var']
            if block in data and var in data[block]:
                moose_variables[yaml_var] = data[block][var]
            else:
                raise KeyError(f"Missing required variable '{var}' in block '{block}' in the YAML file.")

        # Render the template with the extracted variables
        moose_input = moose_template.render(moose_variables)

        # Save the rendered input file
        output_file_path = os.path.join(output_directory, output_file_name)
        os.makedirs(output_directory, exist_ok=True)
        with open(output_file_path, 'w') as output_file:
            output_file.write(moose_input)
