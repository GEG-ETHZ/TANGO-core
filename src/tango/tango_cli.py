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
        
        if args.parameter_overrides:
            print(f"Applying {len(args.parameter_overrides)} parameter overrides:")
            for override in args.parameter_overrides:
                print(f"  {override}")
        
        if args.params_json:
            print(f"Applying JSON parameter overrides: {args.params_json}")
        
        self._tango = Tango(args.input_file, 
                           parameter_overrides=args.parameter_overrides,
                           params_json=args.params_json)
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

