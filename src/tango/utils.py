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
from tango.time_stepper import LinearInterpolation
from typing import Dict, Any
import csv

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


# def load_from_yaml(filename: str):
#     try:
#         with open(filename) as f:
#             specs = load(f, Loader=SafeLoader)
#     except Exception:
#         raise RuntimeError(f"Failed to read {filename}")
#     check_inputs(specs)
#
#     try:
#         time_config = specs["schedule"].get("time", {})
#
#     except KeyError as e:
#         raise RuntimeError(f"Missing expected time subblock key in YAML: {e}")
#
#     if (specs["schedule"]["time"]['type'] == "ConstantDT"):
#         specs["schedule"]["num_tsteps"] = time_config["num_tsteps"]
#         specs["schedule"]["dt"] = time_config["dt"]
#
#     time_type = specs["schedule"]["time"]['type']
#
#     if time_type == "FunctionDT":
#         time_list = specs["functions"]['dts']['time']
#         dt_list = specs["functions"]['dts']['dt']
#         end_time = specs["functions"]['dts']['end_time']
#
#         interpolator = LinearInterpolation(time_list, dt_list)
#
#         # Generate interpolated time steps
#         current_time = time_list[0]
#         result = []
#         dt_list = []  # List to store only the time steps
#
#         while current_time <= end_time:
#             step = interpolator.sample(current_time)
#             next_time = current_time + step
#             if next_time > end_time:
#                 step = end_time - current_time
#                 next_time = end_time
#             result.append((step, current_time))
#             dt_list.append(float(step))  # Convert to Python float
#             if next_time == end_time:
#                 time_list.append(float(end_time))  # Ensure end_time is added
#                 break
#             current_time = next_time
#
#         specs["schedule"]['dt_list'] = [float(step[0]) for step in result]
#
#         print(dt_list)
#
#         print(specs["schedule"]['dt_list'])
#
#         for time_step, time in result:
#             print(f"Time Step: {time_step:.4f}, Time: {time:.4f}")
#
#     elif time_type == "ConstantDT":
#         # Generate a list with `num_tsteps` members, each having the value of `dt`
#         num_tsteps = specs["schedule"]["num_tsteps"]
#         dt = specs["schedule"]["dt"]
#         specs["schedule"]['dt_list'] = [dt] * num_tsteps  # Create the constant DT list
#
#         print(specs["schedule"]['dt_list'])
#
#     else:
#         raise RuntimeError(f"Unsupported time type: {time_type}")
#
#     return specs


def load_from_yaml(filename: str) -> Dict[str, Any]:
    """
    Load specifications from a YAML file, validate them, and process time configurations.

    Args:
        filename (str): The path to the YAML file.

    Returns:
        Dict[str, Any]: A dictionary containing the processed specifications.

    Raises:
        RuntimeError: If there is an issue reading the YAML file or processing its contents.
    """
    try:
        # Load the YAML file
        with open(filename, 'r') as file:
            specs = yaml.load(file, Loader=SafeLoader)
    except Exception as e:
        raise RuntimeError(f"Failed to read {filename}: {e}")

    # Validate inputs
    check_inputs(specs)  # Ensure this function is properly implemented elsewhere

    # Extract and validate time configuration
    try:
        time_config = specs["schedule"].get("time", {})
        time_type = time_config.get("type")
    except KeyError as e:
        raise RuntimeError(f"Missing expected key in YAML: {e}")

    if time_type not in {"ConstantDT", "FunctionDT"}:
        raise RuntimeError(f"Unsupported time type: {time_type}")

    if time_type == "ConstantDT":
        _process_constant_dt(specs, time_config)
    elif time_type == "FunctionDT":
        _process_function_dt(specs, time_config)

    return specs


def _process_constant_dt(specs: Dict[str, Any], time_config: Dict[str, Any]) -> None:
    """
    Process constant time step configuration.

    Args:
        specs (Dict[str, Any]): The specifications dictionary.
        time_config (Dict[str, Any]): The time configuration dictionary.

    Raises:
        KeyError: If required keys are missing.
    """
    try:
        num_tsteps = time_config["num_tsteps"]
        dt = time_config["dt"]
    except KeyError as e:
        raise RuntimeError(f"Missing required key for ConstantDT: {e}")

    # Create a list of constant time steps
    specs["schedule"]['dt_list'] = [dt] * num_tsteps


