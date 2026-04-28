import numpy as np
from math import erfc
from math import e as exp
import csv
import os
import logging


from tango.core.abstracts.unit import Unit
from tango.core.fluidstate import FluidState
from tango.core.errors import CoolPropError
from tango.units.dataclasses import ReservoirSpecsNative


class ReservoirFileReaderUnit(Unit):
    """
    Represents a reservoir file reader unit that processes CSV data for inlet and outlet fluid states.

    This class reads reservoir specifications, initializes fluid states, and manages inlet and outlet
    fluid data by reading from specified CSV files. It provides methods for stream processing, updating
    fluid properties, and ensuring the integrity of input specifications.

    Attributes:
        specs (ReservoirSpecsNative): Specifications for the reservoir, processed from the input dictionary.
        inlet_fluid (FluidState): Fluid state at the reservoir inlet.
        outlet_fluid (FluidState): Fluid state at the reservoir outlet.
        current_row (int): Current row index being processed in the CSV data.
        inlet_data (list): Data read from the inlet state CSV file.
        outlet_data (list): Data read from the outlet state CSV file.
    """

    def __init__(self, unit_id: str, specs: dict) -> None:
        """
        Initializes a new instance of the ReservoirFileReaderUnit class.

        Args:
            id (str): Unique identifier for the reservoir unit.
            specs (dict): Specifications of the reservoir unit.

        Raises:
            FileNotFoundError: If the specified CSV file does not exist.
        """
        super().__init__(unit_id, specs)
        self.specs = ReservoirSpecsNative.from_dict(self._process_specs(specs))
        self.init_stream_interface()
        self.outlet_data = self._read_csv_file(self.specs.outlet_state)
        self.inlet_data = self._read_csv_file(self.specs.inlet_state)
        self.current_row = 0

    def init_stream_interface(self, P: float | None = None, T: float | None = None) -> None:
        """
        Initializes the fluid interface for the reservoir.

        Args:
            P (float, optional): Initial pressure in Pascals. Defaults to a pre-defined pressure value.
            T (float, optional): Initial temperature in Kelvin. Defaults to a pre-defined temperature value.
        """
        self.inlet_fluid = FluidState.withPT(self.specs.fluid_name, 30_000_000, 323.25)
        self.outlet_fluid = FluidState.withPT(self.specs.fluid_name, 30_000_000, 323.25)

    def stream_interface(self) -> None:
        """
        Processes the fluid stream and updates the outlet fluid properties based on the current row of data.

        This method retrieves the pressure, temperature, and mass rate from the current row and updates
        the outlet fluid properties.
        """
        try:
            outlet_pressure, outlet_temperature, mass_rate = self.process_stream()
            self.outlet_fluid.updatePT(outlet_pressure, outlet_temperature)
        except CoolPropError as cpe:
            raise type(cpe)(
                f"ReservoirFileReaderUnit `stream_interface` failed\n\t{cpe}"
            ) from cpe
        except Exception as err:
            raise type(err)(
                "ReservoirFileReaderUnit `stream_interface` failed"
            ) from err

    def process_stream(self) -> tuple[float, float, float]:
        """
        Processes the current row of inlet and outlet data to extract pressure, temperature, and mass rate.

        Returns:
            tuple: A tuple containing outlet pressure (float), outlet temperature (float), and mass rate (float).

        Raises:
            Warning: Logs a warning if the end of the CSV file is reached.
        """
        if self.current_row < len(self.inlet_data):
            row = self.inlet_data[self.current_row]
            self.inlet_pressure = float(row[1])
            self.inlet_flow = float(row[3])
        if self.current_row < len(self.outlet_data):
            row = self.outlet_data[self.current_row]
            pressure = float(row[1])
            temperature = float(row[2])
            self.mass_rate = float(row[3])

            return pressure, temperature, self.mass_rate
        else:
            logging.warning("End of the CSV file reached.")
            return self.outlet_fluid.P, self.outlet_fluid.T, self.mass_rate

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _read_csv_file(self, file_path) -> list:
        """
        Reads data from a specified CSV file.

        Args:
            file_path (str): Path to the CSV file.

        Returns:
            list: A list of rows from the CSV file, excluding the header row.

        Raises:
            FileNotFoundError: If the specified CSV file does not exist.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"The CSV file does not exist at {file_path}")

        with open(file_path, 'r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row
            return list(reader)

    def _process_specs(self, specs: dict) -> dict:
        """
        Processes reservoir specifications and ensures the presence of 'well_eff_diameter'.

        Args:
            specs (dict): Specifications dictionary for the reservoir.

        Returns:
            dict: Processed specifications with necessary parameters merged and validated.
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
