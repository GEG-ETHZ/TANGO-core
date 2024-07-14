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
    """The reservoir (1-D well-pair) unit based on Adams et al. (2015)."""

    def __init__(self, id: str, specs: dict) -> None:
        super().__init__(id, specs)
        self.specs = ReservoirSpecsNative.from_dict(self._process_specs(specs))
        self._specs_post_processor()
        self.init_stream_interface()

        self.csv_data = self._read_csv_file()
        self.current_row = 0

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self, P: float = None, T: float = None) -> None:
        self.inlet_fluid = FluidState.withPT(self.fluid_name, 30000000, 323.25)
        self.outlet_fluid = FluidState.withPT(self.fluid_name, 30000000, 323.25)

    def stream_interface(self) -> None:
        outlet_pressure, outlet_temperature, mass_rate = self.process_stream()
        self.outlet_fluid.updatePT(outlet_pressure, outlet_temperature)

        # Print inlet and outlet conditions
        print('\n')
        print(f'File reader inlet -> P = {self.inlet_fluid.P}, T = {self.inlet_fluid.T}')
        print(f'File reader outlet -> P = {self.outlet_fluid.P}, T = {self.outlet_fluid.T}')

    def process_stream(self) -> tuple:
        """Update reservoir state given inlet state (outlet fluid state of injection well)"""
        if self.current_row < len(self.csv_data):
            row = self.csv_data[self.current_row]
            self.current_row += 1

            pressure = float(row[1])
            temperature = float(row[2])

            self.m_dot = self.m_dot_mult * self.mass_rate

            return pressure, temperature, self.m_dot
        else:
            # If we've reached the end of the file
            # For now, we'll just return the last known values
            logging.warning(f"we've reached the end of the file.")
            return self.outlet_fluid.P, self.outlet_fluid.T, self.m_dot

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _read_csv_file(self):
        file_path = self.specs.outlet_state
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"The CSV file does not exist at {file_path}")

        with open(file_path, 'r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row
            return list(reader)

    def _specs_post_processor(self) -> float:
        self.fluid_name = self.specs.fluid_name
        self.well_pattern = self.specs.well_pattern.upper()
        self._initialize_mdot_mult()

    def _process_specs(self, specs) -> dict:
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
        """multiplier to convert injection flow rate to m_dot (well-pair level flow rate)"""
        self.m_dot_mult = 0.25 if self.well_pattern == 'INVERTED_5SPOT' else 1.0
