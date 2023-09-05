from abc import ABC
import networkx as nx


class Unit:

    def __init__(self):
        pass

    def add_unit(self, unit: object, name: str):
        setattr(self, name, unit)


class System(ABC):

    def __init__(self, specs):
        self.specs = specs
        self.unit = Unit()
        self._build_graph()
        self._init_nodes()
        self._init_edges()


    def _build_graph(self) -> None:
        nodes = [(k, v) for k, v in self.specs['graph']['nodes'].items()]
        edges = [(v['source'], v['target'], v | {'id': k}) for k, v in self.specs['graph']['edges'].items()]
        self.graph = nx.Graph()
        self.graph.add_nodes_from(nodes)
        self.graph.add_edges_from(edges)


    def _init_nodes(self) -> None:
        raise NotImplementedError("Implement '_init_node' method in your derived System class.")


    def _init_edges(self) -> None:
        raise NotImplementedError("Implement '_init_edges' method in your derived System class.")


    def execute(self) -> None:
        raise NotImplementedError("Implement 'execute' method in your derived System class.")
