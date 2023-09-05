from tango.core.abstracts.model import *
from tango.core import FluidState


class ModelStateNative(ModelState):

    def __init__(self):
        self.mass_rate: float = 0.0
        self.inlet_fluid: FluidState
        self.outlet_fluid: FluidState


class ModelNative(Model):

    def __init__(self, specs) -> None:
        super().__init__(specs)
        self.inlet_streams = list()
        self.outlet_streams = list()


    def set_inlet_stream(self, sl) -> None:
        self.inlet_streams.append(sl)


    def set_outlet_stream(self, sl) -> None:
        self.outlet_streams.append(sl)


    def init_boundary_states(self, state_source) -> None:
        self.state.inlet_fluid = FluidState.copy(state_source.outlet_fluid)


    def update_inlet_state(self) -> None:
        """ update inlet state based on inlet streams (mass flow rate weighted average) """
        total_mass_rate = 0.
        for sl in self.inlet_streams:
            total_mass_rate += sl.mass_rate
        T_ave, P_ave, H_ave = 0., 0., 0.
        for sl in self.inlet_streams:
            wt = sl.mass_rate / total_mass_rate
            T_ave += wt * sl.fluid_state.T
            P_ave += wt * sl.fluid_state.P
            H_ave += wt * sl.fluid_state.H
        self.state.mass_rate = total_mass_rate
        try:
            self.state.inlet_fluid.updateHP(H=H_ave, P=P_ave)
        except:
            self.state.inlet_fluid.updatePT(P=P_ave, T=T_ave)


    def update_outlet_streams(self) -> None:
        """ update outlet state based assuming uniform stream distribution """
        for sl in self.outlet_streams:
            sl.mass_rate = self.state.mass_rate / len(self.outlet_streams)
            try:
                sl.fluid_state.updateHP(H=self.state.outlet_fluid.H, P=self.state.outlet_fluid.P)
            except:
                sl.fluid_state.updatePT(P=self.state.outlet_fluid.P, T=self.state.outlet_fluid.T)
