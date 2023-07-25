import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import logging
from tango import utils
from tango.runner import Runner


class TANGO:

    def __init__(self,
                 args: list):
        args = utils.parse_args(args)
        utils.set_logger(args)
        self.input_file = args.input_file
        self.specs = utils.load_from_yaml(self.input_file)
        self.runner = Runner(self.specs, self.input_file)


    def run(self) -> None:
        self.runner.start()


if __name__ == '__main__':

    tango = TANGO(sys.argv[1:])

    tango.run()

