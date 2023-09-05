import networkx as nx
import numpy as np
import copy
import logging
import inspect

from tango.core.config import *
from tango.core.constants import *
from tango.core.abstracts.system import *
from tango.utils import *
from tango.models.native import *
from tango.models.native.well import *
from tango.models.native.surface import *
from tango.models.native.stream import *

def get_model_class(type_: str, model_name: str) -> object:
    try:
        return eval(MODEL_OPTIONS[type_.lower()][model_name.lower()])
    except:
        raise ValueErrorr(f"model type: {type_} is not supported in model: {model_name.lower()}.")


class SystemNative(System):

    def __init__(self, specs):
        super().__init__(specs)
        self.x_lst, self.y_lst = [], []
        self.MAX_NUM_ITR = CONVERGENCE_CRITERIA['max_num_itr']


    def _process_specs(self) -> dict:
        specs = dict()
        for id in self.graph.nodes:
            node = self.graph.nodes[id]
            specs[node['type']] = node['specs']
        specs['common'] = self.specs['graph']['specs'] | self.specs['schedule']
        return specs


    def _set_node_object(self, node) -> None:
        if getattr(self, f"{node['type']}_model", None) != None:
            if node['type'] not in MULTIPLE_MODEL_NODE_OPTIONS:  # check if multiple node with the same model type
                raise ValueErrorr(f"Multiple node type: {node['type']} is not supported.")
        self.model.add_model(node['model'], node['type'])


    def _init_nodes(self) -> None:
        specs = self._process_specs()
        for id in self.graph.nodes:
            node = self.graph.nodes[id]
            Model = get_model_class(node['type'], node['model'])
            node['model'] = Model(specs)
            node['model'].init_state()
            self._set_node_object(node)


    def _init_edges(self) -> None:
        for u, v, d in self.graph.edges(data=True):
            source, target = d['source'], d['target']
            stream = StreamNative(id=d['id'])
            stream.init_state(self.graph.nodes[source]['model'].state)
            self.graph.nodes[source]['model'].set_outlet_stream(stream.state)
            self.graph.nodes[target]['model'].set_inlet_stream(stream.state)
            self.graph.nodes[target]['model'].init_boundary_states(self.graph.nodes[source]['model'].state)
            #TODO: add some treatments for cases where the system is not closed (e.g., source=None)
        for id in self.graph.nodes:
            if len(self.graph.nodes[id]['model'].inlet_streams) == 0 and len(self.graph.nodes[id]['model'].outlet_streams) == 0:
                logging.warning(f"Connections are not defined for node: '{id}'")


    def _input_check(self, required_models) -> None:
        for model_name in required_models:
            if getattr(self.model, model_name, None) == None:
                raise RuntimeError(f"Required model: {model_name} is not found.")


    def balanced(self) -> bool:
        return True


    def update_time_dependent_vars(self) -> None:
        pass


    def update(self) -> None:
        pass


    def max_itr_reached(self, count) -> bool:
        if count > self.MAX_NUM_ITR:
            logging.warning(f"Max number of iteration (={count}) has reached in '{inspect.stack()[1][3]}'. Exiting iteration.")
            return True
        return False


    def execute(self) -> None: #TODO: update for one-multiple connections (traverse graph)
        """execute a series of models accosiated with compute nodes within the system"""
        for id in self.graph.nodes:
            node = self.graph.nodes[id]
            node['model'].execute()


class SystemCPGNative(SystemNative):

    def __init__(self, specs):
        super().__init__(specs)
        self._input_check(['injection_well', 'reservoir', 'production_well', 'surface'])
        self._set_convergence_criteria()


    def _set_convergence_criteria(self) -> None:
        self._CONVERGENCE_CRIT_DP_RESERVOIR: float = CONVERGENCE_CRITERIA['dP_reservoir']


    def balanced(self) -> bool:
        self.dP_reservoir = self.model.reservoir.state.get_del_pressure()
        if np.abs(self.dP_reservoir) < self._CONVERGENCE_CRIT_DP_RESERVOIR:
            return True
        return False


    def update(self) -> None:
        """update unknown to balance the system"""
        self.x_lst.append(self.model.surface.state.get_dP_pump())
        self.y_lst.append(self.dP_reservoir)
        if len(self.x_lst) == 1: # first call
            root = 0.5 * self.dP_reservoir
        else:
            root = newton(self.x_lst, self.y_lst)
            self.x_lst.pop(0)
            self.y_lst.pop(0)
        self.model.surface.state.update_dP_pump(root)
        self.model.surface.overwrite_pump_state()


    def update_time_dependent_vars(self) -> None:
        self.x_lst.clear()
        self.y_lst.clear()
        self.model.reservoir.state.update_pressure_old()
        self.model.reservoir.state.update_energy_extracted_old()
        self.model.injection_well.state.update_dimensionless_time_old()
        self.model.production_well.state.update_dimensionless_time_old()




