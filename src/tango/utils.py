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
    """
    Parses command-line arguments for the TANGO application.

    Args:
        args (list): List of command-line arguments.

    Returns:
        argparse.Namespace: Parsed arguments with the following attributes:
            - `input_file` (str): Path to the input YAML file.
            - `debug` (bool): Whether to enable debug logging.

    Example:
        >>> args = parse_args(['-f', 'input.yml', '--debug'])
    """
    parser = argparse.ArgumentParser(description='TANGO - Techno-economic ANalysis of GeOthermal power simulator')
    parser.add_argument('-f',
                        '--file',
                        dest='input_file',
                        help='Input file (.yml)',
                        required=True)
    parser.add_argument('-d',
                        '--debug',
                        dest='debug',
                        help='Set log level to DEBUG',
                        required=False,
                        default=False,
                        action=argparse.BooleanOptionalAction)
    return parser.parse_args(args)


def set_logger(args):
    """
    Sets up logging for the TANGO application.

    Args:
        args (argparse.Namespace): Parsed arguments containing:
            - `input_file` (str): Path to the input YAML file.
            - `debug` (bool): Whether to enable debug logging.

    Raises:
        FileNotFoundError: If the input file specified in `args` does not exist.

    Behavior:
        - Logs messages to a log file named after the input file (with `.log` extension).
        - Logs messages to the console.
        - Adjusts log level based on the `debug` flag.
    """
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


def load_from_yaml(filename: str) -> Dict[str, Any]:
    """
    Loads and validates specifications from a YAML file.

    Args:
        filename (str): Path to the YAML file.

    Returns:
        Dict[str, Any]: A dictionary containing the processed specifications.

    Raises:
        RuntimeError: If there is an issue reading the YAML file or processing its contents.

    Behavior:
        - Reads the YAML file and parses its content.
        - Validates the parsed specifications using `check_inputs`.
        - Processes time configurations based on the `type` field in the "schedule" section.
        - Supports `ConstantDT` and `FunctionDT` time types.

    Example:
        >>> specs = load_from_yaml("input.yml")
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
    Processes constant time step configuration.

    This function generates a list of constant time steps based on the `dt` (time step size) and
    `num_tsteps` (number of time steps) specified in the configuration.

    Args:
        specs (Dict[str, Any]): The specifications dictionary to be updated.
        time_config (Dict[str, Any]): The time configuration dictionary containing:
            - `num_tsteps` (int): Number of time steps.
            - `dt` (float): Size of each time step.

    Raises:
        KeyError: If `num_tsteps` or `dt` is missing in `time_config`.

    Example:
        >>> specs = {"schedule": {}}
        >>> time_config = {"num_tsteps": 10, "dt": 0.5}
        >>> _process_constant_dt(specs, time_config)
        >>> specs["schedule"]['dt_list']
        [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
    """
    try:
        num_tsteps = time_config["num_tsteps"]
        dt = time_config["dt"]
    except KeyError as e:
        raise RuntimeError(f"Missing required key for ConstantDT: {e}")

    # Create a list of constant time steps
    specs["schedule"]['dt_list'] = [dt] * num_tsteps


