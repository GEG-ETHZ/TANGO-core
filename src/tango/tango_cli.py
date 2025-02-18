import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from tango.runner import Tango
from tango.utils import parse_args, set_logger
from tango.optimizerr import Optimizer

class Runner:

    def __init__(self, args: list):
        """
        Initializes the Runner with parsed arguments, logging setup, and the Tango object.
        """
        args = parse_args(args)
        set_logger(args)
        self._tango = Tango(args.input_file)
        # print("Hi")
        # print(self._tango.specs["turbine"]['p_out'])
        # self._tango.specs["turbine"]['p_out'] = 0.04999
        self._optimizer = None
        if "optimization" in self._tango.specs:
            self._optimizer = Optimizer(self._tango, self._tango.specs)

    def start(self) -> None:
        """
        Starts the execution of the workflow. If 'optimization' is present in the specs,
        use the optimizer. Otherwise, use the regular Tango execution.
        """
        if self._optimizer:
            print("Optimization detected. Executing optimizer...")
            self._optimizer.execute()
        else:
            print("No optimization detected. Executing Tango workflow...")
            self._tango.execute()


if __name__ == '__main__':

    runner = Runner(sys.argv[1:])

    runner.start()

