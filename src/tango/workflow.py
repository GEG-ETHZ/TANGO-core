from tango.models.base import *
from tango.models.adams import *
from tango.models.adams.model import *
from tango.models.adams.well import *
from tango.models.adams.surface import *
# from tango.models.surrogate import * # TODO: implement
from tango.core.config import *


def _get_attr_name(compute_node_name: str, model_name: str, attr_type: str):
    name = ''
    for s in compute_node_name.split('_'):
        name += s.capitalize()
    return name + attr_type.capitalize() + model_name


class WorkflowState(ModelState):
    def __init__(self, workflow_dict: dict):
        for compute_node in workflow_dict.keys():
            model_name = workflow_dict[compute_node]
            attr_name = _get_attr_name(compute_node, model_name, 'State')
            try:
                self.add_state(compute_node, eval(attr_name))
            except:
                raise RuntimeError(f"Failed to add state: {attr_name}. Model name:{model_name} for compute node: {compute_node} is not supported.")


class Workflow(Model):

    economic = None
    surface = None
    reservoir = None
    horizontal_well = None
    def __init__(self, specs: dict):
        super().__init__(specs)
        self._workflow_specs = specs['runspec']['workflow'] # {'compute_node': 'model_name'}
        self._econ_model_name = self._workflow_specs.pop('economic', None)
        for compute_node in self._workflow_specs.keys():
            model_name = self._workflow_specs[compute_node]
            attr_name = _get_attr_name(compute_node, model_name, 'Model')
            try:
                self.add_model(compute_node, eval(attr_name))
            except:
                raise RuntimeError(f"Failed to add model: {attr_name}. Model name:{model_name} for compute node: {compute_node} is not supported.")


    def _init_compute_nodes(self) -> None:
        """initialize each compute node"""
        for compute_node in self._workflow_specs.keys():
            getattr(self, compute_node).init_state(getattr(self.state, compute_node))


    def _init_connections(self) -> None: #TODO: Implement tree data structure
        """initialize connections between compute nodes"""
        compute_nodes = [*self._workflow_specs]
        for idx, compute_node in enumerate(self._workflow_specs.keys()):
            getattr(self, compute_node).set_inlet_state(state_self=getattr(self.state, compute_nodes[idx]),
                                                        state_from=getattr(self.state, compute_nodes[idx-1]))


    def _init_system(self) -> None:
        """
            initialize system that oversees all the compute nodes and their states.
            system type varies depending on surface compute node
        """
        AGS = self.reservoir == None and self.horizontal_well != None
        system_attr_name = 'System' if self.surface == None or AGS else f"System{self._workflow_specs['surface']}"
        try:
            System = eval(system_attr_name)
            self.system = System(state=self.state, models=self.model_dict)
        except:
            raise RuntimeError(f"Failed to instantiate System class. Surface model name: {self._workflow_specs['surface']} is not supported.")


    def _init_econ_model(self) -> None:
        """initialize econ model, if applicable"""
        if self._econ_model_name is not None:
            EconModel = eval(_get_attr_name('economic', self._econ_model_name, 'Model'))
            self.economic = EconModel(specs = self.specs['common'] | self.specs['economic'],
                                      model_dict=self.model_dict)
            self.economic.set_inlet_state(self.state.surface)


    def initialize(self, state):

        self.state = state

        self._init_compute_nodes()

        self._init_connections()

        self._init_system()

        self._init_econ_model()


    def execute(self):
        return super().execute(self.state)