def _process_function_dt(specs: Dict[str, Any], time_config: Dict[str, Any]) -> None:
    """
    Processes function-based time step configuration.

    This function generates a dynamic time step list based on a user-defined function.
    It supports various function types, including segmented linear interpolation and irregular time steps.

    Args:
        specs (Dict[str, Any]): The specifications dictionary to be updated.
        time_config (Dict[str, Any]): The time configuration dictionary containing the function reference.

    Supported Function Types:
        - `segmented_linear_csv`: Time and time step data are read from a CSV file.
        - `segmented_linear`: Time and time step data are defined directly in the specifications.
        - `irregular_csv`: Time steps are defined in a single-column CSV file.

    Raises:
        RuntimeError: If the function type is unsupported or required keys are missing.

    Example:
        >>> specs = {
        ...     "schedule": {"time": {"function": "my_function"}},
        ...     "functions": {
        ...         "my_function": {
        ...             "type": "segmented_linear",
        ...             "time": [0, 1, 2],
        ...             "dt": [0.1, 0.2, 0.3],
        ...             "end_time": 2.0
        ...         }
        ...     }
        ... }
        >>> _process_function_dt(specs, specs["schedule"]["time"])
        >>> specs["schedule"]['dt_list']
        [0.1, 0.2, 0.3]
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
    Reads a single-column CSV file and returns a list of values.

    Args:
        csv_file (str): Path to the CSV file.

    Returns:
        list: A list of time step values (`dt`).

    Raises:
        RuntimeError: If the file cannot be read or contains malformed rows.

    Example:
        CSV file content:
        ```
        0.1
        0.2
        0.3
        ```

        >>> _read_csv_single_column("time_steps.csv")
        [0.1, 0.2, 0.3]
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
    Reads time and `dt` values from a two-column CSV file.

    Args:
        csv_file (str): Path to the CSV file.

    Returns:
        (list, list): A tuple containing:
            - `time_list` (list): List of time values.
            - `dt_list` (list): List of corresponding `dt` values.

    Raises:
        RuntimeError: If the file cannot be read or contains malformed rows.

    Example:
        CSV file content:
        ```
        0, 0.1
        1, 0.2
        2, 0.3
        ```

        >>> _read_csv_time_dt("time_steps.csv")
        ([0.0, 1.0, 2.0], [0.1, 0.2, 0.3])
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
    """
    Determines the operating system type.

    Returns:
        str: The operating system type, either:
            - `'WIN'` for Windows,
            - `'LINUX'` for Linux.

    Raises:
        RuntimeError: If the operating system is unsupported.

    Example:
        >>> get_os()
        'LINUX'
    """
    if sys.platform.lower().startswith('win'):
        return 'WIN'
    elif sys.platform.lower().startswith('linux'):
        return 'LINUX'
    else:
        raise RuntimeError(f"OS: {sys.platform} is not supported.")


def check_inputs(specs: dict) -> None:
    """
    Validates the required sections and elements in the specifications.

    Args:
        specs (dict): The specifications dictionary.

    Raises:
        RuntimeError:
            If required sections or elements are missing, or if `nodes` is empty.

    Required Structure:
        - `graph` section:
            - Must contain `nodes` (non-empty).
            - Must contain `edges`.
        - `runspec` section:
            - Must contain `workflow`.

    Example:
        Valid specs:

        .. code-block:: python

            specs = {
                "graph": {
                    "nodes": ["A", "B"],
                    "edges": [["A", "B"]]
                },
                "runspec": {
                    "workflow": "example_workflow"
                }
            }

        >>> check_inputs(specs)
        # No errors if valid.
    """
    required_sections = {
        'graph': ['nodes', 'edges'],
        'runspec': ['workflow']
    }
    for key in required_sections.keys():
        if key not in specs:
            raise RuntimeError(f"'{key}' section (required) is not found")
        for s in required_sections[key]:
            if s not in specs[key]:
                raise RuntimeError(f"'{s}' (required) is not found in section: {key}")
    if len(specs['graph']['nodes']) < 1:
        raise RuntimeError(f"Empty nodes found in 'nodes' section")

def system_name(specs) -> str:
    """
    Determines the system name based on the specifications.

    Args:
        specs (dict): The specifications dictionary containing the system's graph and schedule.

    Returns:
        str: The system name.

    Logic:
        - Extracts the `unit` and `type` of each node in the system graph.
        - Adjusts the system name for specific cases:
            - If the reservoir node uses an external file reader.
            - If the boundary condition iteration checkpoint is at the injection well bottom.
            - If the system includes a horizontal well but no reservoir.

    Example:
        .. code-block:: python

            specs = {
                "graph": {
                    "nodes": {
                        "surface": {"unit": "SurfaceUnit", "type": "surface"}
                    }
                },
                "schedule": {"bc_iteration_checkpoint": "injection_well_bottom"}
            }
            print(system_name(specs))  # Output: 'external'
    """
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
        sys_name = sys_name.split('_')[0]
    return sys_name

def get_unit_class(type_: str, unit_name: str) -> object:
    """
    Retrieves the unit class based on the type and unit name.

    Args:
        type_ (str): The type of the unit.
        unit_name (str): The name of the unit.

    Returns:
        object: The class object corresponding to the unit.

    Raises:
        ValueError: If the type or unit name is unsupported.

    Example:
        >>> get_unit_class("surface", "turbine")
    """
    try:
        return eval(UNIT_OPTIONS[type_.lower()][unit_name.lower()])
    except:
        raise ValueError(f"unit type: {type_} is not supported in unit: {unit_name.lower()}.")


def newton(x_lst: list, y_lst: list) -> float:
    """
    Performs a single iteration of the Newton-Raphson method.

    Args:
        x_lst (list): List of two x-values.
        y_lst (list): List of two corresponding y-values.

    Returns:
        float: The root estimate.

    Example:
        >>> newton([1, 2], [2, 0])
        1.5
    """
    dydx = (y_lst[1] - y_lst[0]) / (x_lst[1] - x_lst[0])
    return x_lst[0] - y_lst[0] / dydx


def get_table(fname: str, header: int = 0) -> pd.DataFrame:
    """
    Reads a table from a file and returns it as a Pandas DataFrame.

    Args:
        fname (str): Path to the file.
        header (int, optional): Row to use as header (default: 0).

    Returns:
        pd.DataFrame: The table as a DataFrame.

    Raises:
        FileNotFoundError: If the file does not exist.
        RuntimeError: If the file extension is unsupported or the file cannot be read.

    Supported File Types:
        - CSV
        - XLSX

    Example:
        >>> get_table("data.csv")
    """
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


def parse_results(d: dict, nodes, current_date: str) -> dict:
    """
    Parses results from nodes and appends them to the results dictionary.

    Args:
        d (dict): The results dictionary.
        nodes (dict): Dictionary of nodes with their states.
        current_date (str): Current date to append to the results.

    Returns:
        dict: The updated results dictionary.

    Example:
        >>> d = {}
        >>> nodes = {"node1": {"unit": UnitState(), "type": "turbine"}}
        >>> parse_results(d, nodes, "2024-12-11")
    """
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
    """
    Generates a dictionary of fluid states for nodes in the system.

    Args:
        pp_inclusion (str): Whether to include power plant components ('yes' or 'no').
        nodes (dict): Dictionary of nodes with their states.
        plant_name (str): Name of the plant.
        fluid_states (dict, optional): Dictionary to store fluid states (default: None).

    Returns:
        dict: The updated fluid states dictionary.

    Example:
        >>> states_dict_generator("yes", nodes, "SurfaceUnitORCNative")
    """
    if fluid_states is None:
        fluid_states = {}

    for id in nodes:
        state = nodes[id]['unit']
        unit_name = nodes[id]['type']
        enthalpy = state.outlet_fluid.H
        pressure = state.outlet_fluid.P

        if plant_name != 'SurfaceUnitORCNative':
            if unit_name not in fluid_states:
                fluid_states[unit_name] = []
            fluid_states[unit_name].append((pressure / 100000.0, enthalpy / 1000.0))

        if id == 'surface' and pp_inclusion == 'yes':
            for component in state.diagram_states:
                enthalpy = state.diagram_states[component].H
                pressure = state.diagram_states[component].P
                if component not in fluid_states:
                    fluid_states[component] = []

                fluid_states[component].append((pressure / 100000.0, enthalpy / 1000.0))

    return fluid_states



def create_connections(pp_inclusion, graph_edges, state):
    """
    Creates a list of connections for the system based on graph edges and the state.

    Args:
        pp_inclusion (str): Whether to include power plant components ('yes' or 'no').
        graph_edges (dict): Dictionary of edges representing the system graph.
        state (object): The current state of the system.

    Returns:
        list: A list of tuples representing connections in the format:
              (source, target, connection_type).

    Logic:
    - Maps node identifiers in `graph_edges` to their corresponding system components.
    - Adds connections based on `state.diagram_connections` if `pp_inclusion` is `'yes'`.
    - Filters out specific connections such as `('production_well', 'surface', 'non-isentropic')`.

    Example:
        >>> graph_edges = {"e1": {"source": "prd_1", "target": "surface"}}
        >>> create_connections("yes", graph_edges, state)
        [('production_well', 'surface', 'non-isentropic')]
    """
    connections = []
    if state.__class__.__name__ != 'SurfaceUnitORCNative':
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

    if pp_inclusion == 'no':
        combined = connections
    else:
        combined = connections + state.diagram_connections
        combined = [conn for conn in combined if conn != ('production_well', 'surface', 'non-isentropic')]

    return combined


def append_results(d: dict, state: classmethod, base_name: str) -> None:
    """
    Appends the results from a given state to a dictionary.

    Args:
        d (dict): Dictionary to store results.
        state (object): The state object containing variables to append.
        base_name (str): Base name used as a prefix for the keys in the dictionary.

    Logic:
    - Iterates through all attributes of the `state` object.
    - Filters out attributes starting with "__" or those listed in `SKIP_REPORT_ATTRIBUTES`.
    - Appends float-type values to the dictionary under keys prefixed with `base_name`.

    Example:
        >>> d = {}
        >>> append_results(d, state, "unit1")
    """
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
    """
    Writes the simulation results to CSV files.

    Args:
        input_file (str): Path to the input file used for the simulation.
        results (tuple): A tuple containing:
            - `physics_results` (dict): Results from physics-based units.
            - `econ_results` (dict): Results from economic-based units.

    Logic:
    - Saves `physics_results` to a CSV file named `<input_file>.smry.csv`.
    - Saves `econ_results` (if available) to a CSV file named `<input_file>.econ.csv`.
    - Removes specific keys, such as `'surface__condensation_temperature_range'`, from the physics results.

    Example:
        >>> write_results("input.yml", (physics_results, econ_results))
    """
    physics_results, econ_results = results

    fname = os.path.splitext(input_file)[0] + ".smry.csv"
    logging.info(f"Saving output summary of physics-based units > {fname}")
    physics_results.pop('surface__condensation_temperature_range', None)
    df = pd.DataFrame(physics_results)
    df.to_csv(fname, index=False)

    if econ_results is None:
        return

    fname = os.path.splitext(input_file)[0] + ".econ.csv"
    logging.info(f"Saving output summary of economic units > {fname}")
    d = dict()
    for key in econ_results.keys():
        d[key] = [econ_results[key]]
    df = pd.DataFrame(d)
    df.to_csv(fname, index=False)

