from tango.core import FluidState
from tango.core.constants import MAX_PRD_PUMP_DP
from tango.units.native.well import *
from tango.core.errors import CoolPropError


class ProductionWellPumpUnitNative(ProductionWellUnitNative):
    """
    Represents a production well pump unit based on Adams et al. (2015).

    This class extends the ProductionWellUnitNative class and adds specific methods and attributes
    for simulating the behavior of a production well pump. It handles pressure, enthalpy, and mass
    flow rate calculations related to the pump, including dynamic updates to the fluid state as
    it passes through the pump.

    Attributes:
        _dP_pump (float): The pressure increase due to the pump (in Pascals).
        _w_pump (float): The work done by the pump (in Watts).
        scaling_factor (float): Factor used to scale mass flow rate based on the well pattern.
    """

    def __init__(self, id: str, specs: dict):
        """
        Initializes a new instance of the ProductionWellPumpUnitNative class.

        Args:
            id (str): A unique identifier for the production well pump unit.
            specs (dict): Specifications of the well pump, which will be parsed and processed.

        Raises:
            RuntimeError: If the production well is not specified in the configuration.
            ValueError: If the pump well length is greater than the production well length.
        """
        ProductionWellUnitNative.__init__(self, id, specs)
        self._initialize_attributes_p()
        self.init_stream_interface()
        self.scaling_factor = 1.0 / 4.0 if self._specs.well_pattern == 'INVERTED_5SPOT' else 1.0

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self) -> None:
        """
        Initializes the stream interface for the production well pump.

        This method sets up the fluid state for both the inlet and outlet of the production well pump,
        using the well's surface pressure and temperature.
        """
        self.mass_rate = self._well_mass_flow_rate
        self.inlet_fluid = FluidState.withPT(self._specs.fluid_name,
                                             self._specs.surface_pressure,
                                             self._specs.surface_temperature)
        self.outlet_fluid = FluidState.copy(self.inlet_fluid)

    def stream_interface(self) -> None:
        """
        Processes the stream through the well pump and updates the fluid state.

        This method processes the fluid stream through the pump, calculating the outlet enthalpy,
        pressure, and mass rate, and updating the outlet fluid state accordingly.
        """
        try:
            outlet_enthalpy, outlet_pressure, mass_rate = self.process_stream_pump()
            self.outlet_fluid.updateHP(outlet_enthalpy, outlet_pressure)
        except CoolPropError as cpe:
            raise type(cpe)(
                f"Production well pump `stream_interface` failed\n\t{cpe}"
            ) from cpe
        except Exception as err:
            raise type(err)(
                "Production well pump `stream_interface` failed"
            ) from err

    def process_stream_pump(self) -> tuple[float, float, float]:
        """
        Processes the fluid stream through the well pump.

        This method calculates the inlet pressure, updates the inlet fluid state with the pump's
        pressure increase, and processes the stream. It also updates the work done by the pump.

        Returns:
            tuple: (float, float, float) representing the outlet enthalpy, outlet pressure, and mass rate.
        """
        try:
            self._set_inlet_pressure()
            self.update_inlet_fluid_state_with_pump()
            h_out, P_out, m_rate = self.process_stream()
            self._update_w_pump()
        except CoolPropError as cpe:
            raise type(cpe)(
                f"Production well pump `process_stream_pump` failed\n\t{cpe}"
            )
        except Exception as err:
            raise type(err)(
                "Production well pump `process_stream_pump` failed"
            ) from err

        return h_out, P_out, m_rate

    # -------------------------------------- Data Storing Functions -------------------------------------- #
    # These PUBLIC functions are specific to native production pump units and are called by the native
    # orchestrator for iterative computations. They should not be set for external pump units.

    def set_dP_pump(self, val: float) -> None:
        """
        Sets the pressure increase due to the pump, ensuring it is within valid limits.

        Args:
            val (float): The pressure increase to set (in Pascals).
        """
        self._dP_pump = min(max(val, 0.0), MAX_PRD_PUMP_DP)

    def get_dP_pump(self) -> float:
        """
        Returns the current pressure increase due to the pump.

        Returns:
            float: The current pressure increase (in Pascals).
        """
        return self._dP_pump

    def update_inlet_fluid_state_with_pump(self) -> None:
        """
        Updates the inlet fluid state after the pump's pressure increase.

        This method adjusts the inlet pressure by adding the pump's pressure increase,
        while keeping the temperature constant.
        """
        P = self._inlet_pressure_tmp + self._dP_pump
        T = self.inlet_fluid.T
        self.inlet_fluid.updatePT(P, T)

    def get_w_pump(self) -> float:
        """
        Returns the work done by the pump.

        Returns:
            float: The work done by the pump (in Watts).
        """
        return self._w_pump

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _initialize_attributes_p(self) -> None:
        """
        Initializes the attributes specific to the pump unit.

        This method sets the initial values for the pump pressure increase and the work done by the pump.
        """
        self._dP_pump = 0.0  # Initial pressure increase (Pa)
        self._w_pump = 0.0   # Initial work done by the pump (W)

    def _process_specs(self, specs: dict) -> dict:
        """
        Processes and validates the specifications for the production well pump.

        This method ensures that the production well is included in the configuration
        and that the pump's well length is not greater than the production well length.

        Args:
            specs (dict): The well pump specifications.

        Returns:
            dict: The processed specifications for the production well pump.

        Raises:
            RuntimeError: If the production well is not specified.
            ValueError: If the pump well length exceeds the production well length.
        """
        if 'production_well' not in specs:
            raise RuntimeError(f"Required unit when using unit: 'production_well' is not found.")
        if specs['production_well_pump']['well_length'] > specs['production_well']['well_length']:
            raise ValueError(f"Unrealistic value found: 'well_length' of 'production_well_pump' is greater than production well length.")
        return specs['common'] | specs['production_well_pump']

    def _update_w_pump(self) -> None:
        """
        Updates the work done by the pump based on the pressure difference and fluid properties.

        This method calculates the work required by the pump to raise the fluid's pressure
        and updates the pump's work attribute accordingly.
        """
        dP_pump = self.get_dP_pump()
        if dP_pump <= 0.0:
            return
        inlet_fluid_state_0 = FluidState.withPT(self._specs.fluid_name,
                                                P=self.fluid_state_init.P - dP_pump,
                                                T=self.fluid_state_init.T)  # State without pumping
        w_pump = self._well_mass_flow_rate * (inlet_fluid_state_0.H - self.fluid_state_init.H) / self._specs.eta_pump
        self._set_w_pump(w_pump)

    def _set_inlet_pressure(self) -> None:
        """
        Sets the temporary inlet pressure for use in pump calculations.

        This method stores the current inlet pressure to be used when updating the fluid state
        with the pump's pressure increase.
        """
        self._inlet_pressure_tmp = self.inlet_fluid.P

    def _set_w_pump(self, val: float) -> None:
        """
        Sets the work done by the pump.

        Args:
            val (float): The work done by the pump (in Watts).
        """
        self._w_pump = val
