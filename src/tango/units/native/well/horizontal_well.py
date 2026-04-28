import copy
import numpy as np
import logging

from tango.units.native.well.base import WellUnitNative
from tango.core.constants import GRAVITY_ACCELERATION
from tango.core.fluidstate import FluidState


class HorizontalWellUnitNative(WellUnitNative):
    """
    Represents a horizontal well unit for simulating fluid flow, extending the WellUnitNative class.

    This class provides methods to simulate fluid flow in horizontal wellbores, taking into account
    the unique specifications and geometry of horizontal wells. It handles dynamic changes in wellbore
    conditions and offers an interface for processing streams through the well.

    Attributes:
        _well_mass_flow_rate (float): The mass flow rate through the well (in kg/s).
        _f_dir (float): Flow direction coefficient.
        length_list (list): List of well lengths along the horizontal well.
        diameter_list (list): List of well diameters along the horizontal well.
    """

    def __init__(self, id: str, specs: dict):
        """
        Initializes a new instance of the HorizontalWellUnitNative class.

        Args:
            id (str): A unique identifier for the horizontal well unit.
            specs (dict): Specifications of the horizontal well, parsed into the appropriate format.

        Raises:
            RuntimeError: If the horizontal well specifications cannot be read for the given id.
        """
        WellUnitNative.__init__(self, id, specs=self._process_specs(id, specs))
        self._specs_post_processor_hw()
        self.init_stream_interface()

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self) -> None:
        """
        Initializes the stream interface for the horizontal well.

        This method sets up the initial fluid properties at the wellhead, including the pressure and
        temperature, based on the wellhead depth, thermal gradient, and surface temperature.
        """
        h = self._specs.wellhead_depth
        dTdz = self._specs.thermal_gradient
        T0 = self._specs.surface_temperature
        initial_pressure = self._specs.brine_density * GRAVITY_ACCELERATION * h
        initial_temperature = T0 + h * dTdz
        self.mass_rate = self._well_mass_flow_rate
        self.inlet_fluid = FluidState.withPT(self._specs.fluid_name, initial_pressure, initial_temperature)
        self.outlet_fluid = FluidState.withPT(self._specs.fluid_name, initial_pressure, initial_temperature)

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _specs_post_processor_hw(self) -> None:
        """
        Processes the horizontal well specifications and initializes attributes.

        This method sets the mass flow rate, flow direction, segment length, and well diameter and length sequences.
        It adjusts for the horizontal well's specific geometry, such as the discretization of the well along its length.
        """
        self._well_mass_flow_rate = self._specs.mass_flow_rate
        self._f_dir = -1.0  # Flow direction for horizontal well
        self._dL = self._well_length / self._num_cells
        self._dz = self._dZ / self._num_cells
        self.length_list = self._specs.well_length_seq
        self.diameter_list = self._specs.well_diameter_seq

    def _process_specs(self, id: str, specs: dict) -> dict:
        """
        Processes the specifications for the horizontal well and validates them.

        Args:
            id (str): The unique identifier for the horizontal well.
            specs (dict): Specifications of the well.

        Returns:
            dict: The processed specifications, combining common and horizontal well-specific data.

        Raises:
            RuntimeError: If horizontal well specifications cannot be found for the given id, or if the wellhead depth is missing.
        """
        if isinstance(specs['horizontal_well'], list):
            specs_tmp = copy.deepcopy(specs)
            specs = {'common': specs_tmp['common'], 'horizontal_well': None}
            for d in specs_tmp['horizontal_well']:
                if id in d.keys():
                    specs['horizontal_well'] = d[id]
                    break
            if specs['horizontal_well'] is None:
                raise RuntimeError(f"Failed to read horizontal_well specs for id: {id}")
        if 'wellhead_depth' not in specs['horizontal_well']:
            raise RuntimeError(f"Required parameter 'wellhead_depth' is not found in specs")
        if np.abs(specs['common']['well_spacing'] - specs['horizontal_well']['well_length']) < 1e-5:
            logging.warning("Inconsistent well_spacing and horizontal_well length found.")
        specs_dict: dict = specs['common'] | specs['horizontal_well']
        return specs_dict

    def _set_well_length(self) -> float:
        """
        Sets the well length based on the horizontal well specifications.

        Returns:
            float: The well length (in meters).

        Raises:
            RuntimeError: If the well length is not defined in the specifications.
        """
        if self._specs.well_length is None:
            raise RuntimeError(f"Required parameter 'well_length' is not found in specs.")
        else:
            well_length: float = self._specs.well_length
            return well_length

    def _initialize_farfield_temperature(self) -> None:
        """
        Initializes the far-field temperature profile along the horizontal well.

        This method calculates the temperature of the surrounding rock based on the well geometry
        and the thermal gradient. It checks for the vertical deviation of the well to ensure correct
        depth-related calculations.

        Raises:
            ValueError: If the vertical deviation is not found or is non-positive.
        """
        if self._specs.vertical_deviation is None:
            raise ValueError(f"Required parameter: 'vertical_deviation' is not found.")
        if self._specs.vertical_deviation <= 0:
            raise ValueError(f"Invalid parameter value found in 'vertical_deviation'. Please use a positive value.")
        self._dZ = self._well_length * np.tan(np.deg2rad(90.0 - self._specs.vertical_deviation))
        Z0 = self._specs.wellhead_depth
        zspace = np.linspace(Z0, Z0 + self._dZ, self._num_cells + 1)
        zspace = (zspace[1:] + zspace[:-1]) * 0.5  # Depth at cell centers

        dTdz = self._specs.thermal_gradient
        T0 = self._specs.surface_temperature
        self._T_r = T0 + zspace * dTdz  # Rock temperature (K)
