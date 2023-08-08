import argparse
import os
import logging
import sys

import numpy as np
import pandas as pd
from oyaml import load, SafeLoader
from datetime import datetime
from pathlib import Path
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
    return parser.parse_args(args)


def set_logger(args):
    input_file = args.input_file
    DEBUG = args.debug
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


def load_from_yaml(filename: str):
    try:
        with open(filename) as f:
            specs = load(f, Loader=SafeLoader)
    except:
        raise RuntimeError(f"Failed to read {filename}")
    check_inputs(specs)
    return specs


def check_inputs(specs: dict) -> None:

    #
    # ... runspec section
    #

    if 'runspec' not in specs:
        raise RuntimeError(f"Required field: 'runspec' not found in the input file.")
    if 'workflow' not in specs['runspec']:
        raise RuntimeError(f"Required field: 'workflow' not found in runspec section.")
    # if 'surface' not in specs['runspec']['workflow'].keys():
    #     raise RuntimeError(f"Required compute_node: 'surface' not found in runspec.workflow.")
    for compute_node in specs['runspec']['workflow'].keys():
        if compute_node not in COMPUTE_NODE_OPTIONS:
            raise RuntimeError(f"Compute node: {compute_node} is not supported. Compute node options: {COMPUTE_NODE_OPTIONS}")
        if compute_node not in specs.keys():
            raise RuntimeError(f"Compute node: {compute_node} section not found in the input file.")

    #
    # ... common section
    #

    if 'common' in specs:
        if 'fluid_name' in specs['common']:
            if specs['common']['fluid_name'] not in FLUID_NAME_OPTIONS:
                raise RuntimeError(f"fluid_name: {specs['common']['fluid_name']} is not supported.")
        if 'well_pattern' in specs['common']:
            if specs['common']['well_pattern'] not in WELL_PATTERN_OPTIONS:
                raise ValueError(f"Well pattern: {specs['common']['well_pattern']} is not supported.")
            if len(specs['common']['well_pattern_dimens']) != 2:
                raise ValueError(
                    f"Something wrong with well_pattern_dimens: {specs['common']['well_pattern']}. Input a list with two integer elements.")
            if bool(list(filter(lambda x: not isinstance(x, int), specs['common']['well_pattern_dimens']))):
                try:
                    specs['common']['well_pattern_dimens'] = [int(x) for x in specs['common']['well_pattern_dimens']]
                except:
                    raise ValueError(
                        f"Something wrong with well_pattern_dimens: {specs['common']['well_pattern']}. Input a list with two integer elements.")
            if specs['common']['well_pattern'] == 'DOUBLET':
                if bool(list(filter(lambda x: x > 1, specs['common']['well_pattern_dimens']))):
                    raise ValueError(f"Multiple well_patterns is not supported for: {specs['common']['well_pattern']}.")

    #
    # ... well(s) section
    #

    if 'production_well_pump' in specs: # treatment for a pump at producer in ORC
        if 'production_well' not in specs:
            raise RuntimeError(f"Required section: production_well not found in the input file.")
        if 'well_length' not in specs['production_well_pump']:
            specs['production_well_pump']['well_length'] = 0.2 * specs['common']['reservoir_depth']
            logging.warning(f"Required value 'well_length' not found in 'production_well_pump'. Assining a default value (=0.2 * reservoir_depth)")
        if 'well_length' not in specs['production_well']:
            specs['production_well']['well_length'] = specs['common']['reservoir_depth'] - specs['production_well_pump']['well_length']
            logging.info(f"well_length for production well not found. Assigning a default value = reservoir_depth - production_well_pump.well_length.")
        elif specs['production_well']['well_length'] + specs['production_well_pump']['well_length'] > specs['common']['reservoir_depth']:
            specs['production_well']['well_length'] = specs['common']['reservoir_depth'] - specs['production_well_pump']['well_length']
            logging.warning(f"Sum of production_well.well_length and production_well_pump.well_length is greater than reservoir_depth. "
                            f"Updating production_well.well_length (=reservoir_depth - production_well_pump.well_length)")
        if 'wellhead_depth' not in specs['production_well']:
            specs['production_well']['wellhead_depth'] = specs['production_well_pump']['well_length']

    #
    # ... reservoir section
    #

    if 'reservoir' in specs: # get effective (average) wellbore diameter for reservoir
        val = 0.41
        if 'injection_well' in specs:
            if 'diameter' in specs['injection_well']:
                val = specs['injection_well']['diameter']
        if 'production_well' in specs:
            if 'diameter' in specs['production_well']:
                val = 0.5 * (val + specs['production_well']['diameter'])
        specs['reservoir']['well_eff_diameter'] = val

    #
    # ... surface section
    #

    if 'common' in specs:
        if 'fluid_name' in specs['common']:
            if specs['common']['fluid_name'] == 'H2O':
                if 'refrigerant' not in specs['surface']:
                    logging.warning(f"'refrigerant' for surface not found. Assigning a default value = 'R245fa'")

    #
    # ... economic section
    #

    if 'economic' in specs:
        if 'project_maturity' not in specs['economic']:
            raise ValueError(f"project_maturity in 'economic' section is not defined.")
        if specs['economic']['project_maturity'].upper() not in PROJECT_MATURITY_OPTIONS:
            raise ValueError(f"project_maturity: {specs['economic']['project_maturity']} is not supported.")

    #TODO: optimize input checking
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


def get_table(fname: str, header: int = 0) -> pd.DataFrame:
    path = fname
    if not os.path.isabs(fname):
        path = os.path.join(Path(__file__).parent.parent.parent, 'data', fname)
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found.")
    try:
        ext = os.path.splitext(path)[1]
        if ext.lower() == '.csv':
            return pd.read_csv(path)
        elif ext.lower() == '.xlsx':
            return pd.read_excel(path, header=header)
        else:
            raise RuntimeError(f"Failed to read {path}. Extension: {ext} is not supported")
    except:
        raise RuntimeError(f"Failed to read {path}.")


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

    if results_econ == None:
        return
    fname = os.path.splitext(input_file)[0] + ".econ.csv"
    logging.info(f"Saving output summary of economic models > {fname}")
    d = dict()
    for key in results_econ.keys():
        d[key] = [results_econ[key]]
    df = pd.DataFrame(d)
    df.to_csv(fname, index=False)


class Struct:
    def __init__(self, **entries):
        self.__dict__.update(entries)

def merge_object_dict(obj, dict):
    d = vars(obj) | dict
    return Struct(**d)