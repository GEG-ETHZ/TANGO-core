from tango.core.abstracts.stream import *
from tango.core import FluidState


class StreamStateNative(StreamState):
    def __init__(self) -> None:
        StreamState.__init__(self)
        self.mass_rate: float = 0.0
        self.fluid_state: FluidState



class StreamNative(Stream):

    def __init__(self, id: str) -> None:
        super().__init__(id)


    def init_state(self, state) -> None:
        self.state = StreamStateNative()
        self.state.fluid_state = state.outlet_fluid
        self.state.mass_rate = state.mass_rate

