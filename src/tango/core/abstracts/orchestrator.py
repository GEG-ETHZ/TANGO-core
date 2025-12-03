import copy
import logging
from tango.utils import get_unit_class, MULTIPLE_UNIT_NODE_OPTIONS 
from tango.core.stream import Stream
from tango.core.errors import CoolPropError
from abc import ABC
import networkx as nx


class Unit:
    """
    Base class to represent a collection of units within a system.
    Allows dynamic addition of unit objects.
    """
    def __init__(self):
        pass

    def add_unit(self, unit: object, name: str):
        """
        Adds a unit to the system with a given name.

        Args:
            unit (object): The unit to be added.
            name (str): The name of the unit.
        """
        setattr(self, name, unit)


class UnitManager(ABC):
    r"""
    Abstract Base Class for managing interconnected units within a system.

    This class handles the creation of a directed graph representing units and
    their connections, initialization of units, and execution of workflows.

    Attributes:
        specs (dict): Specifications for the system, including graph structure and unit configurations.
        unit (Unit): Container for dynamically added units.
        graph (nx.DiGraph): Directed graph representing the system of units.
        root_node_id (str): ID of the root node in the graph.
        root_node (dict): The root node object.
    """

    def __init__(self, specs, unit_options):
        """
        Initializes a new instance of the UnitManager class.

        Args:
            specs (dict): Specifications for the system.
            unit_options (dict): Dictionary mapping unit types and names to classes.
        """
        self.specs = specs
        self.unit_options = unit_options
        self.unit = Unit()
        self._build_graph()
        self._init_nodes()
        self._init_edges()

    def _build_graph(self) -> None:
        """
        Constructs the graph from the provided specifications.
        """
        nodes = [(k, v | {'visited': False}) for k, v in self.specs['graph']['nodes'].items()]
        edges = [(v['source'], v['target'], v | {'id': k}) for k, v in self.specs['graph']['edges'].items()]
        self.graph = nx.DiGraph()
        self.graph.add_nodes_from(nodes)
        self.graph.add_edges_from(edges)

    def _init_nodes(self) -> None:
        """
        Initializes all nodes in the graph by instantiating their associated units.
        """
        self._process_specs()
        for node_id in self.graph.nodes:
            node = self.graph.nodes[node_id]
            Unit = get_unit_class(type_=node['type'], unit_name=node['unit'], unit_options=self.unit_options)
            node['unit'] = Unit(node_id, specs=self.specs)
            self.unit.add_unit(node['unit'], node_id)
            node['id'] = node_id
            self._set_node_object(node)
        self.root_node_id = list(self.graph.nodes)[0]
        self.root_node = self.graph.nodes[self.root_node_id]

    def _init_edges(self) -> None:
        """
        Initializes the edges in the graph, creating streams between connected units.
        """
        for u, v, d in self.graph.edges(data=True):
            source, target = d['source'], d['target']
            stream = Stream(id=d['id'], state=self.graph.nodes[source]['unit'])
            self.graph.nodes[source]['unit'].set_outlet_stream(stream.state)
            self.graph.nodes[target]['unit'].set_inlet_stream(stream.state)
            self.graph.nodes[target]['unit'].init_inlet_state(self.graph.nodes[source]['unit'])
        self._graph_check()

    def _process_specs(self) -> None:
        """
        Processes and combines common specifications for units.
        """
        self.specs['common'] = self.specs['props'] | self.specs['schedule'] | self.specs['surface']

    def _set_node_object(self, node) -> None:
        """
        Adds a unit to the container dynamically, checking for duplicates.

        Args:
            node (dict): Node object containing unit information.
        """
        existing_unit = getattr(self.unit, node['type'], None)
        if existing_unit is not None:
            if existing_unit is node['unit']:
                return
            if node['type'] not in MULTIPLE_UNIT_NODE_OPTIONS:
                raise ValueError(f"Multiple node type: {node['type']} is not supported.")
        self.unit.add_unit(node['unit'], node['type'])

    def _input_check(self, required_units) -> None:
        """
        Validates that all required units are present in the system.

        Args:
            required_units (list): List of required unit names.

        Raises:
            RuntimeError: If a required unit is missing.
        """
        for unit_name in required_units:
            if getattr(self.unit, unit_name, None) is None:
                raise AttributeError(f"Required unit: {unit_name} is not found.")

    def _graph_check(self) -> None:
        """
        Validates the integrity of the graph structure.

        Raises:
            RuntimeError: If invalid graph connections are found.
        """
        for _, d1 in self.graph.adj[self.root_node_id].items():
            if d1['target'] != self.root_node_id:
                for _, d2 in self.graph.adj[d1['target']].items():
                    if d2['source'] != self.root_node_id and d2['target'] == d1['target']:
                        raise RuntimeError("Multiple nodes at root node level is not supported.")
        for node_id in self.graph.nodes:
            if len(self.graph.nodes[node_id]['unit'].inlet_streams) == 0 and len(self.graph.nodes[node_id]['unit'].outlet_streams) == 0:
                logging.warning(f"Connections are not defined for node: '{node_id}'")

    def _reset(self) -> None:
        """
        Resets the visited status of all nodes in the graph.
        """
        for node_id in self.graph.nodes:
            self.graph.nodes[node_id]['visited'] = False

    def _update_node(self, node) -> None:
        """
        Updates the state of a node during graph traversal.

        Args:
            node (dict): Node object to update.
            src_unit_id (str): Source unit (i.e. component) id, used for error message generation
            nxt_unit_id (str | None): Next unit (i.e. component) id, used for error message generation
        """

        if node["visited"]:
            return
        if node != self.root_node:
            for src_id in self._source_nodes(node):
                try:
                    self._update_node(self.graph.nodes[src_id])
                except CoolPropError as cpe:
                    new_err = CoolPropError(
                        f"\n\tunit: {node['id']}\n\t{cpe}"
                    )
                    raise new_err from cpe
                except Exception as err:
                    raise type(err)(
                        f"\n\tunit: {node['id']}"
                    ) from err
        try:
            node["unit"].update_inlet_state()
            node["unit"].stream_interface()
            node["unit"].update_outlet_streams()
        except CoolPropError as cpe:
            new_err = type(cpe)(
                f"\n\tunit: {node['id']}\n\t{cpe}"
            )
            raise new_err from cpe
        except Exception as err:
            raise type(err)(
                f"\n\tunit: {node['id']}"
            ) from err

        node["visited"] = True

    def _source_nodes(self, node) -> list:
        """
        Retrieves source nodes for a given node.

        Args:
            node (dict): Node object.

        Returns:
            list: List of source node IDs.
        """
        return [d['source'] for _, d in self.graph.adj[node['id']].items() if d['target'] == node['id']]

    def _next_nodes(self, node) -> list:
        """
        Retrieves target nodes for a given node.

        Args:
            node (dict): Node object.

        Returns:
            list: List of target node IDs.
        """
        return [d['target'] for _, d in self.graph.adj[node['id']].items() if d['source'] == node['id']]

    def _is_terminal(self) -> bool:
        """
        Checks if all nodes in the graph have been visited.

        Returns:
            bool: True if all nodes are visited, False otherwise.
        """
        return all(self.graph.nodes[id]['visited'] for id in self.graph.nodes)

    def execute(self) -> None:
        """
        Executes the workflow by traversing the graph and updating nodes.
        """
        self._reset()
        current_node = self.root_node
        self._update_node(current_node)
        while not self._is_terminal():
            for next_unit_id in self._next_nodes(current_node):
                self._update_node(self.graph.nodes[next_unit_id])
            current_node = self.graph.nodes[next_unit_id]

    def get_val_err_with_cntxt(self, current_node, err: ValueError) -> ValueError:
        context = (
            "At the current mass flow rate ("
            + f"{self.specs['common']['mass_flow_rate']} kg/s), pressure/density drop below zero "
            + "between the following nodes:"
            + f"\n\tcurrent component:\n\t\t{current_node['id']}"
            + "\n\tTroubleshooting: trace back to the previous upstream pump/compressor"
            + " to identify flow restrictions or reduce mass flow rate."
            + "\n\n\tTODO: list upstream components and their approximate flow resistances"
        )
        new_err = ValueError(f"\n\n\tCoolProp message:\n\t{err}\n\t{context}")
        return new_err
