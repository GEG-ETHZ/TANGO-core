import argparse
import copy
import os
import logging
import sys
import time
import json
import pandas as pd
import numpy as np
from tqdm import tqdm

from dataclasses import dataclass
from tango.core.config import *
from tango.core.yaml_loader import load_from_yaml
from tango.models.adams import *
from tango import utils

@dataclass
class RunnerSpecs():
    workflow: str # workflow option
    file: str = '' # input file for the workflow (required only for external software options)
    max_num_itr: int = 10
    dP_reservoir_threshold: float = 1000. # (Pa) convergence criterion


class Runner:

    def __init__(self,
                 args: list):
        args = utils.parse_args(args)
        self.input_file = args.input_file
        utils.set_logger(input_file=self.input_file, DEBUG=args.debug)
        self.x_lst = []
        self.y_lst = []


    def initialize(self) -> None:

        self.start_time = time.time()

        self.read_inputs()

        self.set_workflow()


    def read_inputs(self) -> None:
        try:
            logging.info(f"Running TANGO using {self.input_file}")
            self.specs = load_from_yaml(self.input_file)
            self.runspec = RunnerSpecs(**self.specs['runspec'])
        except:
            raise RuntimeError(f"Failed to read {self.input_file}")
        logging.debug(f"Input summary:\n{json.dumps(self.specs, indent=4)}")


    def set_STANDALONE_CGS(self) -> None:
        self.state = CGSModelStateAdams()
        self.model = CGSModelAdams(self.specs)
        self.model.initialize(self.state)
        self.results = {'time_yr': [],
                        'inj_well_H': [], 'inj_well_P': [], 'inj_well_Q': [], 'inj_well_S': [], 'inj_well_T': [], # surface (outlet)
                        'prd_well_H': [], 'prd_well_P': [], 'prd_well_Q': [], 'prd_well_S': [], 'prd_well_T': [], # surface (inlet)
                        'res_P': [], 'res_T': [],
                        'q_boiler': [], 'q_condenser': [], 'q_cooler': [], 'q_desuperheater': [],
                        'w_condenser': [], 'w_cooler': [], 'w_pump': [], 'w_turbine': [], 'w_net': []}


    def set_STANDALONE_AGS(self) -> None: # TODO: implement
        raise NotImplementedError(f"workflow: 'STANDALONE_AGS' is not supported.")


    def set_CMG(self) -> None: #TODO: implement
        raise NotImplementedError(f"workflow: 'CMG' is not supported.")


    def set_workflow(self) -> None:
        try:
            getattr(self, f"set_{self.runspec.workflow}")()
        except:
            raise ValueError(f"Something went wrong while setting up workflow: {self.runspec.workflow}")


    def save_STANDALONE_CGS_results(self, current_yr: int) -> None:

        self.results['time_yr'].append(current_yr)

        self.results['inj_well_H'].append(self.state.injection_well.inlet_fluid.H)
        self.results['inj_well_P'].append(self.state.injection_well.inlet_fluid.P)
        self.results['inj_well_Q'].append(self.state.injection_well.inlet_fluid.Q)
        self.results['inj_well_S'].append(self.state.injection_well.inlet_fluid.S)
        self.results['inj_well_T'].append(self.state.injection_well.inlet_fluid.T)

        self.results['res_P'].append(self.state.reservoir.outlet_fluid.P)
        self.results['res_T'].append(self.state.reservoir.outlet_fluid.T)

        self.results['prd_well_H'].append(self.state.production_well.outlet_fluid.H)
        self.results['prd_well_P'].append(self.state.production_well.outlet_fluid.P)
        self.results['prd_well_Q'].append(self.state.production_well.outlet_fluid.Q)
        self.results['prd_well_S'].append(self.state.production_well.outlet_fluid.S)
        self.results['prd_well_T'].append(self.state.production_well.outlet_fluid.T)

        self.results['q_boiler'].append(self.state.surface.q_boiler)
        self.results['q_condenser'].append(self.state.surface.q_condenser)
        self.results['q_cooler'].append(self.state.surface.q_cooler)
        self.results['q_desuperheater'].append(self.state.surface.q_desuperheater)
        self.results['w_condenser'].append(self.state.surface.w_condenser)
        self.results['w_cooler'].append(self.state.surface.w_cooler)
        self.results['w_pump'].append(self.state.surface.w_pump)
        self.results['w_turbine'].append(self.state.surface.w_turbine)
        self.results['w_net'].append(self.state.surface.w_net)


    def save_STANDALONE_AGS_results(self) -> None: # TODO: implement
        raise NotImplementedError(f"workflow: 'STANDALONE_AGS' is not supported.")


    def save_CMG_results(self) -> None: #TODO: implement
        raise NotImplementedError(f"workflow: 'CMG' is not supported.")


    def save_results(self, current_yr: int) -> None:
        getattr(self, f"save_{self.runspec.workflow}_results")(current_yr)


    def converged(self) -> bool:

        dP_reservoir = self.state.reservoir.pressure_old - self.state.reservoir.pressure

        if np.abs(dP_reservoir) < self.runspec.dP_reservoir_threshold:
            return True

        if not self.x_lst: # first call
            self.x_lst.append(copy.deepcopy(self.state.surface.dP_pump))
            self.y_lst.append(self.state.reservoir.pressure_old - self.state.reservoir.pressure)
            root = 0.5 * dP_reservoir
        else:
            self.x_lst.append(copy.deepcopy(self.state.surface.dP_pump))
            self.y_lst.append(dP_reservoir)
            root = utils.newton(self.x_lst, self.y_lst)
            self.x_lst.pop(0)
            self.y_lst.pop(0)

        self.model.surface.overwrite_pump_state(state=self.state.surface,
                                                dP_pump=root)

        return False


    def update_primary_variables(self) -> None:
        self.x_lst.clear()
        self.y_lst.clear()
        self.state.reservoir.pressure_old = copy.deepcopy(self.state.reservoir.pressure)


    def step(self) -> None:

        count = 0
        for j in range(self.runspec.max_num_itr):
            count += 1
            self.model.execute(self.state)
            if self.converged():
                logging.debug(f"Converged after {count} iterations")
                break
        
        if count == self.runspec.max_num_itr:
            logging.warning(f"Max number of iteration (={count}) has reached. ")

        self.update_primary_variables()


    def run_models(self) -> None:

        logging.info(f"Executing physics-based models: {list(self.model.model_dict.keys())}")

        lifetime_yr = self.specs['common']['lifetime']
        current_yr = self.specs['common']['start_year']

        for i in tqdm(range(lifetime_yr), desc="Progress: ", ncols = 100, file=sys.stdout):
            self.save_results(current_yr)
            try:
                self.step()
            except:
                raise RuntimeError(f"Something went wrong at time step: {current_yr}")
            current_yr += 1

        logging.info(f"Executing economic models.")
        self.model.economic.execute()


    def post_processing(self) -> None: #TODO: improve

        utils.write_results(input_file=self.input_file,
                            results_physics=self.results,
                            results_econ=self.model.economic.results)

        logging.info("Simulation finished normally. Elapsed time: {:.2f} seconds.".format(time.time() - self.start_time))


    def start(self) -> None:

        self.initialize()

        self.run_models()

        self.post_processing()


