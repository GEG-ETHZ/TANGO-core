from tango.units.dataclasses import CommonSpecs
from tango.units.native.surface.base import *
from dataclasses import dataclass

import yaml
from tespy.components import Sink, Source, Turbine, SimpleHeatExchanger, Compressor, Valve, DropletSeparator, Merge, HeatExchanger, CycleCloser
from tespy.connections import Connection
from tespy.networks import Network
import numpy as np

from tabulate import tabulate
from termcolor import colored
from itertools import cycle

@dataclass
class SurfaceSpecsFlexiblePP(CommonSpecs):

    pp_design_file: str = None
    pipe_diameter: float = None
    approach_temperature: float = None
    epsilon: float = 55.e-6
    cooling_tower_design: str = 'CLOSED' # should be removed
    cooling_mode: str = 'WET' # should be removed
    temperature_range: float = 0.0

    def __post_init__(self):
        required_fields = ['pipe_diameter']
        for s in required_fields:
            if getattr(self, s, None) is None:
                raise RuntimeError(f"Required parameter: {s} is not found.")

class SurfaceUnitFlexiblePP(SurfaceUnitNative):
    def __init__(self, id: str, specs: dict):
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsFlexiblePP.from_dict(self._process_specs(specs))
        self._m_dot_mult = 1
        self.current_row = 0
        self.init_stream_interface()

        # yaml_config_path = '/Users/morteza/Documents/projects/TANGO/examples/testi2.yml'
        yaml_config_path = self.specs.pp_design_file

        self.power_plant = PowerPlant(yaml_config_path, self.specs)
        # self.power_plant_cost = PowerPlantCost(self.power_plant)

    def init_stream_interface(self, P: float = None, T: float = None) -> None:
        """
        Initializes the fluid states for the CO2 thermosiphon system:
        production_well - turbine - condenser - pump - injection_well.
        """
        if P is not None and T is not None:
            self.inlet_fluid = FluidState.withPT(self._fluid_name, P, T)

        # self.mass_rate = self.specs.mass_flow_rate * self.specs.well_pattern_dimens[0] * self.specs.well_pattern_dimens[1] / self.specs.num_pp
        # self.mass_rate = self.specs.mass_flow_rate

        self.mass_rate = self.specs.mass_flow_rate * self.specs.well_pattern_dimens[0] * self.specs.well_pattern_dimens[1] / self.specs.num_pp
        self.outlet_fluid = FluidState.withPT(self.specs.fluid_name, 10000000.0, 290.0)
        # self.outlet_fluid = FluidState.withPT('H2O', 4000000.0, 413.0)

    def process_stream(self) -> None:
        """
        Processes the stream by updating turbine, condenser, and pump states,
        and computes the net system performance.
        """

        # self.mass_rate = self.specs.mass_flow_rate * self.specs.well_pattern_dimens[0] * self.specs.well_pattern_dimens[1] / self.specs.num_pp

        ################################################################################################################

        self.power_plant.set_attributes(fluid={self.specs.fluid_name: 1}, mass_rate=self.mass_rate, production_pressure=self.inlet_fluid.P/100000, production_temperature=self.inlet_fluid.T - 273.15)
        # self.power_plant.set_attributes(fluid={'H2O': 1}, mass_rate=50, production_pressure=40, production_temperature=140)
        print({self.specs.fluid_name: 1}, self.mass_rate, self.inlet_fluid.P/100000, self.inlet_fluid.T - 273.15)
        self.power_plant.network.solve('design')
        outlet_state = self.power_plant.get_outlet_conditions()

        # self.total_cost = self.power_plant_cost.compute_total_cost()
        self.w_net = self.power_plant.calculate_net_power()

        return outlet_state['pressure'] * 1000000.0, outlet_state['temperature'] + 273.15, self.mass_rate

    def _process_specs(self, specs) -> dict:
        """
        Combines common and surface-specific specifications.

        Args:
            specs (dict): Input specifications with keys `common` and `surface`.

        Returns:
            dict: Merged dictionary of specifications.
        """
        return specs['common'] | specs['surface']


