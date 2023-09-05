import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from tango.runner import Runner
from tango.utils import *

class Tango:

    def __init__(self,
                 args: list):
        args = parse_args(args)
        set_logger(args)
        self.runner = Runner(args.input_file)


    def execute(self) -> None:
        self.runner.start()


if __name__ == '__main__':

    tango = Tango(sys.argv[1:])

    tango.execute()

