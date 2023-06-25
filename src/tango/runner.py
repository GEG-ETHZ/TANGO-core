import argparse
import os
import logging
import sys
import time
import json
import pandas as pd

from tango.core.yaml_loader import load_from_yaml
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
        #TODO: enable non CGS (conventional geothermal system) options
        self.state = CGSModelStateAdams()
        self.model = CGSModelAdams(self.specs)
        self.model.initialize(self.state)
        self.print_input_summary()


    def print_input_summary(self) -> None:
        logging.info(f"Input summary: {json.dumps(self.specs, indent=4)}")
        logging.debug(f"Detailed input summary for each component.")
        for name in self.model.model_dict.keys():
            logging.debug(f"{name}:\n{json.dumps(self.model.model_dict[name].specs.__dict__, indent=4)}")


    def run_models(self) -> None:
        # for i in range(self.specs['lifetime']): #TODO: check how lifetime comes into play
        #     self.model.execute(state)
        logging.info(f"Executing models.")
        self.model.execute(self.state)
        self.model.economic.execute()



    def post_processing(self) -> None:
        fname = os.path.splitext(self.input_file)[0] + ".csv"
        logging.info("Post processing.")
        logging.info(f"Writing output summary in {fname}")
        d = dict()
        for key in self.model.economic.results.keys():
            d[key] = [self.model.economic.results[key]]
        df = pd.DataFrame(d)
        df.to_csv(fname, index=False)


    def start(self):

        self.initialize()

        self.run_models()

        self.post_processing()

        logging.info("Simulation finished normally. Elapsed time: {:.2f} seconds.".format(time.time() - self.start_time))