# def _process_function_dt(specs: Dict[str, Any], time_config: Dict[str, Any]) -> None:
#     """
#     Process function-based time step configuration.
#
#     Args:
#         specs (Dict[str, Any]): The specifications dictionary.
#         time_config (Dict[str, Any]): The time configuration dictionary.
#
#     Raises:
#         RuntimeError: If required keys for function-based DT are missing.
#     """
#     try:
#         # Get the function name from the schedule's time configuration
#         function_name = specs["schedule"]["time"]["function"]
#
#         # Retrieve the function details from the specs
#         function_data = specs["functions"][function_name]
#         time_list = function_data["time"]
#         dt_list = function_data["dt"]
#         end_time = function_data["end_time"]
#     except KeyError as e:
#         raise RuntimeError(f"Missing required key for FunctionDT or invalid function reference: {e}")
#
#     # Initialize the interpolator
#     interpolator = LinearInterpolation(time_list, dt_list)
#     current_time = time_list[0]
#     result = []
#
#     # Generate interpolated time steps
#     while current_time <= end_time:
#         step = interpolator.sample(current_time)
#         next_time = current_time + step
#
#         # Ensure the final step does not exceed the end time
#         if next_time > end_time:
#             step = end_time - current_time
#             next_time = end_time
#
#         result.append((step, current_time))
#
#         if next_time == end_time:
#             break
#
#         current_time = next_time
#
#     # Store the interpolated time steps
#     specs["schedule"]['dt_list'] = [float(step[0]) for step in result]





def _process_function_dt(specs: Dict[str, Any], time_config: Dict[str, Any]) -> None:
    """
    Process function-based time step configuration.

    Args:
        specs (Dict[str, Any]): The specifications dictionary.
        time_config (Dict[str, Any]): The time configuration dictionary.

    Raises:
        RuntimeError: If required keys for function-based DT are missing.
    """
    try:
        function_name = specs["schedule"]["time"]["function"]
        function_data = specs["functions"][function_name]

        if function_data["type"] == "segmented_linear_csv":
            csv_file = function_data["file"]
            end_time = function_data["end_time"]
            time_list, dt_list = _read_csv_time_dt(csv_file)
        elif function_data["type"] == "segmented_linear":
            time_list = function_data["time"]
            dt_list = function_data["dt"]
            end_time = function_data["end_time"]
        elif function_data["type"] == "irregular_csv":
            csv_file = function_data["file"]
            dt_list = _read_csv_single_column(csv_file)
            specs["schedule"]['dt_list'] = dt_list
            return
        else:
            raise RuntimeError(f"Unsupported function type: {function_data['type']}")
    except KeyError as e:
        raise RuntimeError(f"Missing required key for FunctionDT or invalid function reference: {e}")

    interpolator = LinearInterpolation(time_list, dt_list)
    current_time = time_list[0]
    result = []

    while current_time <= end_time:
        step = interpolator.sample(current_time)
        next_time = current_time + step

        if next_time > end_time:
            step = end_time - current_time
            next_time = end_time

        result.append((step, current_time))

        if next_time == end_time:
            break

        current_time = next_time

    specs["schedule"]['dt_list'] = [float(step[0]) for step in result]


def _read_csv_single_column(csv_file: str) -> list:
    """
    Read a single-column CSV file and return the list of values.

    Args:
        csv_file (str): Path to the CSV file.

    Returns:
        list: A list of time step values (dt).

    Raises:
        RuntimeError: If the file cannot be read or is malformed.
    """
    dt_list = []

    try:
        with open(csv_file, 'r') as file:
            reader = csv.reader(file)
            for row in reader:
                if len(row) != 1:
                    raise RuntimeError(f"Malformed row in CSV file: {row}")
                dt_list.append(float(row[0]))
    except Exception as e:
        raise RuntimeError(f"Error reading CSV file {csv_file}: {e}")

    return dt_list


def _read_csv_time_dt(csv_file: str) -> (list, list):
    """
    Read time and dt values from a CSV file.

    Args:
        csv_file (str): Path to the CSV file.

    Returns:
        (list, list): A tuple of two lists: time values and dt values.

    Raises:
        RuntimeError: If the file cannot be read or is malformed.
    """
    time_list = []
    dt_list = []

    try:
        with open(csv_file, 'r') as file:
            reader = csv.reader(file)
            for row in reader:
                if len(row) < 2:
                    raise RuntimeError(f"Malformed row in CSV file: {row}")
                time_list.append(float(row[0]))
                dt_list.append(float(row[1]))
    except Exception as e:
        raise RuntimeError(f"Error reading CSV file {csv_file}: {e}")

    return time_list, dt_list




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
        if specs['schedule']['bc_iteration_checkpoint'] == 'injection_well_bottom':
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


def states_dict_generator(pp_inclusion, nodes, plant_name, fluid_states: dict = None) -> dict:
    if fluid_states is None:
        fluid_states = {}

    for id in nodes:
        state = nodes[id]['unit']
        unit_name = nodes[id]['type']
        enthalpy = state.outlet_fluid.H
        pressure = state.outlet_fluid.P

        if (plant_name != 'SurfaceUnitORCNative'):
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

    return fluid_states


def create_connections(pp_inclusion, graph_edges, state):
    connections = []
    if (state.__class__.__name__ != 'SurfaceUnitORCNative'):
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

    if (pp_inclusion == 'no'):
        combined = connections
    else:
        combined = connections + state.diagram_connections
        combined = [conn for conn in combined if conn != ('production_well', 'surface', 'non-isentropic')]

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
    # print(physics_results)
    # for key, value in physics_results.items():
    #     print(f"{key}: {len(value)}")
    physics_results.pop('surface__condensation_temperature_range', None)
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
