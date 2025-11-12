from tango.core.constants import GRAVITY_ACCELERATION
from tango.units.dataclasses import ReservoirSpecsPorousflow
from tango.core.fluidstate import FluidState
from tango.units.external.MOOSE.base import MOOSERunner, TangoMooseInterface
from tango.core.abstracts.unit import Resistance


class ReservoirUnitPorousflow(MOOSERunner, Resistance):
    r"""
    MOOSE Reservoir Unit for simulating porous flow in reservoirs.

    This class interfaces with a MOOSE-based application to simulate reservoir behavior
    based on specified inlet conditions, fluid properties, and reservoir characteristics.

    Attributes:
        specs (ReservoirSpecsPorousflow): Specifications for the reservoir simulation.
        fluid_name (str): Name of the fluid used in the simulation.
        well_pattern (str): Well pattern for the reservoir (e.g., 'INVERTED_5SPOT').
        initial_temperature (float): Initial reservoir temperature (°C).
        initial_pressure (float): Initial reservoir pressure (Pa).
        m_dot_mult (float): Multiplier to convert injection flow rate to well-pair level flow rate.
        _post_processor_path (str): Path to the post-processor for MOOSE.
        _interface (TangoMooseInterface): Interface for communicating with the MOOSE application.

    Methods:
        init_stream_interface: Initializes stream interface with specified or default conditions.
        process_stream: Updates reservoir state based on inlet conditions.
        _compute_area: Computes the reservoir area if not specified.
        _compute_initial_temperature: Calculates the initial temperature of the reservoir.
        _compute_initial_pressure: Calculates the initial pressure of the reservoir.
        _initialize_mdot_mult: Initializes the mass flow rate multiplier based on the well pattern.
    """
    def __init__(self, unit_id: str, specs: dict) -> None:
        """
        Initializes a new instance of the ReservoirUnitPorousflow class.

        Args:
            id (str): Identifier for the reservoir unit.
            specs (dict): Specifications for the reservoir simulation.
        """
        super().__init__(unit_id, specs)
        self.specs = ReservoirSpecsPorousflow.from_dict(self._process_specs(specs))
        self._specs_post_processor()
        self.init_stream_interface()

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self, P: float = None, T: float = None) -> None:
        """
        Initializes the stream interface with specified or default pressure and temperature.

        Args:
            P (float, optional): Initial pressure for the reservoir (Pa).
            T (float, optional): Initial temperature for the reservoir (°C).
        """
        P = self.initial_pressure if P is None else P
        T = self.initial_temperature if T is None else T
        self.inlet_fluid = FluidState.withPT(self.fluid_name, P, T)
        self.outlet_fluid = FluidState.withPT(self.fluid_name, P, T)

    def process_stream(self) -> tuple:
        r"""
        Updates the reservoir state given the inlet state.

        This function simulates the reservoir's response based on the inlet fluid state
        and updates the outlet fluid state using MOOSE.

        Returns:
            tuple: Updated outlet pressure (Pa), temperature (°C), and mass rate (kg/s).
        """
        self.m_dot = self.m_dot_mult * self.mass_rate
        self._interface.pressure_from_TANGO = self.inlet_fluid.P
        self._interface.temperature_from_TANGO = self.inlet_fluid.T
        self._interface.flowrate_from_TANGO = self.mass_rate / self.inlet_fluid.rho
        self._interface.run(self._post_processor_path)
        self.mass_rate = self.m_dot

        return self._interface.pressure_from_MOOSE, self._interface.temperature_from_MOOSE, self.mass_rate

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _specs_post_processor(self) -> None:
        """
        Processes the specifications to initialize reservoir properties.
        """
        self.fluid_name = self.specs.fluid_name
        self.well_pattern = self.specs.well_pattern.upper()
        self.initial_temperature = self._compute_initial_temperature()
        self.initial_pressure = self._compute_initial_pressure()
        self._initialize_mdot_mult()
        self._post_processor_path = self.specs.post_processor_path
        self._interface = TangoMooseInterface(
            self.specs.moose_executable_path,
            self.specs.moose_input_path,
            self.specs.pressure_bc_file,
            self.specs.flowrate_bc_file,
            self.specs.temperature_bc_file)

    def _process_specs(self, specs) -> dict:
        """
        Combines common and reservoir-specific specifications.

        Args:
            specs (dict): Input specifications.

        Returns:
            dict: Merged specifications.
        """
        return specs['common'] | specs['reservoir']

    def _compute_area(self) -> float:
        """
        Computes the reservoir area.

        Returns:
            float: Computed reservoir area (m²).
        """
        return 0.5 * (self.specs.well_spacing ** 2) if self.specs.area is None else self.specs.area

    def _compute_initial_temperature(self) -> float:
        r"""
        Computes the initial reservoir temperature.

        Formula:
            .. math::
                T_{\text{initial}} = T_0 + h \cdot \frac{dT}{dz}

        Where:
            - \( T_0 \): Surface temperature (°C).
            - \( h \): Reservoir depth (m).
            - \( \frac{dT}{dz} \): Thermal gradient (°C/m).

        Returns:
            float: Initial temperature (°C).
        """
        if self.specs.initial_temperature is not None:
            return self.specs.initial_temperature
        h, dTdz, T0 = self.specs.reservoir_depth, self.specs.thermal_gradient, self.specs.surface_temperature

        return T0 + h * dTdz

    def _compute_initial_pressure(self) -> float:
        r"""
        Computes the initial reservoir pressure.

        Formula:
            .. math::
                P_{\text{initial}} = \rho_{\text{brine}} \cdot g \cdot h

        Where:
            - \( \rho_{\text{brine}} \): Brine density (kg/m³).
            - \( g \): Gravity acceleration (m/s²).
            - \( h \): Reservoir depth (m).

        Returns:
            float: Initial pressure (Pa).
        """
        if self.specs.initial_pressure is not None:
            return self.specs.initial_pressure

        return self.specs.brine_density * GRAVITY_ACCELERATION * self.specs.reservoir_depth

    def _initialize_mdot_mult(self) -> None:
        """
        Initializes the mass flow rate multiplier based on the well pattern.

        Multiplier Values:
            - 0.25 for 'INVERTED_5SPOT'.
            - 1.0 for other patterns.
        """
        self.m_dot_mult = 0.25 if self.well_pattern == 'INVERTED_5SPOT' else 1.0
