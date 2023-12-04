from tango.core.constants import GRAVITY_ACCELERATION
from tango.units.native.common import ReservoirSpecsPorousflow
from tango.units.external.MOOSE.base import *


class ReservoirUnitPorousflow(MOOSERunner):
    """MOOSE Reservoir Unit"""

    def __init__(self, id: str, specs: dict) -> None:
        super().__init__(id, specs)
        self.specs = ReservoirSpecsPorousflow.from_dict(self._process_specs(specs))
        self._specs_post_processor()
        self.init_stream_interface()

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self, P: float = None, T: float = None) -> None:
        P = self.initial_pressure if P == None else P
        T = self.initial_temperature if T == None else T
        self.inlet_fluid = FluidState.withPT(self.fluid_name, P, T)
        self.outlet_fluid = FluidState.withPT(self.fluid_name, P, T)

    def process_stream(self) -> tuple:
        """Update reservoir state given inlet state (outlet fluid state of injection well)"""
        self.m_dot = self.m_dot_mult * self.mass_rate
        self._interface.pressure_from_TANGO = self.inlet_fluid.P
        self._interface.temperature_from_TANGO = self.inlet_fluid.T
        self._interface.flowrate_from_TANGO = self.mass_rate / self.inlet_fluid.rho
        self._interface.run(self._post_processor_path)
        self.mass_rate = self.m_dot

        return self._interface.pressure_from_MOOSE, self._interface.temperature_from_MOOSE, self.mass_rate

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _specs_post_processor(self) -> float:
        self.fluid_name = self.specs.fluid_name
        self.well_pattern = self.specs.well_pattern.upper()
        self.initial_temperature = self._compute_initial_temperature()
        self.initial_pressure = self._compute_initial_pressure()
        self._initialize_mdot_mult()

        # TODO: generate MOOSE input should be added here!
        self._post_processor_path = self.specs.post_processor_path

        self._interface = TangoMooseInterface(
            self.specs.moose_executable_path,
            self.specs.moose_input_path,
            self.specs.pressure_bc_file,
            self.specs.flowrate_bc_file,
            self.specs.temperature_bc_file)

    def _process_specs(self, specs) -> dict:
        return specs['common'] | specs['reservoir']

    def _compute_area(self) -> float:
        return 0.5 * (self.specs.well_spacing ** 2) if self.specs.area is None else self.specs.area

    def _compute_initial_temperature(self) -> float:
        if self.specs.initial_temperature is not None:
            return self.specs.initial_temperature
        h, dTdz, T0 = self.specs.reservoir_depth, self.specs.thermal_gradient, self.specs.surface_temperature
        return T0 + h * dTdz  # deg C

    def _compute_initial_pressure(self) -> float:
        if self.specs.initial_pressure is not None:
            return self.specs.initial_pressure
        return self.specs.brine_density * GRAVITY_ACCELERATION * self.specs.reservoir_depth

    def _initialize_mdot_mult(self) -> None:
        """multiplier to convert injection flow rate to m_dot (well-pair level flow rate)"""
        self.m_dot_mult = 0.25 if self.well_pattern == 'INVERTED_5SPOT' else 1.0
