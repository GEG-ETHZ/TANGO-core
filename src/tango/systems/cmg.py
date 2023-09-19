import copy
import logging
import inspect

from tango.core.config import *
from tango.core.constants import *
from tango.core.stream import *
from tango.core.abstracts.system import *
from tango.utils import *


class SystemCMG(System):

    def __init__(self, specs):
        super().__init__(specs)


    def _build_graph(self) -> None:
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
        for node in self.nodes:
            Unit = get_unit_class(node[1]['type'], node[1]['unit'])
            node[1]['unit'] = Unit(id, self.specs['cmg'])
            node[1]['unit'].initialize()


    def _init_edges(self) -> None:
        pass



    def execute(self) -> None: #TODO: update for one-multiple connections (traverse graph)
        """execute a series of units accosiated with compute nodes within the system"""
        self.nodes[0][1]['unit'].execute()


        # for id in self.graph.nodes:
        #     self.graph.nodes[id]['unit'].execute()