# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""tango_core — command-line entry point for tango simulations.

Usage examples
--------------
Run a simulation::

    tango_core run templates/hydro_sf_electric.yml

Run with debug logging::

    tango_core run templates/hydro_sf_electric.yml --log-level DEBUG

Validate an input file without running::

    tango_core validate templates/hydro_sf_electric.yml

Print version::

    tango_core --version

Copy the bundled templates into a local directory to start from::

    tango_core init my_project
"""

from __future__ import annotations

import argparse
import importlib.resources
import logging
import shutil
import sys
import time
from pathlib import Path

from tango_core import __version__, phase_diagrams, results_export
from tango_core.core.errors import ConfigError, TangoError
from tango_core.workflows.workflow import Workflow

_AVAILABLE_APPS = frozenset(
    {
        "demo_hydro_sf_electric",
        "demo_well_mesh_convergence",
        "opt_AGS_direct_heat",
        "opt_hydro_df_electric",
        "opt_hydro_sf_electric",
    },
)  # must track applications/'s subdirectories and pyproject.toml's
# [tool.hatch.build.targets.wheel.force-include] entries for them

_LICENSE_NOTICE = "Copyright 2025 ETH Zurich. Licensed under the Apache License, Version 2.0."


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with sub-commands.

    ``--log-level`` is accepted BOTH before and after the subcommand
    (``tango_core --log-level DEBUG run f.yml`` and
    ``tango_core run f.yml --log-level DEBUG`` both work). The
    top-level parser owns an INDEPENDENT copy with a real default
    (``"INFO"``) — NOT inherited via ``parents``, and NOT combined with
    ``set_defaults()`` — while each subparser gets a separate copy (via a
    shared parent parser) with ``default=argparse.SUPPRESS``, so it only
    overrides the top-level value when the user actually gives
    ``--log-level`` after the subcommand.

    Both pieces of that split matter, confirmed empirically: giving the
    subparser copy a real default (no ``SUPPRESS``) makes argparse
    re-apply IT unconditionally when dispatching to the subparser,
    silently discarding a top-level ``--log-level DEBUG`` back to
    ``"INFO"`` even though the user never touched ``--log-level`` after
    the subcommand. And making the TOP-level parser inherit the same
    ``SUPPRESS``-defaulted parent (instead of an independent, real-default
    copy) reproduces the exact same silent-discard bug the other
    direction — confirmed with an isolated repro, `argparse`'s subparser
    dispatch does not treat ``parents``-inherited actions the way a
    naive reading of ``SUPPRESS``'s docs would suggest.
    """
    log_level_parent = argparse.ArgumentParser(add_help=False)
    log_level_parent.add_argument(
        "--log-level",
        default=argparse.SUPPRESS,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help=("Logging verbosity.  Use DEBUG to see per-iteration convergence output. Default: INFO."),
    )

    parser = argparse.ArgumentParser(
        prog="tango_core",
        allow_abbrev=False,
        description=(
            "tango — next-generation TANGO simulation framework.\n"
            "Directed-graph geothermal simulation with Pydantic-validated inputs."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  tango_core run templates/hydro_sf_electric.yml\n"
            "  tango_core run my_config.yml --log-level DEBUG\n"
            "  tango_core --log-level DEBUG run my_config.yml\n"
            "  tango_core validate my_config.yml\n"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"tango_core {__version__}\n\n{_LICENSE_NOTICE}",
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
        allow_abbrev=False,
        help="Run a tango simulation.",
        description=(
            "Load a tango YAML input file, build the component graph, "
            "and execute the simulation.  Logs a one-line summary per timestep."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[log_level_parent],
    )
    run_p.add_argument(
        "input_file",
        type=Path,
        metavar="INPUT_FILE",
        help=("Path to the tango YAML input file (e.g. templates/hydro_sf_electric.yml)."),
    )
    run_p.add_argument(
        "--save-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "Write results to DIR (created if needed): <name>.results.yml (full "
            "results -- every component's final config/state, reloadable "
            "with Workflow.from_file()), <name>.smry.csv (one row per "
            "timestep, one column per component's own scalar history "
            "field), <name>.econ.csv (one row, the economic component's "
            "final state -- omitted if the config has no economic: block; "
            "every CSV header ends in its unit, e.g. [K]), "
            "and <name>.phase_<fluid>.html per working fluid (interactive "
            "P-h phase diagram with a year slider -- omitted if the config "
            "has no GraphSurface surface component). "
            "Saving is opt-in: nothing is written unless this is given."
        ),
    )
    run_p.add_argument(
        "--phase-diagram-config",
        default=None,
        metavar="CONFIG",
        help=(
            "Reference lines drawn on the phase diagrams written by --save-dir: "
            "a YAML/JSON file path, or the same as an inline string. Keys "
            "(each a count, spread over the plotted states, or a list of "
            "values): isotherm_temperatures_kelvin, "
            "isentrope_entropies_kj_per_kg_kelvin, "
            "isochore_densities_kg_per_m3, qualities; optional "
            "fluids.<name> overrides per working fluid. Defaults: 5 "
            "isotherms/isentropes/isochores, qualities [0.2, 0.4, 0.6, 0.8]. "
            "Example: '{isotherm_temperatures_kelvin: [350, 450], qualities: 3}'."
        ),
    )
    # ---- validate ----
    val_p = sub.add_parser(
        "validate",
        allow_abbrev=False,
        help="Validate a tango input file without running the simulation.",
        description=(
            "Parse and validate the YAML input file: check that all required "
            "fields are present, all component types are registered, and all "
            "Pydantic specs are satisfied.  Does not execute any physics."
        ),
        parents=[log_level_parent],
    )
    val_p.add_argument(
        "input_file",
        type=Path,
        metavar="INPUT_FILE",
        help="Path to the tango YAML input file to validate.",
    )

    # ---- init ----
    init_p = sub.add_parser(
        "init",
        allow_abbrev=False,
        help="Copy the bundled templates and applications into a local directory.",
        description=(
            "Copy tango's bundled templates/ and every applications/ "
            "pipeline into DEST (created if needed) as a starting point for "
            "your own analysis. Anything that already exists under DEST is "
            "left as-is (not overwritten, not an error), so re-running init "
            "is always safe -- e.g. to pull down applications/ after an "
            "earlier init only fetched templates/. Pass --app one or "
            "more times to copy only specific applications/ instead of all "
            "of them, or --no-apps to skip applications/ entirely."
        ),
        parents=[log_level_parent],
    )
    init_p.add_argument(
        "dest",
        type=Path,
        nargs="?",
        default=Path(),
        metavar="DEST",
        help="Directory to copy templates/ and applications/ into. Default: current directory.",
    )
    init_p.add_argument(
        "--app",
        action="append",
        choices=sorted(_AVAILABLE_APPS),
        dest="apps",
        metavar="APP",
        help="Copy only DEST/applications/APP instead of every application. "
        "Repeatable. See --list-apps for the available names, or "
        "applications/README.md in the repository for what each one does.",
    )
    init_p.add_argument(
        "--no-apps",
        action="store_true",
        help="Copy only templates/, skipping applications/ entirely.",
    )
    init_p.add_argument(
        "--list-apps",
        action="store_true",
        help="Print the available --app names and exit, without copying anything.",
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
    logger.info(
        "tango_core %s",
        __version__,
    )
    logger.info("Input: %s", args.input_file)

    phase_config = None
    if args.phase_diagram_config is not None:
        try:
            phase_config = phase_diagrams.load_phase_diagram_config(args.phase_diagram_config)
        except ConfigError as exc:
            logger.error("Phase diagram config error: %s", exc)
            return 1

    try:
        wf = Workflow.from_file(args.input_file)
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    t_start = time.time()
    try:
        wf.run()
    except TangoError as exc:
        logger.error("Simulation error: %s", exc)
        return 2

    elapsed = time.time() - t_start
    print(f"Simulation finished normally. Elapsed time: {elapsed:.3g} seconds.")

    if args.save_dir is not None:
        written = results_export.write_results(wf, args.save_dir, args.input_file.stem)
        written += phase_diagrams.write_phase_diagrams(wf, args.save_dir, args.input_file.stem, phase_config)
        for path in written:
            print(f"Wrote: {path}")

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


def _cmd_init(args: argparse.Namespace, log_level: str) -> int:
    """Execute the ``init`` sub-command.

    Returns:
        Exit code: 0 on success, 1 if the destination already exists.

    """
    _configure_logging(log_level)
    logger = logging.getLogger(__name__)

    if args.list_apps:
        for app in sorted(_AVAILABLE_APPS):
            print(app)
        return 0

    # No --app given at all -> copy every application (the common case: get
    # a fully working project in one shot). --app one-or-more times narrows
    # that to just the named apps. --no-apps skips applications/ entirely.
    # These three are mutually exclusive by construction (argparse's
    # choices= already rejects unknown --app values; --no-apps + --app
    # together is nonsensical but harmless -- --no-apps just wins below).
    explicit_apps = args.apps is not None
    apps: list[str] = [] if args.no_apps else (args.apps if explicit_apps else sorted(_AVAILABLE_APPS))

    templates_dest = args.dest / "templates"
    app_targets = [args.dest / "applications" / app for app in apps]

    # Only abort on an existing target when the user named that app
    # explicitly -- an explicit ask that can't be honored without
    # overwriting is worth stopping for. In the default "copy everything"
    # case, an already-existing app is just something to leave alone (see
    # the per-app skip below), same treatment as templates/.
    if explicit_apps:
        for target in app_targets:
            if target.exists():
                logger.error("%s already exists -- remove it or choose a different DEST.", target)
                return 1

    # NOT importlib.resources.files("tango_core.templates") -- templates/
    # has no __init__.py, so Python treats it as an implicit namespace package,
    # and importlib.resources.as_file() cannot materialize a namespace
    # package's MultiplexedPath as a directory (tries to read it as a single
    # file's bytes, raising FileNotFoundError). Resolving it as a subdirectory
    # of the real tango package (which has __init__.py) avoids that path --
    # same reasoning applies to each applications/<app> copy below.
    if templates_dest.exists():
        logger.info("%s already exists -- leaving it as-is.", templates_dest)
    else:
        src = importlib.resources.files("tango_core") / "templates"
        with importlib.resources.as_file(src) as src_path:
            shutil.copytree(src_path, templates_dest)
        logger.info("Copied templates to %s", templates_dest)

    for app, app_dest in zip(apps, app_targets, strict=True):
        if app_dest.exists():
            logger.info("%s already exists -- leaving it as-is.", app_dest)
            continue
        src = importlib.resources.files("tango_core") / "applications" / app
        with importlib.resources.as_file(src) as src_path:
            shutil.copytree(src_path, app_dest)
        logger.info("Copied applications/%s to %s", app, app_dest)

    print(f"tango_core run {templates_dest / 'hydro_sf_electric.yml'}")
    return 0


def main() -> None:
    """Entry point registered as ``tango_core`` in pyproject.toml."""
    parser = _build_parser()
    args = parser.parse_args()

    # Global log level (may be overridden per sub-command)
    global_level: str = args.log_level

    if args.command == "run":
        sys.exit(_cmd_run(args, global_level))
    elif args.command == "validate":
        sys.exit(_cmd_validate(args, global_level))
    elif args.command == "init":
        sys.exit(_cmd_init(args, global_level))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