class SystemORCNative(SystemNative):

    def __init__(self, state):
        super().__init__(state)
        self._input_check(['injection_well', 'reservoir', 'production_well', 'production_well_pump', 'surface'])
        self._set_convergence_criteria()


    def _set_convergence_criteria(self) -> None:
        self._CONVERGENCE_CRIT_DP_RESERVOIR: float = CONVERGENCE_CRITERIA['dP_reservoir']
        self._CONVERGENCE_CRIT_DP_SURFACE: float = CONVERGENCE_CRITERIA['dP_surface']
        self._CONVERGENCE_CRIT_DT_SURFACE: float = CONVERGENCE_CRITERIA['dT_surface']


    def _update_injection_well_inlet_P(self) -> None:
        """Local iterations to update injection well inlet pressure"""
        self.model.injection_well.update_inlet_state()
        dP_reservoir = self.model.reservoir.state.get_del_pressure()
        x_lst, y_lst = [], []
        count = 0
        while np.abs(dP_reservoir) > self._CONVERGENCE_CRIT_DP_RESERVOIR:
            if self.max_itr_reached(count):
                break
            x_lst.append(copy.deepcopy(self.model.injection_well.state.inlet_fluid.P))
            y_lst.append(dP_reservoir)
            if len(x_lst) == 1:  # first call
                root = x_lst[0] + dP_reservoir
            else:
                root = newton(x_lst, y_lst)
                x_lst.pop(0), y_lst.pop(0)
            self.model.injection_well.state.update_inlet_fluid_state_PT(P=root)
            self.model.injection_well.update()
            self.model.reservoir.execute()
            dP_reservoir = self.model.reservoir.state.get_del_pressure()
            count += 1


    def _compute_dP_surface(self) -> float:
        return self.model.production_well_pump.state.outlet_fluid.P \
             - self.model.injection_well.state.inlet_fluid.P \
             - self.model.surface.state.dP_pipe


    def _update_production_well(self) -> None:
        self.model.production_well.execute()
        self.model.production_well_pump.execute()
        self._update_production_well_pump()


    def _update_production_well_pump(self) -> None:
        """Local iterations to update dP_pump in production well with pump"""
        dP_pump = self.model.production_well_pump.state.get_dP_pump()
        dP_surface = self._compute_dP_surface()
        if dP_pump == 0. and dP_surface >= 0:
            return # no pummping needed
        x_lst, y_lst = [], []
        count = 0
        while np.abs(dP_surface) > self._CONVERGENCE_CRIT_DP_SURFACE:
            if self.max_itr_reached(count):
                break
            x_lst.append(copy.deepcopy(dP_pump))
            y_lst.append(dP_surface)
            if len(x_lst) == 1:  # first call
                root = -1.0 * dP_surface
            else:
                root = newton(x_lst, y_lst)
                x_lst.pop(0), y_lst.pop(0)
            self.model.production_well_pump.state.set_dP_pump(root)
            self.model.production_well_pump.state.update_inlet_fluid_state_with_pump()
            self.model.production_well_pump.update()
            self.model.surface.update_inlet_state()
            self.model.surface.overwrite_state_pipe()
            dP_pump = self.model.production_well_pump.state.get_dP_pump()
            dP_surface = self._compute_dP_surface()
            count += 1
        self.model.surface.state.w_downhole_pump = self.model.production_well_pump.state.get_w_pump()


    def _update_surface(self) -> None:
        self.model.surface.execute()
        self.model.injection_well.update_inlet_state()


    def _update_injection_well_inlet_T(self) -> None:
        """Local iterations to update temperature at injection well"""
        self.model.surface.execute()
        dT_surface = self.model.injection_well.state.get_del_temperature(T=self.model.surface.state.outlet_fluid.T)
        self.x_lst.append(copy.deepcopy(self.model.injection_well.state.get_inlet_temperature_tmp()))
        self.y_lst.append(dT_surface)
        if len(self.x_lst) == 1: # first call
            root = self.model.surface.state.outlet_fluid.T
        else:
            try:
                root = newton(self.x_lst, self.y_lst)
            except:
                root= -1. # dummy
            root = max(root, MIN_INJ_TEMPERATURE)
            self.x_lst.pop(0)
            self.y_lst.pop(0)
        self.model.injection_well.state.update_inlet_fluid_state_PT(T=root)
        self.model.injection_well.state.update_inlet_temperature_tmp()


    def balanced(self) -> bool:
        dP_reservoir = self.model.reservoir.state.get_del_pressure()
        dP_surface = self._compute_dP_surface()
        dT_surface = self.model.injection_well.state.get_del_temperature(T=self.model.surface.state.outlet_fluid.T)
        if  np.abs(dP_reservoir) < self._CONVERGENCE_CRIT_DP_RESERVOIR and \
            np.abs(dP_surface) < self._CONVERGENCE_CRIT_DP_SURFACE and \
            np.abs(dT_surface) < self._CONVERGENCE_CRIT_DT_SURFACE:
            return True
        return False


    def update(self) -> None:
        """update unknown variables to balance the system"""
        count = 0
        while not self.balanced():

            if self.max_itr_reached(count):
                break

            self._update_injection_well_inlet_P()

            self._update_production_well()

            self._update_injection_well_inlet_T()

            count += 1


    def update_time_dependent_vars(self) -> None:
        self.x_lst.clear()
        self.y_lst.clear()
        self.model.reservoir.state.update_pressure_old()
        self.model.reservoir.state.update_energy_extracted_old()
        self.model.injection_well.state.update_dimensionless_time_old()
        self.model.production_well.state.update_dimensionless_time_old()
        self.model.production_well_pump.state.update_dimensionless_time_old()
