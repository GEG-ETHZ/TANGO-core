import argparse
import os
import logging

import numpy as np
import pandas as pd
from oyaml import load, SafeLoader
from datetime import datetime

from tango.core.config import *
from tango.core.constants import *


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
    parser.add_argument('-t',
                        '--test',
                        dest='test',
                        help='run with test option',
                        required=False,
                        default=False,
                        action=argparse.BooleanOptionalAction)
    return parser.parse_args(args)


def set_logger(input_file: str, DEBUG: bool, TEST: bool = False):
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
    if not TEST:
        console = logging.StreamHandler()
        console.setLevel(level)
        logging.getLogger('').addHandler(console)


def load_from_yaml(filename: str):
    with open(filename) as f:
        specs = load(f, Loader=SafeLoader)
    return specs


def check_inputs(specs: dict) -> None:
    if specs['runspec']['workflow'] not in WORKFLOW_OPTIONS:
        raise RuntimeError(f"Invalid workflow found: {specs['runspec']['workflow']}")
    else:
        if 'STANDALONE' in specs['runspec']['workflow'] and 'fluid_name' not in specs['common']:
            raise RuntimeError(f"'fluid_name' is missing in 'common' section.")
    if not isinstance(specs['common']['num_tsteps'], int):
        raise RuntimeError(
            f"Invalid variable type found in {specs['common']['num_tsteps']}: {type(specs['common']['num_tsteps'])}. Use type: int")
    if specs['common']['num_tsteps'] < 1:
        raise RuntimeError(
            f"Invalid value found in {specs['common']['num_tsteps']}: Use an integer value greater than 0")
    if specs['common']['dt'] > 5.0:
        logging.warning(f"Large time step size found: {specs['common']['dt']}. It may result in inaccurate results.")
    if specs['common']['fluid_name'] not in FLUID_NAME_OPTIONS:
        raise RuntimeError(f"fluid_name: {specs['common']['fluid_name']} is not supported.")
    #TODO: add warning messages for unrealistic input values


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


def parse_results(d: dict, state_lst: list, base_name_lst: list, current_date:str) -> dict:
    name = 'date'
    if name not in d.keys():
        d[name] = [current_date]
    else:
        d[name].append(current_date)
    for i, state in enumerate(state_lst):
        append_results(d, state, base_name_lst[i])


def parse_results(d: dict, state, current_date:str) -> dict:
    name = 'date'
    if name not in d.keys():
        d[name] = [current_date]
    else:
        d[name].append(current_date)
    unit_names = [var for var in dir(state) if not var.startswith("__")]
    for unit_name in unit_names:
        if unit_name in REPORT_SETTINGS.keys():
            unit_state = getattr(state, unit_name)
            if REPORT_SETTINGS[unit_name]:
                unit_state = getattr(unit_state, REPORT_SETTINGS[unit_name])
            append_results(d, unit_state, unit_name)


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
