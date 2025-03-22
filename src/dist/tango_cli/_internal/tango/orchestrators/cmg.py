import copy
import logging
import inspect

from tango.core.config import *
from tango.core.constants import *
from tango.core.stream import *
from tango.core.abstracts.orchestrator import *
from tango.utils import *


class SystemCMG(UnitManager):
    r"""
    System Manager for CMG simulations.

    This class manages a system of interconnected units for CMG-based simulations,
    building a graph structure to represent node relationships and executing workflows
    across the system.

    Attributes:
        specs (dict): Specifications for the system, including graph structure and unit details.
        nodes (list): List of nodes in the system graph.
        graph (nx.Graph): NetworkX graph representing connections between units.
    """

    def __init__(self, specs):
        """
        Initializes a new instance of the SystemCMG class.

        Args:
            specs (dict): Specifications for the system.
        """
        super().__init__(specs)

    def _build_graph(self) -> None:
        """
        Builds the graph structure representing the system's nodes and edges.

        This method initializes the nodes and edges of the graph based on the
        specifications provided in `self.specs`.
        """
        self.nodes = []
        nodes = [(k, v) for k, v in self.specs['graph']['nodes'].items()]
        if len(nodes) == 1:
            self.nodes = nodes
            return

        edges = [(v['source'], v['target'], v | {'id': k}) for k, v in self.specs['graph']['edges'].items()]
        self.graph = nx.Graph()
        self.graph.add_nodes_from(nodes)
        self.graph.add_edges_from(edges)

    def _init_nodes(self) -> None:
        """
        Initializes all units associated with the nodes in the graph..

        This method dynamically retrieves and instantiates the appropriate unit
        class for each node based on its type and configuration.
        """
        for node in self.nodes:
            Unit = get_unit_class(node[1]['type'], node[1]['unit'])
            node[1]['unit'] = Unit(node[0], self.specs['cmg'])
            node[1]['unit'].initialize()

    def _init_edges(self) -> None:
        """
        Placeholder for initializing edges in the graph.

        This method can be extended to define data flow or dependency relationships
        between units connected by edges in the graph.
        """
        pass

    def stream_interface(self) -> None:
        """
        Executes a series of operations across nodes in the system.

        This method processes the graph, invoking the `stream_interface` method
        for each unit associated with the nodes in the system.

        Currently supports a single-node system but can be extended for complex graphs.
        """
        self.nodes[0][1]['unit'].stream_interface()

        # Uncomment to traverse and execute for all nodes in the graph
        # for id in self.graph.nodes:
        #     self.graph.nodes[id]['unit'].stream_interface()

