import subprocess
import re
import csv
import os
import signal


class TangoMooseInterface:
    def __init__(self, moose_executable_path,
                 moose_input_path,
                 pressure_bc_file,
                 flowrate_bc_file,
                 temperature_bc_file):

        self._pressure_bc_path = self._set_bc_path(moose_input_path, pressure_bc_file)
        self._flowrate_bc_path = self._set_bc_path(moose_input_path, flowrate_bc_file)
        self._temperature_bc_path = self._set_bc_path(moose_input_path, temperature_bc_file)

        self._setup_process(moose_executable_path, moose_input_path)

        self._set_initial_bc()

        self._setup_csv_file(self._pressure_bc_path, self.pressure_from_TANGO)
        self._setup_csv_file(self._flowrate_bc_path, self.flowrate_from_TANGO)
        self._setup_csv_file(self._temperature_bc_path, self.temperature_from_TANGO)


    def _set_bc_path(self, moose_input_path, bc_file):
        return os.path.join(os.path.dirname(moose_input_path), bc_file)


    # TODO: the intial BC values should come from the other unit, but it cause convergence issues in MOOSE
    # (rapis jump of BC over a short period)
    def _set_initial_bc(self, pressure=8000000, flowrate=0.02, temperature=300):
        self.pressure_from_TANGO = pressure
        self.flowrate_from_TANGO = flowrate
        self.temperature_from_TANGO = temperature


    def _setup_csv_file(self, path, initial_bc_value):
        with open(path, mode='w', newline='', buffering=1) as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow([0.0, initial_bc_value])


    def _setup_process(self, moose_executable_path, moose_input_path):
        command = [moose_executable_path, '-i', moose_input_path]
        self._process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, universal_newlines=True)


    def parse_moose_output(self, line):
        timestep_pattern = r"^Time Step (\d+), time = ([\d.]+(?:e[\+\-]?\d+)?), dt = ([\d.]+(?:e[\+\-]?\d+)?)"
        success_pattern = r'Solve Converged!'
        timestep_match = re.search(timestep_pattern, line)
        success_match = re.search(success_pattern, line)
        return timestep_match, success_match


    def extract_timestep_info(self, timestep_match):
        current_timestep = int(timestep_match.group(1))
        time = float(timestep_match.group(2))
        dt = float(timestep_match.group(3))
        return current_timestep, time, dt


    def print_timestep_info(self, current_timestep, time, dt):
        print(f"Time Step {current_timestep}, time = {time}, dt = {dt:.2f}")


    def _write_csv_row(self, path, time, last_row_value):
        with open(path, mode='a', newline='', buffering=1) as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow([time, last_row_value])


    def read_csv_contents(self, CSV_file_path):
        try:
            with open(CSV_file_path, mode='r', newline='') as csv_file:
                print("Current CSV contents:")
                for line in csv_file:
                    print(line.strip())
        except FileNotFoundError as e:
            print(f"CSV file not found at path: {CSV_file_path}")
        except Exception as e:
            print(f"An error occurred while printing CSV contents: {e}")


    def get_last_row_value(self, path):
        try:
            with open(path, mode='r', newline='') as csv_file:
                csv_reader = csv.reader(csv_file)
                rows = list(csv_reader)
                if len(rows) > 1:
                    last_row = rows[-1]
                    return (float(last_row[1]), float(last_row[2]), float(last_row[3]))
                else:
                    raise ValueError("CSV file does not contain data rows.")
        except FileNotFoundError as e:
            raise FileNotFoundError(f"CSV file not found at path: {path}") from e
        except (ValueError, IndexError) as e:
            raise ValueError("Error while parsing CSV data.") from e


    def _run_moose_simulation(self, post_processor_path):
        self._process.send_signal(signal.SIGCONT)
        for line in self._process.stdout:
            print(line.strip())
            timestep_match, success_match = self.parse_moose_output(line)
            if timestep_match:
                current_timestep, time, dt = self.extract_timestep_info(timestep_match)
                self._write_csv_row(self._pressure_bc_path, time, self.pressure_from_TANGO)
                self._write_csv_row(self._temperature_bc_path, time, self.temperature_from_TANGO)
                self._write_csv_row(self._flowrate_bc_path, time, self.flowrate_from_TANGO)
                if int(current_timestep) > 1:
                    self.pressure_from_MOOSE, self.flowrate_from_MOOSE, self.temperature_from_MOOSE = self.get_last_row_value(post_processor_path)
                else:
                    self.pressure_from_MOOSE = self.pressure_from_TANGO
                    self.flowrate_from_MOOSE = self.flowrate_from_TANGO
                    self.temperature_from_MOOSE = self.temperature_from_TANGO
                # self.read_csv_contents(self._pressure_bc_path)
                # self.read_csv_contents(self._temperature_bc_path)
                self._process.send_signal(signal.SIGSTOP)
                break


    def run(self, post_processor_path):
        try:
            self._run_moose_simulation(post_processor_path)
        except subprocess.CalledProcessError as e:
            print(f"Error running MOOSE: {e}")
        except Exception as e:
            print(f"An error occurred: {e}")
