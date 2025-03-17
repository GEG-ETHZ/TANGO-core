import sys
from datetime import datetime
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent))

from tango.runner import Tango
from tango.utils import parse_args, set_logger
from tango.optimizerr import Optimizer

EXPIRATION_DATE = datetime(2025, 5,31)

class Runner:

    def __init__(self, args: list):
        """
        Initializes the Runner with parsed arguments, logging setup, and the Tango object.
        """
        args = parse_args(args)
        set_logger(args)
        self._tango = Tango(args.input_file)
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

    current_date = datetime.now()

    if current_date > EXPIRATION_DATE:
        print("This executable has expired. Please contact the developer for an updated version.")
        sys.exit(1)

    runner = Runner(sys.argv[1:])

    runner.start()

