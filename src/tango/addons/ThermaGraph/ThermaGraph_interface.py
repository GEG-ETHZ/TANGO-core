from tango.addons.base import *
import subprocess
import os
import json

class ThermaGraph_addon(TangoAddon):
    def __init__(self, graph, results):
        super().__init__(graph, results)

    def post_process(self, specs):
        """
        Generate two JSON files based on the graph and results.
        """

        self.states_file = specs.states_file
        self.connections_file = specs.connections_file

        # Extract nodes and edges
        nodes = self.graph.get('nodes', {})
        edges = self.graph.get('edges', {})

        # Determine the number of data points from the results
        num_points = len(self.results['date'])

        # Create data structure for the first JSON file (pressures and enthalpies)
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

        # Create data structure for the second JSON file (connections)
        connections = []
        for edge_id, edge_data in edges.items():
            source = edge_data['source']
            target = edge_data['target']
            connections.append([source, target, "non-isentropic"])

        # Write the first JSON file
        with open(self.states_file, 'w') as file1:
            json.dump(components, file1, indent=4)

        # Write the second JSON file
        with open(self.connections_file, 'w') as file2:
            json.dump(connections, file2, indent=4)

        print("JSON files generated.")

    def execute(self):
        """
        Execute the add-on by launching the PyQt module with the generated files.
        """

        components_file = os.path.abspath(self.states_file)
        connections_file = os.path.abspath(self.connections_file)

        try:
            subprocess.run(
                ['python', '/Users/morteza/Documents/projects/TANGO/src/tango/addons/ThermaGraph/Frame.py', components_file, connections_file],
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error launching PyQt module: {e}")
            raise




