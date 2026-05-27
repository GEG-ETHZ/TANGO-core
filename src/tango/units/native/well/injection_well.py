from tango.core.constants import ATMOSPHERIC_PRESSURE, MIN_INJ_TEMPERATURE
from tango.core.fluidstate import FluidState
from tango.units.native.well.base import WellUnitNative


class InjectionWellUnitNative(WellUnitNative):
    """Represents an injection well unit based on Adams et al. (2015).

    This class simulates the behavior of an injection well, where fluids are injected into the wellbore.
    It extends the WellUnitNative class, with additional methods specific to injection well operations.
    The class handles initialization of well specifications, stream interfaces, and temperature tracking.

    Attributes:
        _well_mass_flow_rate (float): The mass flow rate through the well (in kg/s).
        _f_dir (float): Flow direction coefficient.
        _injection_temperature_tmp (float): Temporary storage for the injection temperature (in Kelvin).
        scaling_factor (float): Factor used to scale mass flow rate.

    """

    def __init__(self, unit_id: str, specs: dict):
        """Initializes a new instance of the InjectionWellUnitNative class.

        Args:
            id (str): A unique identifier for the injection well.
            specs (dict): Specifications of the injection well, which will be parsed and processed.

        Raises:
            RuntimeError: If required specifications are missing or invalid.

        """
        WellUnitNative.__init__(self, unit_id, specs=self._process_specs(specs))
        self._specs_post_processor_iw()
        self.init_stream_interface()
        self._initialize_attributes_hw()

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self, P: float | None = None, T: float | None = None) -> None:
        """Initializes the stream interface for the injection well.

        This method sets up the fluid state for both the inlet and outlet of the injection well,
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

    def get_del_temperature(self, T: float) -> float:
        """Returns the temperature difference between the injection temperature and a given temperature.

        Args:
            T (float): The temperature to compare against.

        Returns:
            float: The temperature difference (in Kelvin).

        """
        return self._injection_temperature_tmp - T

    def update_inlet_fluid_state_PT(self, P: float | None = None, T: float | None = None) -> None:
        """Updates the fluid state at the inlet based on pressure and temperature.

        If only pressure or temperature is provided, the other value is taken from the current inlet fluid state.
        The method ensures that the minimum temperature and atmospheric pressure are respected.

        Args:
            P (float, optional): The pressure (in Pascals). Defaults to current inlet pressure.
            T (float, optional): The temperature (in Kelvin). Defaults to current inlet temperature.

        """
        if P is not None and T is None:
            P = max(P, ATMOSPHERIC_PRESSURE)
            T = self.inlet_fluid.T
        elif P is None and T is not None:
            P = self.inlet_fluid.P
            T = max(T, MIN_INJ_TEMPERATURE)
        self.inlet_fluid.updatePT(P, T)

    def update_inlet_temperature_tmp(self) -> None:
        """Updates the temporary storage for the inlet injection temperature.

        This method stores the current inlet fluid temperature for use in temperature tracking.
        """
        self._injection_temperature_tmp = self.inlet_fluid.T

    def get_inlet_temperature_tmp(self) -> float:
        """Returns the temporary injection temperature stored during the simulation.

        Returns:
            float: The injection temperature from the previous iteration (in Kelvin).

        """
        return self._injection_temperature_tmp

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _specs_post_processor_iw(self) -> None:
        """Processes the specifications for the injection well and initializes attributes.

        This method sets the mass flow rate, flow direction, and well geometry based on the specifications.
        """
        if self._specs.bc_iteration is not None:
            self._well_mass_flow_rate = self.mass_rate
        else:
            self._well_mass_flow_rate = self._specs.mass_flow_rate

        self._f_dir = -1.0  # Downwards flow direction for injection wells
        self.length_list = self._specs.well_length_seq
        self.diameter_list = self._specs.well_diameter_seq

    def _initialize_attributes_hw(self) -> None:
        """Initializes time-related attributes for the injection well.

        This method sets up the initial injection temperature for tracking purposes.
        """
        self._injection_temperature_tmp = 0.0  # Initial injection temperature (K)

    def _process_specs(self, specs: dict) -> dict:
        """Processes and merges the common and injection well-specific specifications.

        Args:
            specs (dict): The well specifications.

        Returns:
            dict: The processed specifications for the injection well.

        """
        specs_dict: dict = specs["common"] | specs["injection_well"]
        return specs_dict

    def _set_mult(self) -> None:
        """Sets the scaling factor for the mass flow rate based on the well pattern.

        This method adjusts the mass flow rate based on the well pattern type. For example, in a '5SPOT' pattern,
        the mass flow rate is scaled by 0.25, while for other patterns, it remains unchanged.
        """
        self._m_dot_mult = 0.25 if self._specs.well_pattern in ["5SPOT"] else 1.0
