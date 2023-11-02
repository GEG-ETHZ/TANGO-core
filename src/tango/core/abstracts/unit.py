from abc import ABC
from tango.core import FluidState


class UnitSpecs(ABC):
    pass


class UnitState(ABC):

    def __init__(self):
        self.mass_rate: float = 0.0
        self.inlet_fluid: FluidState
        self.outlet_fluid: FluidState

    def update(self) -> None:
        pass


class Unit(ABC):

    def __init__(self, id, specs) -> None:
        self.id = id
        self.specs = specs
        self.inlet_streams = list()
        self.outlet_streams = list()


    def set_inlet_stream(self, sl) -> None:
        self.inlet_streams.append(sl)


    def set_outlet_stream(self, sl) -> None:
        self.outlet_streams.append(sl)


    def init_inlet_state(self, inlet_state) -> None:
        self.state.inlet_fluid = FluidState.copy(inlet_state.outlet_fluid)


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


    def init_state(self) -> None:
        raise NotImplementedError("Implement 'init_state' method in your derived Unit class.")


    def execute(self) -> None:
        raise NotImplementedError("Implement 'execute' method in your derived Unit class.")
