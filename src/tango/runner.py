import logging
from tango import utils
from tango.core.config import *
from tango.runners.base import RunnerSpecs, Runner
from tango.runners.standaloneCPG import RunnerStandaloneCPG
from tango.runners.standaloneORC import RunnerStandaloneORC

class Runner:

    def __init__(self,
                 args: list):
        args = utils.parse_args(args)
        self.input_file = args.input_file
        utils.set_logger(input_file=self.input_file,
                         DEBUG=args.debug,
                         TEST=args.test)

        self.read_inputs()

        self.set_runner()


    def read_inputs(self) -> None:
        try:
            logging.info(f"Running TANGO using {self.input_file}")
            self.specs = utils.load_from_yaml(self.input_file)
        except:
            raise RuntimeError(f"Failed to read {self.input_file}")
        utils.check_inputs(self.specs)
        self.workflow = self.specs['runspec']['workflow'].upper()


    def get_runner(self) -> object:
        name = 'Runner' \
             + self.workflow.split('_')[0].lower().capitalize() \
             + MAP_FLUIDNAME_TO_SURFACE_PLANT_DESIGN[self.specs['common']['fluid_name']]
        try:
            runner = eval(name)
        except:
            raise NotImplementedError(f"workflow: {self.workflow} is not supported.")
        return runner

    def set_runner(self) -> None:

        Runner = self.get_runner()

        self.runner = Runner(self.specs, self.input_file)


    def start(self) -> None:

        self.runner.start()





