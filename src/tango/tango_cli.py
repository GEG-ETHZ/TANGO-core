import sys

from tango.runner import Runner
from tango.utils import parse_tango_args


def main():
    """Run TANGO CLI."""
    args = parse_tango_args(sys.argv[1:])

    runner = Runner(
        input_file=args.input_file,
        save_dir=args.save_dir,
        no_save=args.no_save,
        parameter_overrides=args.parameter_overrides,
        user_id=args.user_id,
        log_level=args.log_level,
    )
    runner.start()


if __name__ == "__main__":
    main()
