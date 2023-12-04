from tango.core.constants import *
from tango.units.native.well.base import *


class InjectionWellUnitNative(WellUnitNative):
    """The injection well unit based on Adams et al. (2015)."""
    def __init__(self, id: str, specs: dict):
        WellUnitNative.__init__(self, id, specs=self._process_specs(specs))
        self._specs_post_processor_iw()
        self.init_stream_interface()
        self._initialize_attributes_hw()

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self, P: float=None, T: float=None) -> None:
        P = self._specs.surface_pressure if P==None else P
        T = self._specs.surface_temperature if T == None else T
        self.mass_rate = self._well_mass_flow_rate
        self.inlet_fluid = FluidState.withPT(self._specs.fluid_name, P, T)
        self.outlet_fluid = FluidState.copy(self.inlet_fluid)

    # -------------------------------------- data storing Functions -------------------------------------- #
    # These PUBLIC functions are specific to native horizontal well units. They will be called by the native
    # orchestrator for iterative computations. Please don't set them for external horizontal well units, as
    # they will not be called by the native orchestrator, and the solution is not iterative.

    def get_del_temperature(self, T:float) -> float:
        return self._injection_temperature_tmp - T


    def update_inlet_fluid_state_PT(self, P: float = None, T: float = None) -> None:
        if P != None and T == None:
            P = max(P, ATMOSPHERIC_PRESSURE)
            T = self.inlet_fluid.T
        elif P == None and T != None:
            P = self.inlet_fluid.P
            T = max(T, MIN_INJ_TEMPERATURE)
        self.inlet_fluid.updatePT(P, T)


    def update_inlet_temperature_tmp(self) -> None:
        self._injection_temperature_tmp = self.inlet_fluid.T


    def get_inlet_temperature_tmp(self) -> float:
        return self._injection_temperature_tmp

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _specs_post_processor_iw(self) -> float:
        self._well_mass_flow_rate = self._specs.mass_flow_rate
        self._f_dir = -1.0 # downwards
        self._set_mult()


    def _initialize_attributes_hw(self) -> float:
        self._injection_temperature_tmp: float = 0. # injection temperature at previous iteration (K)


    def _process_specs(self, specs) -> dict:
        return specs['common'] | specs['injection_well']


    def _set_mult(self) -> None:
        """
            - m_dot_mult is to convert m_dot (well-pair level mass flow rate) at a producer
              to a pattern level mass flow rate (=injection mass flow rate)
        """
        self._m_dot_mult = 0.25 if self._specs.well_pattern in ['5SPOT'] else 1.
