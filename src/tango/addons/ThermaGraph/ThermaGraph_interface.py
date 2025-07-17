from tango.addons.base import *
import subprocess
import os
import json


class ThermaGraph_addon(TangoAddon):
    def __init__(self, graph, results):
        super().__init__(graph, results)

    def post_process(self, specs):
        self.fluid_name = getattr(specs, 'fluid_name', 'CO2')
        if self.graph.get('power_plant_graph', {}):  # Check if `power_plant_graph` exists and is not empty
            self.post_process2(specs)
        else:
            self.post_process1(specs)

    def post_process1(self, specs):
        """
        Generate two JSON files based on the graph and results.
        """

        self.states_file = specs.states_file
        self.connections_file = specs.connections_file

        # Extract nodes and edges
        nodes = self.graph['main_graph'].get('nodes', {})
        edges = self.graph['main_graph'].get('edges', {})

        num_points = len(self.results['date'])
        components = {}

        for node_name, node_data in nodes.items():
            node_type = node_data['type']
            pressure_key = f"{node_type}_P"
            enthalpy_key = f"{node_type}_H"

            if pressure_key in self.results and enthalpy_key in self.results:
                pressures = [round(p / 1e5, 2) for p in self.results[pressure_key]]  # Convert to bar
                enthalpies = [round(h / 1e3, 2) for h in self.results[enthalpy_key]]  # Convert to kJ/kg

                components[node_name] = [
                    [pressures[i], enthalpies[i]] for i in range(num_points)
                ]

        connections = []
        for edge_id, edge_data in edges.items():
            source = edge_data['source']
            target = edge_data['target']
            connections.append([source, target, "non-isentropic"])

        with open(self.states_file, 'w') as file1:
            json.dump(components, file1, indent=4)

        with open(self.connections_file, 'w') as file2:
            json.dump(connections, file2, indent=4)

        print("JSON files generated.")

    def post_process2(self, specs):
        """
        Generate two JSON files based on the combined graph and results.
        Handles both `main_graph` and `power_plant_graph` by merging them and adjusting connections
        according to the specified logic.
        """
        import json

        self.states_file = specs.states_file
        self.connections_file = specs.connections_file

        # Extract nodes and edges
        nodes = self.graph['main_graph'].get('nodes', {})
        edges = self.graph['main_graph'].get('edges', {})
        power_plant_nodes = self.graph['power_plant_graph'].get('nodes', {})
        power_plant_edges = self.graph['power_plant_graph'].get('edges', {})
        surface_target = None
        surface_source = None

        for edge_id, edge_data in edges.items():
            if edge_data['target'] == 'surface':
                surface_source = edge_data['source']
            elif edge_data['source'] == 'surface':
                surface_target = edge_data['target']

        outlet_source = None
        inlet_target = None
        for edge_id, edge_data in power_plant_edges.items():
            if edge_data['target'] == 'outlet':
                outlet_source = edge_data['source']
            elif edge_data['source'] == 'inlet':
                inlet_target = edge_data['target']

        if outlet_source and surface_target:
            new_edge_id = max(edges.keys()) + 1 if edges else 1
            edges[new_edge_id] = {'source': outlet_source, 'target': surface_target}

        if surface_source and inlet_target:
            new_edge_id = max(edges.keys()) + 1
            edges[new_edge_id] = {'source': surface_source, 'target': inlet_target}

        surface_connections = [edge_id for edge_id, edge_data in edges.items() if 'surface' in (edge_data['source'], edge_data['target'])]
        for edge_id in surface_connections:
            del edges[edge_id]
        if 'surface' in nodes:
            del nodes['surface']

        for edge_id, edge_data in power_plant_edges.items():
            if edge_data['source'] != 'inlet' and edge_data['target'] != 'outlet':
                new_edge_id = max(edges.keys()) + 1
                edges[new_edge_id] = edge_data

        combined_nodes = {**nodes, **power_plant_nodes}
        combined_edges = edges
        num_points = len(self.results['date'])
        components = {}
        multi_outlet_nodes = {}

        for edge_id, edge_data in power_plant_edges.items():
            source = edge_data['source']
            source_port = edge_data.get('source_port', 'out')

            if source not in multi_outlet_nodes:
                multi_outlet_nodes[source] = set()
            multi_outlet_nodes[source].add(source_port)

        for node_name, node_data in combined_nodes.items():
            if node_name in multi_outlet_nodes and len(multi_outlet_nodes[node_name]) > 1:
                for outlet_suffix in ['out1', 'out2']:
                    new_node_name = f"{node_name}_{outlet_suffix}"
                    pressure_key = f"{node_name}_outlet{outlet_suffix[-1]}_pressure"
                    enthalpy_key = f"{node_name}_outlet{outlet_suffix[-1]}_enthalpy"

                    if pressure_key not in self.results or enthalpy_key not in self.results:
                        continue

                    pressures = [round(p / 1e5, 2) for p in self.results[pressure_key]]  # Convert to bar
                    enthalpies = [round(h / 1e3, 2) for h in self.results[enthalpy_key]]  # Convert to kJ/kg

                    components[new_node_name] = [[pressures[i], enthalpies[i]] for i in range(num_points)]
            else:
                node_type = node_data['type']
                pressure_key = f"{node_type}_P"
                enthalpy_key = f"{node_type}_H"

                if pressure_key not in self.results or enthalpy_key not in self.results:
                    pressure_key = f"{node_name}_outlet1_pressure"
                    enthalpy_key = f"{node_name}_outlet1_enthalpy"

                if pressure_key not in self.results or enthalpy_key not in self.results:
                    continue

                pressures = [round(p / 1e5, 2) for p in self.results[pressure_key]]  # Convert to bar
                enthalpies = [round(h / 1e3, 2) for h in self.results[enthalpy_key]]  # Convert to kJ/kg
                components[node_name] = [[pressures[i], enthalpies[i]] for i in range(num_points)]

        modified_edges = {}

        for edge_id, edge_data in combined_edges.items():
            source = edge_data['source']
            target = edge_data['target']
            source_port = edge_data.get('source_port', 'out')

            if source in multi_outlet_nodes and len(multi_outlet_nodes[source]) > 1:
                # Determine the correct outlet based on the original source_port
                if source_port == 'out1':
                    modified_edges[edge_id] = {
                        'source': f"{source}_out1",
                        'target': target,
                        'source_port': source_port,
                        'target_port': edge_data.get('target_port', 'in')
                    }
                elif source_port == 'out2':
                    modified_edges[edge_id] = {
                        'source': f"{source}_out2",
                        'target': target,
                        'source_port': source_port,
                        'target_port': edge_data.get('target_port', 'in')
                    }
            else:
                # If it's not a multi-outlet node, keep the edge unchanged
                modified_edges[edge_id] = edge_data

        # Add new edges for multi-outlet targets without duplication
        for edge_id, edge_data in power_plant_edges.items():
            target = edge_data['target']

            if target in multi_outlet_nodes and len(multi_outlet_nodes[target]) > 1:
                num_outlets = len(multi_outlet_nodes[target])  # Count the number of unique outlet ports
                for i in range(1, num_outlets + 1):
                    new_edge = {
                        'source': edge_data['source'],
                        'target': f"{target}_out{i}",
                        'source_port': edge_data.get('source_port', 'out'),
                        'target_port': edge_data.get('target_port', 'in')
                    }

                    # Ensure no duplicate edges are added to modified_edges
                    if not any(
                        existing_edge['source'] == new_edge['source'] and
                        existing_edge['target'] == new_edge['target']
                        for existing_edge in modified_edges.values()
                    ):
                        new_edge_id = max(modified_edges.keys(), default=0) + 1
                        modified_edges[new_edge_id] = new_edge

        # print("Final modified_edges with multi-outlet handling:")
        # for edge_id, edge_data in modified_edges.items():
        #     print(f"{edge_id}: {edge_data}")

        combined_edges = modified_edges

        connections = []
        for edge_id, edge_data in combined_edges.items():
            source = edge_data['source']
            target = edge_data['target']
            connections.append([source, target, "non-isentropic"])

        with open(self.states_file, 'w') as file1:
            json.dump(components, file1, indent=4)

        with open(self.connections_file, 'w') as file2:
            json.dump(connections, file2, indent=4)

        print("JSON files generated.")

    def execute(self):
        """
        Execute the add-on by launching the PyQt module with the generated files.
        """
        components_file = os.path.abspath(self.states_file)
        connections_file = os.path.abspath(self.connections_file)
        fluid_name = getattr(self, 'fluid_name', 'CO2')

        try:
            subprocess.run(
                ['python', '/Users/morteza/Documents/projects/TANGO/src/tango/addons/ThermaGraph/Frame.py', components_file, connections_file, fluid_name],
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error launching PyQt module: {e}")
            raise
