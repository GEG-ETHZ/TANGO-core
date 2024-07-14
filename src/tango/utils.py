import argparse
import os
import logging
import sys
import numpy as np
import pandas as pd
from oyaml import load, SafeLoader
from datetime import datetime
from pathlib import Path
from enum import Enum

from tango.core.config import *
from tango.core.constants import *
from tango.units.native import *
from tango.units.native.well import *
from tango.units.native.surface import *
from tango.units.cmg.imex import *
from tango.units.cmg.gem import *
from tango.units.cmg.coflow import *
from tango.units.external.MOOSE.well.well import *
from tango.units.external.DWSIM.CPG import *
from tango.units.external.MOOSE.reservoir.reservoir import *
from tango.units.native.surface.tespy.CPG import *
from tango.units.native.surface.tespy.tespy_ORC import *
from tango.units.native.surface.tespy.tespy_SF import *
from tango.units.native.surface.tespy.tespy_DF import *
from tango.units.native.unit_reader import *

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


def get_os() -> str:
    if sys.platform.lower().startswith('win'):
        return 'WIN'
    elif sys.platform.lower().startswith('linux'):
        return 'LINUX'
    # sys.platform.lower().startswith('darwin'): # <- mac OS
    else:
        raise RuntimeError(f"OS: {sys.platform} is not supported.")


def check_inputs(specs: dict) -> None:
    required_sections = {'graph': ['nodes', 'edges'],
                         'runspec': ['workflow']}
    for key in required_sections.keys():
        if key not in specs:
            raise RuntimeError(f"'{key}' section (required) is not found")
        for s in required_sections[key]:
            if s not in specs[key]:
                raise RuntimeError(f"'{s}' (required) is not found in section: {key}")
    if len(specs['graph']['nodes']) < 1:
        raise RuntimeError(f"Empty nodes found in 'nodes' section")


def system_name(specs) -> str:
    unit_types = []
    for key in specs['graph']['nodes'].keys():
        node = specs['graph']['nodes'][key]
        sys_name = node['unit'].strip().split('_')[0]
        if 'surface' == node['type']:
            sys_name = node['unit']
        if 'reservoir' in specs['graph']['nodes'] and specs['graph']['nodes']['reservoir'].get('unit') == 'filereader':
            sys_name = 'external'
        if 'reservoir' in specs['graph']['nodes'] and specs['graph']['nodes']['reservoir'].get('unit') == 'filereader':
            sys_name = 'external'
        unit_types.append(node['type'])
    if 'horizontal_well' in unit_types and 'reservoir' not in unit_types:
        sys_name = sys_name.split('_')[0] # AGS
    return sys_name


def get_unit_class(type_: str, unit_name: str) -> object:
    try:
        return eval(UNIT_OPTIONS[type_.lower()][unit_name.lower()])
    except:
        raise ValueError(f"unit type: {type_} is not supported in unit: {unit_name.lower()}.")


def newton(x_lst: list, y_lst: list) -> float:
    dydx = (y_lst[1] - y_lst[0]) / (x_lst[1] - x_lst[0])
    return x_lst[0] - y_lst[0] / dydx


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


def parse_results(d: dict, nodes, current_date:str) -> dict:
    name = 'date'
    if name not in d.keys():
        d[name] = [current_date]
    else:
        d[name].append(current_date)
    for id in nodes:
        state = nodes[id]['unit']
        unit_name = nodes[id]['type']
        if unit_name in REPORT_SETTINGS.keys():
            if REPORT_SETTINGS[unit_name]:
                state = getattr(state, REPORT_SETTINGS[unit_name])
            append_results(d, state, unit_name)


