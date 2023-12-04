from tango.core import FluidState
from tango.core.constants import MAX_PRD_PUMP_DP
from tango.units.native.well import *


class ProductionWellPumpUnitNative(ProductionWellUnitNative):
    """The production well unit based on Adams et al. (2015)."""
    def __init__(self, id: str, specs: dict):
        ProductionWellUnitNative.__init__(self, id, specs)
        self._init_storing_attributes_p()
        self.init_stream_interface()

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self):
        self.mass_rate = self._well_mass_flow_rate
        self.inlet_fluid = FluidState.withPT(self._specs.fluid_name,
                                                   self._specs.surface_pressure,
                                                   self._specs.surface_temperature)
        self.outlet_fluid = FluidState.copy(self.inlet_fluid)


    def stream_interface(self) -> None:
        outlet_enthalpy, outlet_pressure, mass_rate = self.process_stream_pump()
        self.mass_rate = mass_rate
        self.outlet_fluid.updateHP(outlet_enthalpy, outlet_pressure)


    def process_stream_pump(self) -> None:
        self._set_inlet_pressure()
        self.update_inlet_fluid_state_with_pump()
        self.process_stream()
        h_out, P_out, m_rate = self.process_stream()
        self._update_w_pump()

        return h_out, P_out, m_rate

    # -------------------------------------- data storing Functions -------------------------------------- #
    # These PUBLIC functions are specific to native production pump units. They will be called by the native
    # orchestrator for iterative computations. Please don't set them for external production pump units, as
    # they will not be called by the native orchestrator, and the solution is not iterative.

    def set_dP_pump(self, val) -> None:
        self._dP_pump = min(max(val, 0.), MAX_PRD_PUMP_DP)


    def get_dP_pump(self) -> None:
        return self._dP_pump


    def update_inlet_fluid_state_with_pump(self) -> None:
        P = self._inlet_pressure_tmp + self._dP_pump
        T = self.inlet_fluid.T
        self.inlet_fluid.updatePT(P, T)


    def get_w_pump(self) -> None:
        return self._w_pump

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _init_storing_attributes_p(self) -> float:
        self._dP_pump: float = 0.
        self._w_pump: float = 0.


    def _process_specs(self, specs) -> dict:
        if 'production_well' not in specs:
            raise RuntimeError(f"Required unit when using unit: 'production_well' is not found.")
        if specs['production_well_pump']['well_length'] > specs['production_well']['well_length']:
            raise ValueError(f"Unrealistic value found: 'well_length' of 'production_well_pump' is greater than production well length")
        return specs['common'] | specs['production_well_pump']


    def _update_w_pump(self):
        dP_pump = self.get_dP_pump()
        if dP_pump <= 0.:
            return
        inlet_fluid_state_0 = FluidState.withPT(self._specs.fluid_name,
                                                P=self.fluid_state_init.P - dP_pump,
                                                T=self.fluid_state_init.T) # state w/o pumping
        w_pump = self._well_mass_flow_rate * (inlet_fluid_state_0.H - self.fluid_state_init.H) / self._specs.eta_pump
        self._set_w_pump(w_pump)


    def _set_inlet_pressure(self) -> None:
        self._inlet_pressure_tmp = self.inlet_fluid.P


    def _set_w_pump(self, val) -> None:
        self._w_pump = val
