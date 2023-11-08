from tango.core.constants import GRAVITY_ACCELERATION
from tango.core.abstracts.unit import *
from tango.units.native.common import ReservoirSpecsPorousflow
from tango.interfaces.tango_moose_interface import *


class ReservoirUnitPorousflow(Unit):
    """MOOSE Reservoir Unit"""
    def __init__(self, id: str, specs: dict) -> None:
        super().__init__(id, specs)
        self.specs = ReservoirSpecsPorousflow.from_dict(self._process_specs(specs))
        self.fluid_name = self.specs.fluid_name
        self.well_pattern = self.specs.well_pattern.upper()
        self.initial_temperature = self._compute_initial_temperature()
        self.initial_pressure = self._compute_initial_pressure()
        self._initialize_mdot_mult()
        self.init_state()

        self.moose_executable_path = self.specs.moose_executable_path
        self.moose_input_path = self.specs.moose_input_path
        self.post_processor_path = self.specs.post_processor_path
        self.pressure_bc_file = self.specs.pressure_bc_file
        self.flowrate_bc_file = self.specs.flowrate_bc_file
        self.temperature_bc_file = self.specs.temperature_bc_file

        self.interface = TangoMooseInterface(
                self.moose_executable_path,
                self.moose_input_path,
                self.pressure_bc_file,
                self.flowrate_bc_file,
                self.temperature_bc_file)

    def _process_specs(self, specs) -> dict:
        return specs['common'] | specs['reservoir']


    def _compute_area(self) -> float:
        return 0.5 * (self.specs.well_spacing ** 2) if self.specs.area is None else self.specs.area


    def _compute_initial_temperature(self) -> float:
        if self.specs.initial_temperature is not None:
            return self.specs.initial_temperature
        h, dTdz, T0 = self.specs.reservoir_depth, self.specs.thermal_gradient, self.specs.surface_temperature
        return T0 + h * dTdz # deg C


    def _compute_initial_pressure(self) -> float:
        if self.specs.initial_pressure is not None:
            return self.specs.initial_pressure
        return self.specs.brine_density * GRAVITY_ACCELERATION * self.specs.reservoir_depth


    def _initialize_mdot_mult(self) -> None:
        """multiplier to convert injection flow rate to m_dot (well-pair level flow rate)"""
        self.m_dot_mult = 0.25 if self.well_pattern == 'INVERTED_5SPOT' else 1.0


    def init_state(self, P: float=None, T:float=None) -> None:
        P = self.initial_pressure if P==None else P
        T = self.initial_temperature if T == None else T
        self.state = UnitState()
        self.state.inlet_fluid = FluidState.withPT(self.fluid_name, P, T)
        self.state.outlet_fluid = FluidState.withPT(self.fluid_name, P, T)


    def update(self) -> None:
        """Update reservoir state given inlet state (outlet fluid state of injection well)"""
        state = self.state
        self.m_dot = self.m_dot_mult * state.mass_rate
        self.interface.pressure_from_TANGO = self.state.inlet_fluid.P
        self.interface.temperature_from_TANGO = self.state.inlet_fluid.T
        self.interface.flowrate_from_TANGO = self.state.mass_rate/self.state.inlet_fluid.rho
        self.interface.run(self.post_processor_path)
        self.state.outlet_fluid.updatePT(self.interface.pressure_from_MOOSE, self.interface.temperature_from_MOOSE)
        state.mass_rate = self.m_dot
        self.update_outlet_streams()


    def execute(self) -> None:
        self.update_inlet_state()
        self.update()
        print("res_in ", self.state.inlet_fluid.P, self.state.inlet_fluid.T)
        print("res_out ", self.state.outlet_fluid.P, self.state.outlet_fluid.T)
