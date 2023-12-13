from tespy.components import Sink, Source, Turbine, SimpleHeatExchanger, Compressor
from tespy.connections import Connection
from tespy.networks import Network
import yaml


class PowerPlantBase:

    def __init__(self, yaml_file_path):

        self.nw = Network(p_unit='bar', T_unit='C', h_unit='kJ / kg', iterinfo=False)
        self.components, self.connections = self.read_yaml_file(yaml_file_path)
        for connection in self.connections.values():
            self.nw.add_conns(connection)

        self.set_attributes_and_solve()

    def read_yaml_file(self, yaml_file_path):
        with open(yaml_file_path, 'r') as file:
            yaml_data = file.read()
        data = yaml.safe_load(yaml_data)

        component_data = [
            (component_type, data.get(component_type, {}))
            for component_type, node in data['power_plant_graph']['nodes'].items()
        ]
        connections_list = [
            (data['power_plant_graph']['edges'][edge]['source'],
             data['power_plant_graph']['edges'][edge]['target'],
             data['power_plant_graph']['edges'][edge].get('attributes', {}))
            for edge in data['power_plant_graph']['edges']
        ]

        components = self.create_components(component_data, data)
        connections = self.create_connections(connections_list, components)

        return components, connections

    def create_components(self, component_data, data):
        component_types = {
            name: globals().get(node['type'])
            for name, node in data['power_plant_graph']['nodes'].items()
        }
        components = {}
        for data in component_data:
            name, attr = data[0], data[1] if len(data) > 1 else {}
            if name in component_types:
                components[name] = component_types[name](name)
                components[name].set_attr(**attr)

        return components

    def create_connections(self, connections_list, components):
        connection_instances = {}
        for conn in connections_list:
            from_component, to_component, attr = conn[0], conn[1], conn[2] if len(conn) > 2 else {}
            from_instance = components.get(from_component)
            to_instance = components.get(to_component)
            if from_instance is not None and to_instance is not None:
                # Create a connection instance and set attributes
                connection_name = f"{from_component}_{to_component}"
                connection_instances[connection_name] = Connection(from_instance, 'out1', to_instance, 'in1')
                connection_instances[connection_name].set_attr(**attr)

        return connection_instances

    def set_attributes_and_solve(self):
        self.nw.solve('design')
        self.nw.print_results()


# yaml_file_path = '/Users/morteza/PycharmProjects/tespy/belphi2.yml'
# yaml_file_path = '/Users/morteza/Documents/projects/TANGO/examples/testcase1.yml'
# pp = PowerPlantBase(yaml_file_path)
# print(pp.components['turbine'].P.val)

