import copy
from tango.utils import *
from tango.core.stream import *
from abc import ABC
import networkx as nx


class Unit:

    def __init__(self):
        pass

    def add_unit(self, unit: object, name: str):
        setattr(self, name, unit)


class UnitManager(ABC):

    def __init__(self, specs):
        self.specs = specs
        self.unit = Unit()
        self._build_graph()
        self._init_nodes()
        self._init_edges()


    def _build_graph(self) -> None:
        nodes = [(k, v | {'visited': False}) for k, v in self.specs['graph']['nodes'].items()]
        edges = [(v['source'], v['target'], v | {'id': k}) for k, v in self.specs['graph']['edges'].items()]
        self.graph = nx.DiGraph()
        self.graph.add_nodes_from(nodes)
        self.graph.add_edges_from(edges)


    def _init_nodes(self) -> None:
        self._process_specs()
        for id in self.graph.nodes:
            node = self.graph.nodes[id]
            Unit = get_unit_class(node['type'], node['unit'])
            node['unit'] = Unit(id, self.specs)
            node['id'] = id
            self._set_node_object(node)
        self.root_node_id = list(self.graph.nodes)[0]
        self.root_node = self.graph.nodes[self.root_node_id]


    def _init_edges(self) -> None: #TODO: add some treatments for cases where the system is not closed (e.g., source=None)
        for u, v, d in self.graph.edges(data=True):
            source, target = d['source'], d['target']
            stream = Stream(id=d['id'], state=self.graph.nodes[source]['unit'])
            self.graph.nodes[source]['unit'].set_outlet_stream(stream.state)
            self.graph.nodes[target]['unit'].set_inlet_stream(stream.state)
            self.graph.nodes[target]['unit'].init_inlet_state(self.graph.nodes[source]['unit'].state)
        self._graph_check()


    def _process_specs(self) -> None:
        self.specs['common'] = self.specs['props'] | self.specs['schedule'] | self.specs['surface']


    def _set_node_object(self, node) -> None:
        if getattr(self.unit, f"{node['type']}", None) != None:
            if node['type'] not in MULTIPLE_UNIT_NODE_OPTIONS:  # check if multiple node with the same unit type
                raise ValueError(f"Multiple node type: {node['type']} is not supported.")
        self.unit.add_unit(node['unit'], node['type'])


    def _input_check(self, required_units) -> None:
        for unit_name in required_units:
            if getattr(self.unit, unit_name, None) == None:
                raise RuntimeError(f"Required unit: {unit_name} is not found.")


    def _graph_check(self) -> None:
        for _, d1 in self.graph.adj[self.root_node_id].items():
            if d1['target'] != self.root_node_id:
                for _, d2 in self.graph.adj[d1['target']].items():
                    if d2['source'] != self.root_node_id and d2['target'] == d1['target']:
                        raise RuntimeError("Multiple nodes at root node level is not found.")
        for id in self.graph.nodes:
            if len(self.graph.nodes[id]['unit'].inlet_streams) == 0 and len(self.graph.nodes[id]['unit'].outlet_streams) == 0:
                logging.warning(f"Connections are not defined for node: '{id}'")


    def _reset(self) -> None:
        for id in self.graph.nodes:
            node = self.graph.nodes[id]['visited'] = False


    def _update_node(self, node) -> None:
        if node['visited'] == True:
            return
        if node != self.root_node:
            for id in self._source_nodes(node):
                self._update_node(self.graph.nodes[id])
        node['unit'].execute()
        node['visited'] = True


    def _source_nodes(self, node) -> list:
        nodes = list()
        for _, d in self.graph.adj[node['id']].items():
            if d['target'] == node['id']:
                nodes.append(d['source'])
        return nodes


    def _next_nodes(self, node) -> list:
        nodes = list()
        for _, d in self.graph.adj[node['id']].items():
            if d['source'] == node['id']:
                nodes.append(d['target'])
        return nodes


    def _is_terminal(self) -> bool:
        for id in self.graph.nodes:
            if self.graph.nodes[id]['visited'] == False:
                return False
        return True


    def execute(self) -> None: #TODO: update for one-multiple connections (traverse graph)
        """execute a series of units accosiated with compute nodes within the system"""
        self._reset()
        current_node = self.root_node
        self._update_node(current_node)
        while not self._is_terminal():
            for id in self._next_nodes(current_node):
                self._update_node(self.graph.nodes[id])
            current_node = self.graph.nodes[id]
