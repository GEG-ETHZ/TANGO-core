import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from tango.driver import Tango
from tango.utils import parse_args, set_logger
from optimizer.driver import Optimizer

class Runner:

    def __init__(self,
                 args: list):
        args = parse_args(args)
        set_logger(args)
        self._tango = Tango(args.input_file)
        self._optimizer = self._init_optimizer(args)


    def _init_optimizer(self, args) -> object:
        if args.opt != None or "optimization" in self._tango.specs:
            return Optimizer(fun=self._tango)
        else:
            return None


    def start(self) -> None:
        if self._optimizer != None:
            self._optimizer.execute()
        else:
            self._tango.execute()


if __name__ == '__main__':

    runner = Runner(sys.argv[1:])

    runner.start()

