import argparse
import os
import logging
import sys
import time
import json

from tango.core.yaml_loader import load_from_yaml
# from tango.models.adams import CGSModelAdams, CGSModelStateAdams
from tango.models.adams import *

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
        logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
        logging.getLogger('PIL').setLevel(logging.WARNING)
        console = logging.StreamHandler()
        console.setLevel(level)
        logging.getLogger('').addHandler(console)


    def initialize(self) -> None:

        self.start_time = time.time()

        self.read_inputs()

        self.set_workflow()


    def read_inputs(self):
        try:
            logging.info(f"Running TANGO using {self.input_file}")
            self.specs = load_from_yaml(self.input_file)
        except:
            raise RuntimeError(f"Failed to read {self.input_file}")


    def set_workflow(self) -> None:
        self.state = CGSModelStateAdams()
        self.model = CGSModelAdams(self.specs)
        self.model.init_state(self.state)
        self.econ = None
        if 'economic' in self.specs:
            # self.model.econ.init_specs()
            self.econ = EconomicModelAdams(model=self.model,
                                           specs=self.specs['common'] | self.specs['economic'])
        self.print_input_summary()


    def print_input_summary(self) -> None:
        logging.info(f"Input summary: {json.dumps(self.specs, indent=4)}")
        logging.debug(f"Detailed input summary for each component.")
        for name in self.model.model_dict.keys():
            data = self.model.model_dict[name].specs.__dict__
            logging.debug(f"{name}:\n{json.dumps(data, indent=4)}")
        if self.econ:
            data = self.specs['common'] | self.specs['economic']
            logging.debug(f"economic:\n{json.dumps(data, indent=4)}")


    def run_geothermal_power_model(self) -> None:
        logging.info("Running geothermal power model")
        # for i in range(self.specs['lifetime']): #TODO: check how lifetime comes into play
        #     self.model.execute(state)
        self.model.execute(self.state)


    def run_econ_model(self) -> None:
        if self.econ == None:
            return
        logging.info("Running economic model")
        self.econ.init_state(state=self.state)
        self.econ.execute()


    def post_processing(self) -> None:
        pass


    def run(self):

        self.run_geothermal_power_model()

        self.run_econ_model()

        self.post_processing()

        logging.info("Simulation finished normally. Elapsed time: {:.2f} seconds.".format(time.time() - self.start_time))