# def states_dict_generator(pp_inclusion, nodes, fluid_states: dict = None) -> dict:
#     if fluid_states is None:
#         fluid_states = {}
#
#     for id in nodes:
#         state = nodes[id]['unit']
#         unit_name = nodes[id]['type']
#         enthalpy = state.outlet_fluid.H
#         pressure = state.outlet_fluid.P
#
#         # if unit_name not in fluid_states:
#         #     fluid_states[unit_name] = []
#         #
#         # fluid_states[unit_name].append((pressure/100000.0, enthalpy/1000.0))
#
#         if((id == 'surface') and (pp_inclusion == 'yes')):
#             for component in state.diagram_states:
#                 enthalpy = state.diagram_states[component].H
#                 pressure = state.diagram_states[component].P
#                 # print(component, 'it is')
#                 if component not in fluid_states:
#                     fluid_states[component] = []
#
#                 fluid_states[component].append((pressure/100000.0, enthalpy/1000.0))
#
#     # print('fluid_stateshere', fluid_states)
#     # print(state.diagram_states, 'kaka')
#
#     return fluid_states

def states_dict_generator(pp_inclusion, nodes, fluid_states: dict = None) -> dict:
    if fluid_states is None:
        fluid_states = {}

    for id in nodes:
        state = nodes[id]['unit']
        unit_name = nodes[id]['type']
        enthalpy = state.outlet_fluid.H
        pressure = state.outlet_fluid.P

        if unit_name not in fluid_states:
            fluid_states[unit_name] = []

        fluid_states[unit_name].append((pressure/100000.0, enthalpy/1000.0))

        if((id == 'surface') and (pp_inclusion == 'yes')):
            for component in state.diagram_states:
                enthalpy = state.diagram_states[component].H
                pressure = state.diagram_states[component].P
                print(component, 'it is')
                if component not in fluid_states:
                    fluid_states[component] = []

                fluid_states[component].append((pressure/100000.0, enthalpy/1000.0))

    # print('fluid_stateshere', fluid_states)

    return fluid_states


def create_connections(pp_inclusion, graph_edges, state):
    connections = []
    # node_mapping = {
    #     'surface': 'surface',
    #     'inj_1': 'injection_well',
    #     'reservoir': 'reservoir',
    #     'prd_1': 'production_well',
    #     'prd_2': 'production_well_pump',
    #     'h_well': 'horizontal_well',
    #     'h_well_1': 'production_well',
    #     'h_well_2': 'production_well'
    # }
    #
    # for edge in graph_edges.values():
    #     source = node_mapping[edge['source']]
    #     target = node_mapping[edge['target']]
    #     connections.append((source, target, 'non-isentropic'))

    # print(connections)
    # print(state.diagram_connections)
    if (pp_inclusion == 'no'):
        combined = connections
    else:
        # combined = connections + state.diagram_connections
        combined = state.diagram_connections
        combined = [conn for conn in combined if conn != ('production_well', 'surface', 'non-isentropic')]

    # print('combinedhere', combined)

    return combined


def create_connections(pp_inclusion, graph_edges, state):
    connections = []
    node_mapping = {
        'surface': 'surface',
        'inj_1': 'injection_well',
        'reservoir': 'reservoir',
        'prd_1': 'production_well',
        'prd_2': 'production_well_pump',
        'h_well': 'horizontal_well',
        'h_well_1': 'production_well',
        'h_well_2': 'production_well'
    }

    for edge in graph_edges.values():
        source = node_mapping[edge['source']]
        target = node_mapping[edge['target']]
        connections.append((source, target, 'non-isentropic'))

    # print(connections)
    # print(state.diagram_connections)
    if (pp_inclusion == 'no'):
        combined = connections
    else:
        combined = connections + state.diagram_connections
        # combined = state.diagram_connections
        combined = [conn for conn in combined if conn != ('production_well', 'surface', 'non-isentropic')]

    # print('combinedhere', combined)

    return combined


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


def write_results(input_file: str, results: tuple) -> None:

    physics_results, econ_results = results

    fname = os.path.splitext(input_file)[0] + ".smry.csv"
    logging.info(f"Saving output summary of physics-based units > {fname}")
    df = pd.DataFrame(physics_results)
    df.to_csv(fname, index=False)

    if econ_results == None:
        return
    fname = os.path.splitext(input_file)[0] + ".econ.csv"
    logging.info(f"Saving output summary of economic units > {fname}")
    d = dict()
    for key in econ_results.keys():
        d[key] = [econ_results[key]]
    df = pd.DataFrame(d)
    df.to_csv(fname, index=False)