class PowerPlant:
    def __init__(self, yaml_config_path, specs):

        # self.cooling_mode = 'WET'
        self.pp_specs = specs

        # if self.cooling_mode == 'WET':
        #     self._coeffs_cooling = [1.2, 0.0, -3.79e-3, 1.95e-2]
        #     self._coeffs_condensing = [1.65, -6.24e-6, -5.03e-3, 0.0]
        # elif self.cooling_mode == 'DRY':
        #     self._coeffs_cooling = [7.65e-1, 0.0, 0.0, 1.28e-1]
        #     self._coeffs_condensing = [0.619, 0.0, 0.0, 0.0]
        # else:
        #     raise ValueError(f"surface_cooling_tower_mode: {self.cooling_mode} is not supported")

        with open(yaml_config_path, 'r') as file:
            self.config = yaml.safe_load(file)

        # Create TESPy components
        self.nodes = {}
        for node_name, node_data in self.config['power_plant_graph']['nodes'].items():
            self.nodes[node_name] = self._create_component(node_data['type'], node_name)

        # Create TESPy connections
        self.connections = []
        for edge_id, edge_data in self.config['power_plant_graph']['edges'].items():
            source = self.nodes[edge_data['source']]
            target = self.nodes[edge_data['target']]
            source_port = edge_data.get('source_port', 'out1')
            target_port = edge_data.get('target_port', 'in1')
            connection = Connection(source, source_port, target, target_port)
            self.connections.append(connection)

        self.network = Network(p_unit='bar', T_unit='C', h_unit='kJ / kg', iterinfo=False)
        self.network.add_conns(*self.connections)

    def _create_component(self, component_type, name):
        component_mapping = {
            'Sink': Sink,
            'Source': Source,
            'Turbine': Turbine,
            'SimpleHeatExchanger': SimpleHeatExchanger,
            'Compressor': Compressor,
            'Valve': Valve,
            'DropletSeparator': DropletSeparator,
            'Merge': Merge,
            'HeatExchanger': HeatExchanger,
            'CycleCloser': CycleCloser
        }
        return component_mapping[component_type](name)

    def set_attributes(self, fluid, mass_rate, production_pressure, production_temperature):
        # Set attributes for components
        for component_name, attributes in self.config.items():
            if component_name in self.nodes:
                component = self.nodes[component_name]
                adjusted_attributes = {}

                for attr_name, attr_value in attributes.items():
                    if attr_name == 'efficiency':  # Efficiency for turbine and pump
                        adjusted_attributes['eta_s'] = attr_value
                    elif attr_name in ['ttd_u', 'ttd_l', 'pr1', 'pr2']:  # Specific to HeatExchanger
                        adjusted_attributes[attr_name] = attr_value
                # Set component-specific attributes conditionally
                component.set_attr(**adjusted_attributes)

        # Set attributes for connections
        for connection in self.connections:
            source_component = connection.source  # TESPy component object
            component_type = type(source_component).__name__  # Get the type as a string

            # Handle attributes dynamically for each connection based on the component type
            connection_attributes = {}

            if component_type == 'Source':
                # Handle the inlet source specifically
                if source_component.label == 'inlet':  # Match by name only for very specific cases
                    connection_attributes['fluid'] = fluid
                    connection_attributes['m'] = mass_rate
                    connection_attributes['T'] = production_temperature
                    connection_attributes['p'] = production_pressure
                else:
                    # Dynamically handle multiple sources by their labels
                    component_label = source_component.label  # e.g., "source1" or "source2"
                    source_config = self.config.get(component_label, {})  # Get config for the specific source

                    if 'fluid' in source_config:
                        connection_attributes['fluid'] = source_config['fluid']
                    if 'm' in source_config:
                        connection_attributes['m'] = source_config['m']
                    if 'T' in source_config:
                        connection_attributes['T'] = source_config['T']
                    if 'p' in source_config:
                        connection_attributes['p'] = source_config['p']
                    if 'vapor_mass_fraction_out' in source_config:
                        connection_attributes['x'] = source_config['vapor_mass_fraction_out']

            elif component_type == 'Sink':
                # Dynamically handle multiple sinks by their labels
                component_label = source_component.label  # e.g., "sink1" or "sink2"
                sink_config = self.config.get(component_label, {})  # Get config for the specific sink
                if 'T' in sink_config:
                    connection_attributes['T'] = sink_config['T']
                if 'p' in sink_config:
                    connection_attributes['p'] = sink_config['p']

            elif component_type == 'Valve':
                # Dynamically handle valve configuration based on label
                component_label = source_component.label  # Get the specific label of the valve
                valve_config = self.config.get(component_label, {})  # Look up the config for the specific valve by its label
                if 'p_out' in valve_config:
                    connection_attributes['p'] = valve_config['p_out']
                if 'T_out' in valve_config:
                    connection_attributes['T'] = valve_config['T_out']

            elif component_type == 'Turbine':
                # Dynamically handle turbine configuration based on label
                component_label = source_component.label  # Get the specific label of the turbine
                turbine_config = self.config.get(component_label, {})  # Look up the config for the specific turbine by its label
                if 'p_out' in turbine_config:
                    connection_attributes['p'] = turbine_config['p_out']
                if 'T_out' in turbine_config:
                    connection_attributes['T'] = turbine_config['T_out']

            elif component_type == 'SimpleHeatExchanger':
                # Handle both condensers (or any other heat exchanger)
                component_label = source_component.label
                if component_label in self.config:  # Check if the component is in the config
                    heat_exchanger_config = self.config[component_label]
                    if 'p_out' in heat_exchanger_config:
                        connection_attributes['p'] = heat_exchanger_config['p_out']
                    if 'T_out' in heat_exchanger_config:
                        connection_attributes['T'] = heat_exchanger_config['T_out']
                    if 'vapor_mass_fraction_out' in heat_exchanger_config:
                        connection_attributes['x'] = heat_exchanger_config['vapor_mass_fraction_out']

            elif component_type == 'Compressor':
                # Dynamically handle pump configuration based on label
                component_label = source_component.label  # Get the specific label of the pump
                pump_config = self.config.get(component_label, {})  # Look up the config for the specific pump by its label
                if 'p_out' in pump_config:
                    connection_attributes['p'] = pump_config['p_out']
                if 'T_out' in pump_config:
                    connection_attributes['T'] = pump_config['T_out']

            elif component_type == 'DropletSeparator':
                # Dynamically handle droplet separator configuration based on label
                component_label = source_component.label  # Get the specific label of the droplet separator
                droplet_separator_config = self.config.get(component_label, {})  # Look up the config for the specific separator by its label

            elif component_type == 'Merge':
                # Dynamically handle merge configuration based on label
                component_label = source_component.label  # Get the specific label of the merge component
                merge_config = self.config.get(component_label, {})  # Look up the config for the specific merge by its label

            elif component_type == 'CycleCloser':
                # Dynamically handle merge configuration based on label
                component_label = source_component.label  # Get the specific label of the merge component
                CycleCloser_config = self.config.get(component_label, {})  # Look up the config for the specific merge by its label

            elif component_type == 'HeatExchanger':
                # Handle HeatExchanger configuration for dual connections
                component_label = source_component.label
                heat_exchanger_config = self.config.get(component_label, {})
                source_port = connection.source_id  # Get the specific port (e.g., 'out1' or 'out2')

                # Assign attributes based on the source port
                if source_port == 'out1':
                    if 'p_out1' in heat_exchanger_config:
                        connection_attributes['p'] = heat_exchanger_config['p_out1']
                    if 'p0_out1' in heat_exchanger_config:
                        connection_attributes['p0'] = heat_exchanger_config['p0_out1']
                    if 'h0_out1' in heat_exchanger_config:
                        connection_attributes['h0'] = heat_exchanger_config['h0_out1']
                    if 'T_out1' in heat_exchanger_config:
                        connection_attributes['T'] = heat_exchanger_config['T_out1']
                    if 'vapor_mass_fraction_out1' in heat_exchanger_config:
                        connection_attributes['x'] = heat_exchanger_config['vapor_mass_fraction_out1']
                    if 'fluid_out1' in heat_exchanger_config:
                        connection_attributes['fluid'] = heat_exchanger_config['fluid_out1']
                elif source_port == 'out2':
                    if 'p_out2' in heat_exchanger_config:
                        connection_attributes['p'] = heat_exchanger_config['p_out2']
                    if 'p0_out2' in heat_exchanger_config:
                        connection_attributes['p0'] = heat_exchanger_config['p0_out2']
                    if 'h0_out2' in heat_exchanger_config:
                        connection_attributes['h0'] = heat_exchanger_config['h0_out2']
                    if 'T_out2' in heat_exchanger_config:
                        connection_attributes['T'] = heat_exchanger_config['T_out2']
                    if 'vapor_mass_fraction_out2' in heat_exchanger_config:
                        connection_attributes['x'] = heat_exchanger_config['vapor_mass_fraction_out2']
                    if 'fluid_out2' in heat_exchanger_config:
                        connection_attributes['fluid'] = heat_exchanger_config['fluid_out2']

            # Finally, set the connection attributes
            connection.set_attr(**connection_attributes)

    def _BAC_regression_model(self, coeffs: list) -> float:
        r"""
        Computes the parasitic power fraction using a BAC regression model.

        Args:
            coeffs (list): Coefficients for the regression model.

        Returns:
            float: Parasitic power fraction.

        Formula:
            .. math::
                f = \frac{a}{\Delta T_{\text{approach}}} + b \cdot T_{\text{ambient}} + c \cdot \frac{T_{\text{ambient}}}{\Delta T_{\text{approach}}} + \frac{d}{\Delta T_{\text{approach}} + \Delta T_{\text{range}}}

        Where:
            - \( a, b, c, d \): Regression coefficients.
            - \( T_{\text{ambient}} \): Ambient temperature (\(^\circ\text{C}\)).
            - \( \Delta T_{\text{approach}} \): Approach temperature difference (\(^\circ\text{C}\)).
            - \( \Delta T_{\text{range}} \): Condensation temperature range (\(^\circ\text{C}\)).
        """
        a, b, c, d = coeffs
        T_ambient = self.pp_specs.surface_temperature
        dT_approach = self.pp_specs.approach_temperature
        dT_range = self.pp_specs.temperature_range
        return a / dT_approach + b * T_ambient + c * T_ambient / dT_approach + d / (dT_approach + dT_range)

    def _get_parasitic_power_fraction_cooling(self):
        """
        Computes the parasitic power fraction for cooling.

        Returns:
            float: Cooling parasitic power fraction.
        """
        return self._BAC_regression_model(coeffs=self._coeffs_cooling_power)

    def _get_parasitic_power_fraction_condensing(self):
        """
        Computes the parasitic power fraction for condensing.

        Returns:
            float: Condensing parasitic power fraction.
        """
        return self._BAC_regression_model(coeffs=self._coeffs_condensing_power)

    def calculate_net_power(self):
        gross_power_output = 0.0
        auxiliary_power_consumption = 0.0

        # Sum up power output from turbines
        for node_name, node in self.nodes.items():
            if isinstance(node, Turbine):
                gross_power_output += -node.P.val  # Turbine output power is negative in TESPy

        # Sum up power consumption from compressors (pumps)
        for node_name, node in self.nodes.items():
            if isinstance(node, Compressor):  # Pumps are modeled as compressors in TESPy
                auxiliary_power_consumption += node.P.val  # Pump input power is negative in TESPy

        # Include cooler and condenser power consumption
        w_cooler, w_condenser = self.compute_cooler_condenser_power()
        auxiliary_power_consumption += w_cooler + w_condenser

        # Calculate net power
        net_power = gross_power_output - auxiliary_power_consumption

        return net_power


    # def compute_cooler_condenser_power(self):
    #     w_cooler = w_condenser = 0.0  # Initialize values to prevent unbound errors
    #     q_cooler = q_condenser = 0.0
    #     for node_name, node in self.nodes.items():
    #         if isinstance(node, SimpleHeatExchanger):
    #             component_config = self.config.get(node_name, {})
    #             subtype = component_config.get('Subtype', '').lower()
    #
    #             if subtype == 'cooler':
    #                 q_cooler += -node.Q.val  # Assuming TESPy gives heat load as a positive value
    #                 f_cooling = self._get_parasitic_power_fraction_cooling()
    #                 w_cooler = q_cooler * f_cooling
    #             elif subtype == 'condenser':
    #                 q_condenser += -node.Q.val  # Assuming TESPy gives heat load as a positive value
    #                 f_condensing = self._get_parasitic_power_fraction_condensing()
    #                 w_condenser = q_condenser * f_condensing
    #
    #     return w_cooler, w_condenser

    def compute_cooler_condenser_power(self):
        # Initialize variables
        w_cooler = w_condenser = 0.0  # Power
        q_cooler = q_condenser = 0.0  # Heat load

        for node_name, node in self.nodes.items():
            if isinstance(node, SimpleHeatExchanger):
                component_config = self.config.get(node_name, {})
                subtype = component_config.get('Subtype', '').lower()

                if subtype in ['cooler', 'condenser']:
                    # Extract and validate cooling tower mode
                    tower_mode = component_config.get('cooling_tower_mode', '').upper()
                    if tower_mode not in ['WET', 'DRY']:
                        raise ValueError(f"Invalid cooling_tower_mode '{tower_mode}' in component_config for {node_name}")

                    # Set the cooling tower mode based on the first valid cooler/condenser
                    self._surface_cooling_tower_mode = tower_mode

                    # Set coefficients based on tower mode
                    if self._surface_cooling_tower_mode == 'WET':
                        self._coeffs_cooling_power = [1.2, 0.0, -3.79e-3, 1.95e-2]
                        self._coeffs_condensing_power = [1.65, -6.24e-6, -5.03e-3, 0.0]
                    elif self._surface_cooling_tower_mode == 'DRY':
                        self._coeffs_cooling_power = [7.65e-1, 0.0, 0.0, 1.28e-1]
                        self._coeffs_condensing_power = [0.619, 0.0, 0.0, 0.0]

                    # Calculate heat loads and parasitic power
                    if subtype == 'cooler':
                        q_cooler += -node.Q.val  # Assume TESPy gives heat load as positive
                        f_cooling = self._get_parasitic_power_fraction_cooling()
                        w_cooler = q_cooler * f_cooling
                    elif subtype == 'condenser':
                        q_condenser += -node.Q.val  # Assume TESPy gives heat load as positive
                        f_condensing = self._get_parasitic_power_fraction_condensing()
                        w_condenser = q_condenser * f_condensing

        return w_cooler, w_condenser

    # def generate_output_table(self):
    #     """
    #     Generates and prints a table showing system information:
    #     Units, Ports, Pressure, Temperature, Enthalpy, and Mass Rate.
    #     """
    #     graph_nodes = self.nodes
    #     graph_edges = [(conn.source.label, conn.target.label) for conn in self.connections]
    #
    #     table_data = []
    #     headers = ["Unit", "Port", "Pressure (MPa)", "Temperature (°C)", "Enthalpy (kJ/kg)", "Mass Rate (kg/s)"]
    #
    #     for edge in graph_edges:
    #         source, target = edge
    #         source_unit = graph_nodes[source]
    #         target_unit = graph_nodes[target]
    #
    #         # Handle outlet data
    #         try:
    #             outlet_fluid = getattr(source_unit, 'outl', [])[0].fluid.val
    #             outlet_P = getattr(source_unit, 'outl', [])[0].p.val / 10  # Convert to MPa
    #             outlet_T = getattr(source_unit, 'outl', [])[0].T.val
    #             outlet_H = getattr(source_unit, 'outl', [])[0].h.val   # Convert to kJ/kg
    #             mass_rate = getattr(source_unit, 'outl', [])[0].m.val
    #             table_data.append([source, "Outlet", outlet_P, outlet_T, outlet_H, mass_rate])
    #         except AttributeError:
    #             table_data.append([source, "Outlet", "Error", "Error", "Error", "N/A"])
    #
    #         # Handle inlet data
    #         try:
    #             inlet_fluid = getattr(target_unit, 'inl', [])[0].fluid.val
    #             inlet_P = getattr(target_unit, 'inl', [])[0].p.val / 10  # Convert to MPa
    #             inlet_T = getattr(target_unit, 'inl', [])[0].T.val  # Convert to Celsius
    #             inlet_H = getattr(target_unit, 'inl', [])[0].h.val  # Convert to kJ/kg
    #             mass_rate = getattr(target_unit, 'inl', [])[0].m.val
    #             table_data.append([target, "Inlet", inlet_P, inlet_T, inlet_H, mass_rate])
    #         except AttributeError:
    #             table_data.append([target, "Inlet", "Error", "Error", "Error", "N/A"])
    #
    #     # Rearrange table for better presentation
    #     if table_data:
    #         last_row = table_data.pop()
    #         table_data.insert(0, last_row)
    #
    #     # Assign colors to units
    #     available_colors = ["cyan", "green", "yellow", "red", "blue", "magenta", "white"]
    #     unit_names = list(graph_nodes.keys())
    #     color_map = {unit: color for unit, color in zip(unit_names, cycle(available_colors))}
    #
    #     colored_table_data = []
    #     for row in table_data:
    #         unit_color = color_map.get(row[0], "white")
    #         colored_row = [colored(str(cell), unit_color, attrs=["bold"]) for cell in row]
    #         colored_table_data.append(colored_row)
    #
    #     # Print the formatted table
    #     top_border = "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+"
    #     print(top_border)
    #     print(tabulate(colored_table_data, headers=headers, tablefmt="fancy_grid", colalign=("center", "center", "center", "center", "center", "center")).replace("─", " "))
    #     print(top_border)


    def generate_output_table(self):
        """
        Generates and prints a table showing system information:
        Units, Ports, Pressure, Temperature, Enthalpy, and Mass Rate.
        """
        graph_nodes = self.nodes
        graph_edges = [(conn.source.label, conn.target.label) for conn in self.connections]

        table_data = []
        headers = ["Unit", "Port", "Pressure (MPa)", "Temperature (°C)", "Enthalpy (kJ/kg)", "Mass Rate (kg/s)"]

        processed_ports = set()
        for edge in graph_edges:
            source, target = edge
            source_unit = graph_nodes[source]
            target_unit = graph_nodes[target]

            # Process source unit outlets
            for idx, outlet in enumerate(getattr(source_unit, 'outl', [])):
                port_key = (source, f"Outlet-{idx + 1}")
                if port_key not in processed_ports:
                    processed_ports.add(port_key)
                    table_data.append([source, f"Outlet-{idx + 1}", outlet.p.val / 10, outlet.T.val, outlet.h.val, outlet.m.val])

            # Process target unit inlets
            for idx, inlet in enumerate(getattr(target_unit, 'inl', [])):
                port_key = (target, f"Inlet-{idx + 1}")
                if port_key not in processed_ports:
                    processed_ports.add(port_key)
                    table_data.append([target, f"Inlet-{idx + 1}", inlet.p.val / 10, inlet.T.val, inlet.h.val, inlet.m.val])

        # Rearrange table for better presentation
        if table_data:
            last_row = table_data.pop()
            table_data.insert(0, last_row)

        # Assign colors to units
        available_colors = ["cyan", "green", "yellow", "red", "blue", "magenta", "white"]
        unit_names = list(graph_nodes.keys())
        color_map = {unit: color for unit, color in zip(unit_names, cycle(available_colors))}

        colored_table_data = []
        for row in table_data:
            unit_color = color_map.get(row[0], "white")
            colored_row = [colored(str(cell), unit_color, attrs=["bold"]) for cell in row]
            colored_table_data.append(colored_row)

        # Print the formatted table
        top_border = "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+"
        print(top_border)
        print(tabulate(colored_table_data, headers=headers, tablefmt="fancy_grid", colalign=("center", "center", "center", "center", "center", "center")).replace("\u2500", " "))
        print(top_border)



    def get_outlet_conditions(self):
        """
        Retrieves the outlet pressure and temperature from the results of the network calculation.

        Returns:
            dict: Outlet conditions with keys `pressure` (in MPa) and `temperature` (in °C).
                  If the outlet node is not properly calculated, the values will be `None`.
        """
        outlet_conditions = {
            "pressure": None,
            "temperature": None
        }

        # Find the outlet node (Sink) and its incoming connection
        for connection in self.connections:
            if isinstance(connection.target, Sink) and connection.target.label == "outlet":
                try:
                    # Extract pressure (in MPa) and temperature (in °C)
                    outlet_conditions["pressure"] = connection.p.val / 10  # Convert Pa to MPa
                    outlet_conditions["temperature"] = connection.T.val  # Convert K to °C
                except AttributeError:
                    # If attributes are missing, values remain None
                    pass
                break  # Exit after finding the outlet

        return outlet_conditions
