"""tango_next_cli — command-line entry point for tango_next simulations.

Usage examples
--------------
Run a simulation::

    tango_next_cli run examples/tango_next/flexible_SF_manual.yml

Run with debug logging::

    tango_next_cli run examples/tango_next/flexible_SF_manual.yml --log-level DEBUG

Validate an input file without running::

    tango_next_cli validate examples/tango_next/flexible_SF_manual.yml

Print version::

    tango_next_cli --version
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from tango_next import __version__
from tango_next.core.errors import ConfigError, TangoNextError
from tango_next.workflows.workflow import Workflow


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with sub-commands."""
    parser = argparse.ArgumentParser(
        prog="tango_next_cli",
        description=(
            "tango_next — next-generation TANGO simulation framework.\n"
            "Directed-graph geothermal simulation with Pydantic-validated inputs."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  tango_next_cli run examples/tango_next/flexible_SF_manual.yml\n"
            "  tango_next_cli run my_config.yml --log-level DEBUG\n"
            "  tango_next_cli validate my_config.yml\n"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"tango_next {__version__}",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help=("Logging verbosity.  Use DEBUG to see per-iteration convergence output. Default: %(default)s."),
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ---- run ----
    run_p = sub.add_parser(
        "run",
        help="Run a tango_next simulation.",
        description=(
            "Load a tango_next YAML input file, build the component graph, "
            "and execute the simulation.  Logs a one-line summary per timestep."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run_p.add_argument(
        "input_file",
        type=Path,
        metavar="INPUT_FILE",
        help=("Path to the tango_next YAML input file (e.g. examples/tango_next/flexible_SF_manual.yml)."),
    )
    # ---- validate ----
    val_p = sub.add_parser(
        "validate",
        help="Validate a tango_next input file without running the simulation.",
        description=(
            "Parse and validate the YAML input file: check that all required "
            "fields are present, all component types are registered, and all "
            "Pydantic specs are satisfied.  Does not execute any physics."
        ),
    )
    val_p.add_argument(
        "input_file",
        type=Path,
        metavar="INPUT_FILE",
        help="Path to the tango_next YAML input file to validate.",
    )

    return parser


def _configure_logging(level: str) -> None:
    """Configure root logger and third-party loggers with a timestamped format."""
    numeric_level = getattr(logging, level.upper())
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # TESPy manages its own logger ("TESPyLogger") with a hardcoded level; sync it.
    logging.getLogger("TESPyLogger").setLevel(numeric_level)


def _cmd_run(args: argparse.Namespace, log_level: str) -> int:
    """Execute the ``run`` sub-command.

    Returns:
        Exit code: 0 on success, non-zero on error.

    """
    _configure_logging(log_level)

    logger = logging.getLogger(__name__)
    logger.info("tango_next %s", __version__)
    logger.info("Input: %s", args.input_file)

    try:
        wf = Workflow.from_file(args.input_file)
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    t_start = time.time()
    try:
        wf.run()
    except TangoNextError as exc:
        logger.error("Simulation error: %s", exc)
        return 2

    elapsed = time.time() - t_start
    print(f"Simulation finished normally. Elapsed time: {elapsed:.3g} seconds.")
    return 0


def _cmd_validate(args: argparse.Namespace, log_level: str) -> int:
    """Execute the ``validate`` sub-command.

    Returns:
        Exit code: 0 if valid, 1 if invalid.

    """
    _configure_logging(log_level)
    logger = logging.getLogger(__name__)
    logger.info("Validating: %s", args.input_file)

    try:
        Workflow.from_file(args.input_file)
        logger.info("OK — input file is valid.")
        return 0
    except (ConfigError, Exception) as exc:
        logger.error("Validation failed: %s", exc)
        return 1


def main() -> None:
    """Entry point registered as ``tango_next_cli`` in pyproject.toml."""
    parser = _build_parser()
    args = parser.parse_args()

    # Global log level (may be overridden per sub-command)
    global_level: str = args.log_level

    if args.command == "run":
        sys.exit(_cmd_run(args, global_level))
    elif args.command == "validate":
        sys.exit(_cmd_validate(args, global_level))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
