from tango.models.base import *
from tango.models.adams import *
from tango.models.adams.model import *
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
    def __init__(self, workflow: dict):
        for compute_node in workflow.keys():
            model_name = workflow[compute_node]
            attr_name = get_attr_name(compute_node, model_name, 'State')
            try:
                self.add_state(compute_node, eval(attr_name))
            except:
                raise RuntimeError(f"Failed to add state: {attr_name}. Model name:{model_name} for compute node: {compute_node} is not supported.")


class Workflow(Model):
    def __init__(self, specs: dict, workflow: dict):
        super().__init__(specs)
        self.workflow = workflow
        self.econ_model_name = self.workflow.pop('economic', None)
        self.economic = None
        self.surface = None
        for compute_node in self.workflow.keys():
            model_name = self.workflow[compute_node]
            attr_name = get_attr_name(compute_node, model_name, 'Model')
            try:
                self.add_model(compute_node, eval(attr_name))
            except:
                raise RuntimeError(f"Failed to add model: {attr_name}. Model name:{model_name} for compute node: {compute_node} is not supported.")


    def init_compute_nodes(self) -> None:
        """initialize each compute node"""
        for compute_node in self.workflow.keys():
            getattr(self, compute_node).init_state(getattr(self.state, compute_node))


    def init_connections(self) -> None: #TODO: Implement tree data structure
        """initialize connections between compute nodes"""
        compute_nodes = [*self.workflow]
        for idx, compute_node in enumerate(self.workflow.keys()):
            getattr(self, compute_node).set_inlet_state(state_self=getattr(self.state, compute_nodes[idx]),
                                                        state_from=getattr(self.state, compute_nodes[idx-1]))


    def init_system(self) -> None:
        """
            initialize system that oversees all the compute nodes and their states.
            system type varies depending on surface compute node
        """
        system_attr_name = 'System' if self.surface == None else f"System{self.workflow['surface']}"
        try:
            System = eval(system_attr_name)
            self.system = System(state=self.state, models=self.model_dict)
        except:
            raise RuntimeError(f"Failed to instantiate System class. Surface model name: {self.workflow['surface']} is not supported.")


    def init_econ_model(self) -> None:
        """initialize econ model, if applicable"""
        if self.econ_model_name is not None:
            EconModel = eval(get_attr_name('economic', self.econ_model_name, 'Model'))
            self.economic = EconModel(specs = self.specs['common'] | self.specs['economic'],
                                      model_dict=self.model_dict)
            self.economic.set_inlet_state(self.state.surface)


    def initialize(self, state):

        self.state = state

        self.init_compute_nodes()

        self.init_connections()

        self.init_system()

        self.init_econ_model()


    def execute(self): #-> ModelResult:
        return super().execute(self.state)
