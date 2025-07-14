import subprocess
import re
import csv
import os
import signal


class TangoMooseInterface:
    r"""
    Interface for running and managing MOOSE-based simulations with dynamic boundary condition updates.

    Attributes:
        _pressure_bc_path (str): Path to the pressure boundary condition CSV file.
        _flowrate_bc_path (str): Path to the flowrate boundary condition CSV file.
        _temperature_bc_path (str): Path to the temperature boundary condition CSV file.
        pressure_from_TANGO (float): Initial pressure boundary condition value.
        flowrate_from_TANGO (float): Initial flowrate boundary condition value.
        temperature_from_TANGO (float): Initial temperature boundary condition value.
        pressure_from_MOOSE (float): Pressure value extracted from MOOSE.
        flowrate_from_MOOSE (float): Flowrate value extracted from MOOSE.
        temperature_from_MOOSE (float): Temperature value extracted from MOOSE.
        _process (subprocess.Popen): Subprocess running the MOOSE executable.
    """
    def __init__(self, moose_executable_path,
                 moose_input_path,
                 pressure_bc_file,
                 flowrate_bc_file,
                 temperature_bc_file,
                 specs):
        """
        Initializes the TangoMooseInterface.

        Args:
            moose_executable_path (str): Path to the MOOSE executable.
            moose_input_path (str): Path to the MOOSE input file.
            pressure_bc_file (str): Filename for the pressure boundary condition CSV.
            flowrate_bc_file (str): Filename for the flowrate boundary condition CSV.
            temperature_bc_file (str): Filename for the temperature boundary condition CSV.
        """
        self.MOOSE_specs = specs
        print('interface', self.MOOSE_specs['bc_columns']['pressure_column_index'])
        # print('interface', specs.bc_columns['pressure_column_index'], specs.bc_columns['flowrate_column_index'], specs.bc_columns['temperature_column_index'])
        self._pressure_bc_path = self._set_bc_path(moose_input_path, pressure_bc_file)
        self._flowrate_bc_path = self._set_bc_path(moose_input_path, flowrate_bc_file)
        self._temperature_bc_path = self._set_bc_path(moose_input_path, temperature_bc_file)
        self._setup_process(moose_executable_path, moose_input_path)
        self._set_initial_bc()
        self._setup_csv_file(self._pressure_bc_path, self.pressure_from_TANGO)
        self._setup_csv_file(self._flowrate_bc_path, self.flowrate_from_TANGO)
        self._setup_csv_file(self._temperature_bc_path, self.temperature_from_TANGO)
        self.MOOSE_dt_list = []

    def _set_bc_path(self, moose_input_path, bc_file):
        """
        Constructs the full path for a boundary condition file.

        Args:
            moose_input_path (str): Path to the MOOSE input file.
            bc_file (str): Boundary condition filename.

        Returns:
            str: Full path to the boundary condition file.
        """
        return os.path.join(os.path.dirname(moose_input_path), bc_file)

    def _set_initial_bc(self, pressure=8000000, flowrate=0.02, temperature=300):
        """
        Sets the initial boundary condition values.

        Args:
            pressure (float): Initial pressure (Pa).
            flowrate (float): Initial flowrate (kg/s).
            temperature (float): Initial temperature (K).
        """
        self.pressure_from_TANGO = pressure
        self.flowrate_from_TANGO = flowrate
        self.temperature_from_TANGO = temperature

    def _setup_csv_file(self, path, initial_bc_value):
        """
        Initializes a CSV file with a single row for boundary conditions.

        Args:
            path (str): Path to the CSV file.
            initial_bc_value (float): Initial boundary condition value.
        """
        with open(path, mode='w', newline='', buffering=1) as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow([0.0, initial_bc_value])

    def _setup_process(self, moose_executable_path, moose_input_path):
        """
        Sets up the subprocess for running the MOOSE executable.

        Args:
            moose_executable_path (str): Path to the MOOSE executable.
            moose_input_path (str): Path to the MOOSE input file.
        """
        command = [moose_executable_path, '-i', moose_input_path]
        self._process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, universal_newlines=True)

    def parse_moose_output(self, line):
        """
        Parses MOOSE output for timestep and convergence information.

        Args:
            line (str): A line of MOOSE output.

        Returns:
            tuple: Matches for timestep and convergence patterns.
        """
        timestep_pattern = r"^Time Step (\d+), time = ([\d.]+(?:e[\+\-]?\d+)?), dt = ([\d.]+(?:e[\+\-]?\d+)?)"
        success_pattern = r'Solve Converged!'

        timestep_match = re.search(timestep_pattern, line)
        success_match = re.search(success_pattern, line)

        return timestep_match, success_match

    def extract_timestep_info(self, timestep_match):
        """
        Extracts timestep information from a regex match object.

        Args:
            timestep_match (re.Match): A regex match object containing timestep information.

        Returns:
            tuple: (current_timestep, time, dt) where:
                - current_timestep (int): The current timestep number
                - time (float): The current simulation time
                - dt (float): The timestep size
        """
        current_timestep = int(timestep_match.group(1))
        time = float(timestep_match.group(2))
        dt_raw = timestep_match.group(3)

        dt = float(dt_raw)

        return current_timestep, time, dt

    def _write_csv_row(self, path, time, last_row_value):
        """
        Appends a row to a CSV file for boundary conditions.

        Args:
            path (str): Path to the CSV file.
            time (float): Current simulation time.
            last_row_value (float): Last recorded boundary condition value.
        """
        with open(path, mode='a', newline='', buffering=1) as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow([time, last_row_value])

    def get_last_row_value(self, path):
        """
        Retrieves the last row value from a CSV file.

        Args:
            path (str): Path to the CSV file.

        Returns:
            tuple: Last row values for pressure, flowrate, and temperature.

        Raises:
            FileNotFoundError: If the CSV file is not found.
            ValueError: If the CSV file does not contain data rows.
        """
        try:
            with open(path, mode='r', newline='') as csv_file:
                csv_reader = csv.reader(csv_file)
                rows = list(csv_reader)
                if len(rows) > 1:
                    last_row = rows[-1]
                    return float(last_row[self.MOOSE_specs['bc_columns']['pressure_column_index']]),\
                           float(last_row[self.MOOSE_specs['bc_columns']['flowrate_column_index']]),\
                           float(last_row[self.MOOSE_specs['bc_columns']['temperature_column_index']])
                else:
                    raise ValueError("CSV file does not contain data rows.")
        except FileNotFoundError as e:
            raise FileNotFoundError(f"CSV file not found at path: {path}") from e
        except (ValueError, IndexError) as e:
            raise ValueError("Error while parsing CSV data.") from e

    def _run_moose_simulation(self, post_processor_path):
        """
        Executes the MOOSE simulation and updates boundary conditions dynamically.

        Args:
            post_processor_path (str): Path to the post-processor file.
        """
        self._process.send_signal(signal.SIGCONT)

        for line in self._process.stdout:
            print(line.strip())
            timestep_match, success_match = self.parse_moose_output(line)
            if timestep_match:
                current_timestep, time, dt = self.extract_timestep_info(timestep_match)

                raw_dt = timestep_match.group(3)
                print(f"Raw dt: '{raw_dt}', Parsed dt: {dt}, Type: {type(dt)}")

                self.MOOSE_dt_list.append(dt)
                print(f"MOOSE_dt_list after append: {self.MOOSE_dt_list}")

                self._write_csv_row(self._pressure_bc_path, time, self.pressure_from_TANGO)
                self._write_csv_row(self._temperature_bc_path, time, self.temperature_from_TANGO)
                self._write_csv_row(self._flowrate_bc_path, time, self.flowrate_from_TANGO)
                if int(current_timestep) > 1:
                    self.pressure_from_MOOSE, self.flowrate_from_MOOSE, self.temperature_from_MOOSE = self.get_last_row_value(post_processor_path)
                else:
                    self.pressure_from_MOOSE = self.pressure_from_TANGO
                    self.flowrate_from_MOOSE = self.flowrate_from_TANGO
                    self.temperature_from_MOOSE = self.temperature_from_TANGO
                self._process.send_signal(signal.SIGSTOP)
                break

    def run(self, post_processor_path):
        """
        Runs the MOOSE simulation and updates the boundary conditions.

        Args:
            post_processor_path (str): Path to the post-processor file.
        """
        try:
            self._run_moose_simulation(post_processor_path)
        except subprocess.CalledProcessError as e:
            print(f"Error running MOOSE: {e}")
        except Exception as e:
            print(f"An error occurred: {e}")
