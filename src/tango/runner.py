import argparse
import os
import logging
import sys
import time
import json
import pandas as pd
from tqdm import tqdm

from dataclasses import dataclass
from tango.core.config import *
from tango.core.yaml_loader import load_from_yaml
from tango.models.adams import *

@dataclass
class RunnerSpecs():
    workflow: str # workflow option
    file: str = '' # input file for the workflow (required only for external software options)


class Runner:

    def __init__(self,
                 args: list):
        args = self.parse_args(args)
        self.input_file = args.input_file
        self.set_logger(args.debug)


    def parse_args(self, args) -> argparse.Namespace:
        parser = argparse.ArgumentParser(description='TANGO - Techno-economic ANalysis of GeOthermal power simulator')
        parser.add_argument('-f',
                            '--file',
                            dest='input_file',
                            help='input file (.yml)',
                            required=True)
        parser.add_argument('-d',
                            '--debug',
                            dest='debug',
                            help='set loglevel to DEBUG',
                            required=False,
                            default=False,
                            action=argparse.BooleanOptionalAction)
        return parser.parse_args(args)


    def set_logger(self, DEBUG: bool):
        if not os.path.isfile(self.input_file):
            raise FileNotFoundError(f'{self.input_file} not found')
        level = logging.INFO
        if DEBUG:
            level = logging.DEBUG
        logging.getLogger().setLevel(level)
        logging.basicConfig(filename=os.path.splitext(self.input_file)[0] + ".log",
                            filemode="w",
                            format='%(asctime)s, %(levelname)s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S',
                            level=level)
        console = logging.StreamHandler()
        console.setLevel(level)
        logging.getLogger('').addHandler(console)


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
                        'inj_well_H': [], 'inj_well_P': [], 'inj_well_Q': [], 'inj_well_S': [], 'inj_well_T': [], # surface (inlet)
                        'prd_well_H': [], 'prd_well_P': [], 'prd_well_Q': [], 'prd_well_S': [], 'prd_well_T': [], # surface (outlet)
                        'res_energy_extracted': [], # subsurface
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
            raise ValueError(f"workflow: {self.runspec.workflow} is not supported.")


    def save_STANDALONE_CGS_results(self, current_yr: int) -> None:

        self.results['time_yr'].append(current_yr)

        self.results['inj_well_H'].append(self.state.injection_well.inlet_fluid.H)
        self.results['inj_well_P'].append(self.state.injection_well.inlet_fluid.P)
        self.results['inj_well_Q'].append(self.state.injection_well.inlet_fluid.Q)
        self.results['inj_well_S'].append(self.state.injection_well.inlet_fluid.S)
        self.results['inj_well_T'].append(self.state.injection_well.inlet_fluid.T)

        self.results['res_energy_extracted'].append(self.state.reservoir.energy_extracted)

        self.results['prd_well_P'].append(self.state.production_well.outlet_fluid.P)
        self.results['prd_well_H'].append(self.state.production_well.outlet_fluid.H)
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


    def run_models(self) -> None:

        lifetime_yr = self.specs['common']['lifetime']
        current_yr = self.specs['common']['start_year']

        logging.info(f"Executing physics-based models: {list(self.model.model_dict.keys())}")

        for i in tqdm(range(lifetime_yr), desc="Progress: ", ncols = 100):
            self.save_results(current_yr)
            self.model.execute(self.state)
            current_yr += 1

        logging.info(f"Executing economic models.")
        self.model.economic.execute()


    def post_processing(self) -> None: #TODO: improve

        fname = os.path.splitext(self.input_file)[0] + "_smry.csv"
        logging.info(f"Saving output summary of physics-based models > {fname}")
        df = pd.DataFrame(self.results)
        df.to_csv(fname, index=False)

        fname = os.path.splitext(self.input_file)[0] + "_econ.csv"
        logging.info(f"Saving output summary of economic models > {fname}")
        d = dict()
        for key in self.model.economic.results.keys():
            d[key] = [self.model.economic.results[key]]
        df = pd.DataFrame(d)
        df.to_csv(fname, index=False)

        logging.info("Simulation finished normally. Elapsed time: {:.2f} seconds.".format(time.time() - self.start_time))


    def start(self) -> None:

        self.initialize()

        self.run_models()

        self.post_processing()


