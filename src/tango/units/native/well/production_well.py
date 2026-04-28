from tango.units.native.well.base import WellUnitNative
from tango.core.fluidstate import FluidState


class ProductionWellUnitNative(WellUnitNative):
    """
    Represents a production well unit based on Adams et al. (2015).

    This class simulates the behavior of a production well, where fluids are extracted from the wellbore.
    It extends the WellUnitNative class and includes methods for managing the production well’s
    specifications, stream interfaces, and well length adjustments for economic calculations.

    Attributes:
        _f_dir (float): Flow direction coefficient for upwards flow.
        _well_mass_flow_rate (float): The mass flow rate through the production well (in kg/s).
        scaling_factor (float): Factor used to scale mass flow rate.
    """

    def __init__(self, unit_id: str, specs: dict):
        """
        Initializes a new instance of the ProductionWellUnitNative class.

        Args:
            id (str): A unique identifier for the production well.
            specs (dict): Specifications of the production well, which will be parsed and processed.

        Raises:
            RuntimeError: If required specifications for well length or reservoir depth are missing.
            ValueError: If the production and injection well lengths differ.
        """
        WellUnitNative.__init__(self, unit_id, specs=self._process_specs(specs))
        self._specs_post_processor_pw()
        self.init_stream_interface()
        self.scaling_factor = self._m_dot_mult

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self, P: float | None = None, T: float | None = None) -> None:
        """
        Initializes the stream interface for the production well.

        This method sets up the fluid state for both the inlet and outlet of the production well,
        using the specified or default pressure and temperature.

        Args:
            P (float, optional): The pressure at the well inlet (in Pascals). Defaults to surface pressure.
            T (float, optional): The temperature at the well inlet (in Kelvin). Defaults to surface temperature.
        """
        P = self._specs.surface_pressure if P is None else P
        T = self._specs.surface_temperature if T is None else T
        self.mass_rate = self._well_mass_flow_rate
        self.inlet_fluid = FluidState.withPT(self._specs.fluid_name, P, T)
        self.outlet_fluid = FluidState.copy(self.inlet_fluid)

    def update_well_length(self, pump_well_length: float) -> None:
        """
        Updates the well length for economic calculations.

        This method adds the length of the pump well to the total well length.

        Args:
            pump_well_length (float): The length of the pump well (in meters).
        """
        self._well_length += pump_well_length

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _specs_post_processor_pw(self) -> None:
        """
        Processes the specifications for the production well and initializes attributes.

        This method sets the flow direction, computes the mass flow rate, and initializes the
        well length and diameter sequences based on the specifications.
        """
        self._f_dir = 1.0  # Upwards flow direction for production wells
        self._well_mass_flow_rate = self._compute_well_mass_flow_rate()
        self.length_list = self._specs.well_length_seq
        self.diameter_list = self._specs.well_diameter_seq

    def _process_specs(self, specs: dict) -> dict:
        """
        Processes and validates the specifications for the production well.

        This method checks for required parameters such as well length and reservoir depth.
        It ensures consistency between the production and injection well lengths.

        Args:
            specs (dict): The well specifications.

        Returns:
            dict: The processed specifications for the production well.

        Raises:
            RuntimeError: If required well length or reservoir depth specifications are missing.
            ValueError: If the production and injection well lengths differ.
        """
        if 'production_well_pump' in specs:
            if 'well_length' not in specs['production_well']:
                raise RuntimeError(f"Required parameter: 'well_length' is not found in specs of 'production_well'.")
            if 'well_length' not in specs['production_well_pump']:
                raise RuntimeError(f"Required parameter: 'well_length' is not found in specs of 'production_well_pump'.")
            if 'reservoir' in specs:
                if 'reservoir_depth' not in specs['reservoir']:
                    raise RuntimeError(f"Required parameter: 'reservoir_depth' is not found in specs of 'reservoir'.")
                if specs['production_well']['well_length'] + specs['production_well_pump']['well_length'] != specs['injection_well']['well_length']:
                    raise ValueError(f"Different production and injection lengths are not supported.")
            specs['production_well']['wellhead_depth'] = specs['production_well_pump']['well_length']
        return specs['common'] | specs['production_well']

    def _compute_well_mass_flow_rate(self) -> float:
        """
        Computes the mass flow rate for the production well.

        The mass flow rate is calculated based on the well pattern. For inverted 5-spot patterns,
        the mass flow rate is scaled accordingly.

        Returns:
            float: The mass flow rate (in kg/s).
        """

        self._m_dot_mult = 1.0 / 4.0 if self._specs.well_pattern == 'INVERTED_5SPOT' else 1.0

        if (self._specs.bc_iteration != None):
            return self.mass_rate / 4.0 if self._specs.well_pattern == 'INVERTED_5SPOT' else self.mass_rate
        else:
            return self._specs.mass_flow_rate / 4.0 if self._specs.well_pattern == 'INVERTED_5SPOT' else self._specs.mass_flow_rate
