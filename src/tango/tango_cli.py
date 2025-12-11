import sys
from pathlib import Path

from tango.core.errors import CoolPropError
from tango.runner import Tango, Runner
from tango.utils import parse_tango_args, set_logger


def main():
    """Run TANGO CLI"""
    args = parse_tango_args(sys.argv[1:])
    set_logger(args)

    runner = Runner(
        input_file=args.input_file,
        parameter_overrides=args.parameter_overrides,
        params_json=args.params_json,
        user_id=args.user_id,
    )
    runner.start()


if __name__ == "__main__":
    main()
