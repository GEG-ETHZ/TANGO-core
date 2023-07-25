import logging
from tango import utils
from tango.core.config import *
from tango.runners.base import RunnerSpecs, Runner
from tango.runners.CPG import *
from tango.runners.ORC import *

class Runner:

    def __init__(self,
                 args: list):
        args = utils.parse_args(args)
        self.input_file = args.input_file
        utils.set_logger(input_file=self.input_file,
                         DEBUG=args.debug)
        self.read_inputs()
        self.set_runner()


    def read_inputs(self) -> None:
        try:
            logging.info(f"Running TANGO using {self.input_file}")
            self.specs = utils.load_from_yaml(self.input_file)
        except:
            raise RuntimeError(f"Failed to read {self.input_file}")
        utils.check_inputs(self.specs)


    def get_runner(self) -> object:
        name = 'Runner' + self.specs['runspec']['workflow']['surface']
        try:
            return eval(name)
        except:
            raise NotImplementedError(f"workflow: {self.specs['runspec']['workflow']['surface']} is not supported.")


    def set_runner(self) -> None:
        Runner = self.get_runner()
        self.runner = Runner(self.specs, self.input_file)


    def start(self) -> None:
        self.runner.start()





