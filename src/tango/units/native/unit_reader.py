import numpy as np
from math import erfc
from math import e as exp

from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION
from tango.core.abstracts.unit import *
from tango.units.dataclasses import ReservoirSpecsNative
from tango.units.check_fracing import calculate_injection_rate
import csv
import os
import logging


class ReservoirFileReaderUnit(Unit):
    """
    Represents a reservoir unit (1-D well-pair) that reads state data from a file.

    This class simulates the reservoir state based on Adams et al. (2015) and allows
    initialization of fluid states and updates using CSV data. It is designed to read
    inlet and outlet fluid properties from a specified file and perform calculations
    for each simulation step.

    Attributes:
        specs (ReservoirSpecsNative): Specifications for the reservoir unit.
        inlet_fluid (FluidState): Fluid state at the inlet.
        outlet_fluid (FluidState): Fluid state at the outlet.
        csv_data (list): CSV data containing fluid states.
        current_row (int): Index of the current row being processed from the CSV file.
        m_dot (float): Mass flow rate at the well-pair level.
        m_dot_mult (float): Multiplier to convert injection flow rate to mass flow rate.
    """

    def __init__(self, id: str, specs: dict) -> None:
        """
        Initializes a new instance of the ReservoirFileReaderUnit class.

        Args:
            id (str): Unique identifier for the reservoir unit.
            specs (dict): Specifications for the reservoir unit.
        """
        super().__init__(id, specs)
        self.specs = ReservoirSpecsNative.from_dict(self._process_specs(specs))
        self._specs_post_processor()
        self.init_stream_interface()
        self.csv_data = self._read_csv_file()
        self.current_row = -1

    def init_stream_interface(self, P: float = None, T: float = None) -> None:
        """
        Initializes the fluid interface for the reservoir.

        Args:
            P (float, optional): Initial pressure (Pa). Defaults to 30,000,000 Pa.
            T (float, optional): Initial temperature (K). Defaults to 323.25 K.
        """
        self.inlet_fluid = FluidState.withPT(self.fluid_name, 30000000, 323.25)
        self.outlet_fluid = FluidState.withPT(self.fluid_name, 30000000, 323.25)

    def stream_interface(self) -> None:
        """
        Updates the stream interface, reading fluid properties from the file and
        updating the outlet fluid state.

        This method reads the current row in the CSV data, calculates the outlet
        pressure and temperature, and updates the outlet fluid state.

        Warnings:
            - If the end of the CSV file is reached, the method returns the last known values.

        Prints:
            - Inlet and outlet fluid conditions.
        """
        outlet_pressure, outlet_temperature, mass_rate = self.process_stream()
        self.outlet_fluid.updatePT(outlet_pressure, outlet_temperature)

        print('\n')
        print(f'File reader inlet -> P = {self.inlet_fluid.P}, T = {self.inlet_fluid.T}')
        print(f'File reader outlet -> P = {self.outlet_fluid.P}, T = {self.outlet_fluid.T}')

    def process_stream(self) -> tuple:
        """
        Processes the current stream data from the CSV file.

        This method reads the current row in the CSV file, extracts pressure and temperature,
        and computes the mass flow rate.

        Returns:
            tuple: (float, float, float) representing outlet pressure (Pa), outlet temperature (K), and mass flow rate (kg/s).

        Warnings:
            - If the end of the CSV file is reached, the method returns the last known values and logs a warning.
        """
        if self.current_row < len(self.csv_data):
            row = self.csv_data[self.current_row]
            pressure = float(row[1])
            temperature = float(row[2])

            self.m_dot = self.m_dot_mult * self.mass_rate

            return pressure, temperature, self.m_dot
        else:
            logging.warning("End of the CSV file reached.")
            return self.outlet_fluid.P, self.outlet_fluid.T, self.m_dot

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _read_csv_file(self) -> list:
        """
        Reads the CSV file containing fluid state data.

        Returns:
            list: List of rows from the CSV file, excluding the header row.

        Raises:
            FileNotFoundError: If the specified CSV file does not exist.
        """
        file_path = self.specs.outlet_state
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"The CSV file does not exist at {file_path}")

        with open(file_path, 'r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row
            return list(reader)

    def _specs_post_processor(self) -> None:
        """
        Processes the reservoir specifications and initializes key attributes.

        This method configures:
            - Fluid name.
            - Well pattern.
            - Mass flow rate multiplier.
        """
        self.fluid_name = self.specs.fluid_name
        self.well_pattern = self.specs.well_pattern.upper()
        self._initialize_mdot_mult()

    def _process_specs(self, specs: dict) -> dict:
        """
        Processes the reservoir specifications and computes derived parameters.

        This method ensures the effective well diameter is computed if not already specified,
        and merges common and reservoir-specific specifications.

        Args:
            specs (dict): Input specifications for the reservoir.

        Returns:
            dict: Processed specifications with all required parameters.

        Process:
            - If `well_eff_diameter` is not specified:
                - Use the diameter of the injection and production wells to compute an effective diameter.
                - Defaults to 0.41 m if no values are provided.
            - Merge common and reservoir-specific specs.
        """
        if 'well_eff_diameter' not in specs['reservoir']:
            val = 0.41
            if 'injection_well' in specs:
                if 'diameter' in specs['injection_well']:
                    val = specs['injection_well']['diameter']
            if 'production_well' in specs:
                if 'diameter' in specs['production_well']:
                    val = 0.5 * (val + specs['production_well']['diameter'])
            specs['reservoir']['well_eff_diameter'] = val
        return specs['common'] | specs['reservoir']

    def _initialize_mdot_mult(self) -> None:
        """
        Initializes the multiplier to convert injection flow rate to mass flow rate.

        Process:
            - Sets multiplier to 0.25 for 'INVERTED_5SPOT' well pattern.
            - Defaults to 1.0 for other patterns.
        """
        self.m_dot_mult = 0.25 if self.well_pattern == 'INVERTED_5SPOT' else 1.0

