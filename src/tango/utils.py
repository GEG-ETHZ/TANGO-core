import argparse
import os
import logging
import pandas as pd
from tango.core.config import *


def parse_args(args) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='TANGO - Techno-economic ANalysis of GeOthermal power simulator')
    parser.add_argument('-f',
                        '--file',
                        dest='input_file',
                        help='input file (.yml)',
                        required=True)
    parser.add_argument('-d',
                        '--debug',
                        dest='debug',
                        help='set loglevel to DEBUG',
                        required=False,
                        default=False,
                        action=argparse.BooleanOptionalAction)
    return parser.parse_args(args)


def set_logger(input_file: str, DEBUG: bool):
    if not os.path.isfile(input_file):
        raise FileNotFoundError(f'{input_file} not found')
    level = logging.INFO
    if DEBUG:
        level = logging.DEBUG
    logging.getLogger().setLevel(level)
    logging.basicConfig(filename=os.path.splitext(input_file)[0] + ".log",
                        filemode="w",
                        format='%(asctime)s, %(levelname)s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S',
                        level=level)
    console = logging.StreamHandler()
    console.setLevel(level)
    logging.getLogger('').addHandler(console)


def newton(x_lst: list, y_lst: list) -> float:
    dydx = (y_lst[1] - y_lst[0]) / (x_lst[1] - x_lst[0])  # slope
    return x_lst[0] - y_lst[0] / dydx


def append_results(d: dict, state: classmethod, base_name: str) -> None:
    var_names = [var for var in dir(state) if not var.startswith("__")]
    for name in var_names:
        try:
            val = getattr(state, name)
            if isinstance(val, float) and name not in SKIP_REPORT_ATTRIBUTES:
                s = f"{base_name}_{name}"
                if s in d.keys():
                    d[s].append(val)
                else:
                    d[s] = [val]
        except:
            continue


def parse_results(d: dict, state_lst: list, base_name_lst: list, current_yr:int) -> None:
    name = 'time_yr'
    if name not in d.keys():
        d[name] = [current_yr]
    else:
        d[name].append(current_yr)
    for i, state in enumerate(state_lst):
        append_results(d, state, base_name_lst[i])


def write_results(input_file: str, results_physics: dict, results_econ: dict) -> None:

    fname = os.path.splitext(input_file)[0] + ".smry.csv"
    logging.info(f"Saving output summary of physics-based models > {fname}")
    df = pd.DataFrame(results_physics)
    df.to_csv(fname, index=False)

    fname = os.path.splitext(input_file)[0] + ".econ.csv"
    logging.info(f"Saving output summary of economic models > {fname}")
    d = dict()
    for key in results_econ.keys():
        d[key] = [results_econ[key]]
    df = pd.DataFrame(d)
    df.to_csv(fname, index=False)
