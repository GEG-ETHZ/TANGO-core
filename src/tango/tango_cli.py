import sys
from pathlib import Path

from tango.runner import Tango
from tango.utils import parse_args, set_logger
from tango.optimizerr import Optimizer


class Runner:
    def __init__(self, args: list):
        """Initialize the Runner with parsed arguments, logging setup, and the Tango object."""
        args = parse_args(args)
        set_logger(args)

        if args.parameter_overrides:
            print(f"Applying {len(args.parameter_overrides)} parameter overrides:")
            for override in args.parameter_overrides:
                print(f"  {override}")

        if args.params_json:
            print(f"Applying JSON parameter overrides: {args.params_json}")

        self._tango = Tango(
            args.input_file,
            parameter_overrides=args.parameter_overrides,
            params_json=args.params_json,
            user_id=args.user_id,
        )
        self._optimizer = None
        if "optimization" in self._tango.specs:
            self._optimizer = Optimizer(self._tango, self._tango.specs)

    def start(self) -> None:
        """Start the execution of the workflow. If 'optimization' is present in the specs,
        use the optimizer. Otherwise, check for batch simulation or use regular Tango execution.
        """
        if self._optimizer is not None:
            print("Optimization detected. Executing optimizer...")
            self._optimizer.execute()
        elif "batch_simulation" in self._tango.specs and self._tango.specs["batch_simulation"].get(
            "enabled", False
        ):
            # TODO: `"batch_simulation" in self._tango.specs and ` is probably redundant with the
            # second predicate
            # NOTE: it's possible to have `self._optimizer is not None` and still satisfy this branch
            # which is likely not the intended behavior
            print("Batch simulation detected. Executing batch simulation...")
            self._tango.execute_batch_simulation()
        else:
            print("No optimization or batch simulation detected. Executing Tango workflow...")
            self._tango.execute()


def main():
    """Run TANGO CLI"""
    runner = Runner(sys.argv[1:])
    runner.start()


if __name__ == "__main__":
    main()
