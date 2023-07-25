from tango.models.base import *
from tango.models.adams import *
from tango.models.adams.well import *
from tango.models.adams.surface import *
# from tango.models.surrogate import * # TODO: implement
from tango.core.config import *


def get_attr_name(compute_node_name: str, model_name: str, attr_type: str):
    name = ''
    for s in compute_node_name.split('_'):
        name += s.capitalize()
    return name + attr_type.capitalize() + model_name


class WorkflowState(ModelState):
    """The state of the conventional geothermal system based on Adams model."""
    def __init__(self, workflow: dict):
        for compute_node in workflow.keys():
            model_name = workflow[compute_node]
            attr_name = get_attr_name(compute_node, model_name, 'State')
            try:
                self.add_state(compute_node, eval(attr_name))
            except:
                raise RuntimeError(f"Failed to add state: {attr_name}. Model name:{model_name} for compute node: {compute_node} is not supported.")


class Workflow(Model):
    """The model of the conventional geothermal system based on Adams model."""
    def __init__(self, specs: dict, workflow: dict):
        super().__init__(specs)
        self.workflow = workflow
        self.econ_model_name = self.workflow.pop('economic', None)
        for compute_node in self.workflow.keys():
            model_name = self.workflow[compute_node]
            attr_name = get_attr_name(compute_node, model_name, 'Model')
            self.add_model(compute_node, eval(attr_name))
            try:
                self.add_model(compute_node, eval(attr_name))
            except:
                raise RuntimeError(f"Failed to add model: {attr_name}. Model name:{model_name} for compute node: {compute_node} is not supported.")


    def init_compute_nodes(self, state) -> None:
        """initialize each compute node"""
        for compute_node in self.workflow.keys():
            getattr(self, compute_node).init_state(getattr(state, compute_node))


    def init_connections(self, state) -> None:
        """initialize connections between compute nodes"""
        compute_nodes = [*self.workflow]
        for idx, compute_node in enumerate(self.workflow.keys()):
            getattr(self, compute_node).set_inlet_state(state_self=getattr(state, compute_nodes[idx]),
                                                        state_from=getattr(state, compute_nodes[idx-1]))


    def init_econ_model(self, state) -> None:
        """initialize econ model, if applicable"""
        self.economic = None
        if self.econ_model_name is not None:
            EconModel = eval(get_attr_name('economic', self.econ_model_name, 'Model'))
            self.economic = EconModel(specs = self.specs['common'] | self.specs['economic'],
                                      model_dict=self.model_dict)
            self.economic.set_inlet_state(state.surface)


    def initialize(self, state):

        self.init_compute_nodes(state)

        self.init_connections(state)

        self.init_econ_model(state)


    def execute(self, state): #-> ModelResult:
        return super().execute(state)
