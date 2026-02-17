"""ThermaGraph addon for TANGO phase diagram generation.

This addon generates phase diagrams (P-h, T-s, etc.) showing simulation
state points and connections overlaid on thermodynamic curves.

IMPORTANT DESIGN NOTES:
- post_process(): Generates JSON files with state data for visualization
- execute(): Launches PyQt5 UI or saves SVG in batch mode
- TANGO-APP INTEGRATION: The SVG output is consumed by tango-app via ArangoDB,
  NOT via file paths. The workflow calls _write_phase_diagram_data() which reads
  the SVG and stores svg_content in the 'phase_diagram' collection.
- For headless servers without a display, you can use xvfb-run externally:
  `xvfb-run -a python -c "from ThermaGraph_interface import ..."`
"""

from tango.addons.base import TangoAddon
import os
import json
import sys


class ThermaGraph_addon(TangoAddon):
    """Addon for generating thermodynamic phase diagrams.

    Generates visual representations of simulation state points on
    thermodynamic diagrams (log P-h, T-s, h-s, etc.).

    Data Flow to tango-app:
        1. post_process() generates JSON files (states, connections)
        2. execute() generates SVG file (when auto_save_svg='yes')
        3. native_workflow._write_phase_diagram_data() reads SVG
        4. arangodb_manager stores svg_content in 'phase_diagram' collection
        5. tango-app fetches via getPhaseDiagramData() API

    Attributes:
        graph: Merged graph structure with main_graph and power_plant_graph
        results: Dictionary of simulation results by timestep
        states_file: Path to JSON file with state point data
        connections_file: Path to JSON file with connection data
        fluid_name: Working fluid (default: CO2)
    """

    def __init__(self, graph, results):
        super().__init__(graph, results)

    def post_process(self, specs):
        self.fluid_name = getattr(specs, "fluid_name", "CO2")
    
        # CRITICAL FIX: Copy execution parameters from specs to self so execute() can use them
        # Handle specs being either an object or a dictionary
        print(f"DEBUG: ThermaGraph post_process called with specs type: {type(specs)}")
        if isinstance(specs, dict):
            print(f"DEBUG: Specs keys: {specs.keys()}")
            self.svg_filename = specs.get("svg_filename", "")
            self.auto_save_svg = specs.get("auto_save_svg", "no")
        else:
            print(f"DEBUG: Specs dict: {specs.__dict__ if hasattr(specs, '__dict__') else 'no __dict__'}")
            self.svg_filename = getattr(specs, "svg_filename", "")
            self.auto_save_svg = getattr(specs, "auto_save_svg", "no")

        print(f"DEBUG: ThermaGraph configured - auto_save_svg={self.auto_save_svg}, svg_filename={self.svg_filename}")
            
        if self.graph.get(
            "power_plant_graph", {}
        ):  # Check if `power_plant_graph` exists and is not empty
            self.post_process2(specs)
        else:
            self.post_process1(specs)

    def post_process1(self, specs):
        """
        Generate two JSON files based on the graph and results.
        """
        from tango.addons.utils import resolve_addon_output_path

        # Use output_dir from specs if provided (injected by workflow), else default
        output_dir = getattr(specs, "output_dir", None) or "output"

        self.states_file = resolve_addon_output_path(
            getattr(specs, "states_file", None), "thermagraph_states.json", output_dir
        )
        self.connections_file = resolve_addon_output_path(
            getattr(specs, "connections_file", None),
            "thermagraph_connections.json",
            output_dir,
        )

        # Extract nodes and edges
        nodes = self.graph["main_graph"].get("nodes", {})
        edges = self.graph["main_graph"].get("edges", {})

        num_points = len(self.results["date"])
        components = {}

        for node_name, node_data in nodes.items():
            node_type = node_data["type"]
            pressure_key = f"{node_type}_P"
            enthalpy_key = f"{node_type}_H"

            if pressure_key in self.results and enthalpy_key in self.results:
                pressures = [
                    round(p / 1e5, 2) for p in self.results[pressure_key]
                ]  # Convert to bar
                enthalpies = [
                    round(h / 1e3, 2) for h in self.results[enthalpy_key]
                ]  # Convert to kJ/kg

                components[node_name] = [
                    [pressures[i], enthalpies[i]] for i in range(num_points)
                ]

        connections = []
        for edge_id, edge_data in edges.items():
            source = edge_data["source"]
            target = edge_data["target"]
            connections.append([source, target, "non-isentropic"])

        # Ensure directory exists
        os.makedirs(os.path.dirname(self.states_file), exist_ok=True)

        with open(self.states_file, "w") as file1:
            json.dump(components, file1, indent=4)

        with open(self.connections_file, "w") as file2:
            json.dump(connections, file2, indent=4)

        print("JSON files generated.")

    def post_process2(self, specs):
        """
        Generate two JSON files based on the combined graph and results.
        Handles both `main_graph` and `power_plant_graph` by merging them and adjusting connections
        according to the specified logic.
        """
        import json
        from tango.addons.utils import resolve_addon_output_path

        # Use output_dir from specs if provided (injected by workflow), else default
        output_dir = getattr(specs, "output_dir", None) or "output"

        self.states_file = resolve_addon_output_path(
            getattr(specs, "states_file", None), "thermagraph_states.json", output_dir
        )
        self.connections_file = resolve_addon_output_path(
            getattr(specs, "connections_file", None),
            "thermagraph_connections.json",
            output_dir,
        )

        # Extract nodes and edges
        nodes = self.graph["main_graph"].get("nodes", {})
        edges = self.graph["main_graph"].get("edges", {})
        power_plant_nodes = self.graph["power_plant_graph"].get("nodes", {})
        power_plant_edges = self.graph["power_plant_graph"].get("edges", {})
        surface_target = None
        surface_source = None

        for edge_id, edge_data in edges.items():
            if edge_data["target"] == "surface":
                surface_source = edge_data["source"]
            elif edge_data["source"] == "surface":
                surface_target = edge_data["target"]

        outlet_source = None
        inlet_target = None
        for edge_id, edge_data in power_plant_edges.items():
            if edge_data["target"] == "outlet":
                outlet_source = edge_data["source"]
            elif edge_data["source"] == "inlet":
                inlet_target = edge_data["target"]

        if outlet_source and surface_target:
            new_edge_id = max(edges.keys()) + 1 if edges else 1
            edges[new_edge_id] = {"source": outlet_source, "target": surface_target}

        if surface_source and inlet_target:
            new_edge_id = max(edges.keys()) + 1
            edges[new_edge_id] = {"source": surface_source, "target": inlet_target}

        surface_connections = [
            edge_id
            for edge_id, edge_data in edges.items()
            if "surface" in (edge_data["source"], edge_data["target"])
        ]
        for edge_id in surface_connections:
            del edges[edge_id]
        if "surface" in nodes:
            del nodes["surface"]

        for edge_id, edge_data in power_plant_edges.items():
            if edge_data["source"] != "inlet" and edge_data["target"] != "outlet":
                new_edge_id = max(edges.keys()) + 1
                edges[new_edge_id] = edge_data

        combined_nodes = {**nodes, **power_plant_nodes}
        combined_edges = edges
        num_points = len(self.results["date"])
        components = {}
        multi_outlet_nodes = {}

        for edge_id, edge_data in power_plant_edges.items():
            source = edge_data["source"]
            source_port = edge_data.get("source_port", "out")

            if source not in multi_outlet_nodes:
                multi_outlet_nodes[source] = set()
            multi_outlet_nodes[source].add(source_port)

        for node_name, node_data in combined_nodes.items():
            if (
                node_name in multi_outlet_nodes
                and len(multi_outlet_nodes[node_name]) > 1
            ):
                for outlet_suffix in ["out1", "out2"]:
                    new_node_name = f"{node_name}_{outlet_suffix}"
                    pressure_key = f"{node_name}_outlet{outlet_suffix[-1]}_pressure"
                    enthalpy_key = f"{node_name}_outlet{outlet_suffix[-1]}_enthalpy"

                    if (
                        pressure_key not in self.results
                        or enthalpy_key not in self.results
                    ):
                        continue

                    pressures = [
                        round(p / 1e5, 2) for p in self.results[pressure_key]
                    ]  # Convert to bar
                    enthalpies = [
                        round(h / 1e3, 2) for h in self.results[enthalpy_key]
                    ]  # Convert to kJ/kg

                    components[new_node_name] = [
                        [pressures[i], enthalpies[i]] for i in range(num_points)
                    ]
            else:
                node_type = node_data["type"]
                pressure_key = f"{node_type}_P"
                enthalpy_key = f"{node_type}_H"

                if pressure_key not in self.results or enthalpy_key not in self.results:
                    pressure_key = f"{node_name}_outlet1_pressure"
                    enthalpy_key = f"{node_name}_outlet1_enthalpy"

                if pressure_key not in self.results or enthalpy_key not in self.results:
                    continue

                pressures = [
                    round(p / 1e5, 2) for p in self.results[pressure_key]
                ]  # Convert to bar
                enthalpies = [
                    round(h / 1e3, 2) for h in self.results[enthalpy_key]
                ]  # Convert to kJ/kg
                components[node_name] = [
                    [pressures[i], enthalpies[i]] for i in range(num_points)
                ]

        modified_edges = {}

        for edge_id, edge_data in combined_edges.items():
            source = edge_data["source"]
            target = edge_data["target"]
            source_port = edge_data.get("source_port", "out")

            if source in multi_outlet_nodes and len(multi_outlet_nodes[source]) > 1:
                # Determine the correct outlet based on the original source_port
                if source_port == "out1":
                    modified_edges[edge_id] = {
                        "source": f"{source}_out1",
                        "target": target,
                        "source_port": source_port,
                        "target_port": edge_data.get("target_port", "in"),
                    }
                elif source_port == "out2":
                    modified_edges[edge_id] = {
                        "source": f"{source}_out2",
                        "target": target,
                        "source_port": source_port,
                        "target_port": edge_data.get("target_port", "in"),
                    }
            else:
                # If it's not a multi-outlet node, keep the edge unchanged
                modified_edges[edge_id] = edge_data

        # Add new edges for multi-outlet targets without duplication
        for edge_id, edge_data in power_plant_edges.items():
            target = edge_data["target"]

            if target in multi_outlet_nodes and len(multi_outlet_nodes[target]) > 1:
                num_outlets = len(
                    multi_outlet_nodes[target]
                )  # Count the number of unique outlet ports
                for i in range(1, num_outlets + 1):
                    new_edge = {
                        "source": edge_data["source"],
                        "target": f"{target}_out{i}",
                        "source_port": edge_data.get("source_port", "out"),
                        "target_port": edge_data.get("target_port", "in"),
                    }

                    # Ensure no duplicate edges are added to modified_edges
                    if not any(
                        existing_edge["source"] == new_edge["source"]
                        and existing_edge["target"] == new_edge["target"]
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
            source = edge_data["source"]
            target = edge_data["target"]
            connections.append([source, target, "non-isentropic"])

        # Ensure directory exists
        os.makedirs(os.path.dirname(self.states_file), exist_ok=True)

        with open(self.states_file, "w") as file1:
            json.dump(components, file1, indent=4)

        with open(self.connections_file, "w") as file2:
            json.dump(connections, file2, indent=4)

        print("JSON files generated.")

    def execute(self, step_index=None):
        """
        Execute the add-on by launching the PyQt interactive diagram plotter.

        This method directly imports and calls the Frame module rather than
        spawning a subprocess, which is cleaner and avoids environment issues.
        """
        # Handle headless execution for batch mode EARLY, before any imports
        # that might initialize Qt (like matplotlib.backends.backend_qt5agg)
        auto_save_svg = getattr(self, "auto_save_svg", "no")
        print(f"DEBUG EXECUTE: auto_save_svg={auto_save_svg}")
        if auto_save_svg == "yes":
            # If no display is available, force offscreen platform
            if sys.platform != "win32" and not os.environ.get("DISPLAY"):
                os.environ["QT_QPA_PLATFORM"] = "offscreen"
                print(f"ThermaGraph: Headless mode detected. Set QT_QPA_PLATFORM={os.environ.get('QT_QPA_PLATFORM')}")
            elif os.environ.get("QT_QPA_PLATFORM") == "offscreen":
                 print(f"ThermaGraph: QT_QPA_PLATFORM already set to 'offscreen'")
        components_file = os.path.abspath(self.states_file)
        connections_file = os.path.abspath(self.connections_file)
        fluid_name = getattr(self, "fluid_name", "CO2")
        auto_save_svg = getattr(self, "auto_save_svg", "no")
        svg_filename = getattr(self, "svg_filename", "")
        print(f"DEBUG EXECUTE: fluid={fluid_name}, svg_filename={svg_filename}")

        if not os.path.exists(components_file):
            print(f"Error: Components file does not exist: {components_file}")
            return
        if not os.path.exists(connections_file):
            print(f"Error: Connections file does not exist: {connections_file}")
            return

        # Add the ThermaGraph directory to path for relative imports in Frame.py
        thermagraph_dir = os.path.dirname(os.path.abspath(__file__))
        if thermagraph_dir not in sys.path:
            sys.path.insert(0, thermagraph_dir)

        from tango.addons.ThermaGraph.Frame import MainWindow
        from PyQt5.QtWidgets import QApplication

        # Reuse existing QApplication if possible (singleton)
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        # Helper to prevent GC
        self.window = MainWindow(default_fluid=fluid_name)
        self.window.load_files(components_file, connections_file)

        if auto_save_svg == "yes" and svg_filename:
            try:
                os.makedirs(os.path.dirname(svg_filename), exist_ok=True)
                self.window.canvas.figure.savefig(svg_filename, format="svg")
                print(f"SVG successfully saved to: {svg_filename}")
            except Exception as e:
                print(f"Error saving SVG: {e}")
            return  # Exit without showing UI in batch mode

        # Interactive mode - show UI
        # Interactive mode - show UI only if NOT headless
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            self.window.show()
            app.exec_()
        else:
            print("ThermaGraph: Headless mode detected, skipping UI execution (app.exec_()).")
