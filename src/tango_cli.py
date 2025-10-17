import sys
import logging
from datetime import datetime
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent))

from tango.runner import Tango
from tango.utils import parse_args, set_logger
from tango.optimizerr import Optimizer

<<<<<<< HEAD:src/tango/tango_cli.py
class Runner:
=======
EXPIRATION_DATE = datetime(2025, 12,31)

class Tango:
>>>>>>> main:src/tango_cli.py

    def __init__(self, args: list):
        """
        Initializes the Runner with parsed arguments, logging setup, and the Tango object.
        """
        args = parse_args(args)
        set_logger(args)
        
        if args.parameter_overrides:
            print(f"Applying {len(args.parameter_overrides)} parameter overrides:")
            for override in args.parameter_overrides:
                print(f"  {override}")
        
        if args.params_json:
            print(f"Applying JSON parameter overrides: {args.params_json}")
        
        self._tango = Tango(args.input_file, 
                           parameter_overrides=args.parameter_overrides,
                           params_json=args.params_json,
                           user_id=args.user_id)
        self._optimizer = None
        if "optimization" in self._tango.specs:
            self._optimizer = Optimizer(self._tango, self._tango.specs)

    def start(self) -> None:
        """
        Starts the execution of the workflow. If 'optimization' is present in the specs,
        use the optimizer. Otherwise, check for batch simulation or use regular Tango execution.
        """
        if self._optimizer:
            print("Optimization detected. Executing optimizer...")
            self._optimizer.execute()
        elif 'batch_simulation' in self._tango.specs and self._tango.specs['batch_simulation'].get('enabled', False):
            print("Batch simulation detected. Executing batch simulation...")
            self._tango.execute_batch_simulation()
        else:
            print("No optimization or batch simulation detected. Executing Tango workflow...")
            self._tango.execute()


if __name__ == '__main__':

<<<<<<< HEAD:src/tango/tango_cli.py
    runner = Runner(sys.argv[1:])
=======
    current_date = datetime.now()

    if current_date > EXPIRATION_DATE:
        logging.info("This executable has expired. Please contact the developer for an updated version.")
        sys.exit()

    tango = Tango(sys.argv[1:])
>>>>>>> main:src/tango_cli.py

    runner.start()

