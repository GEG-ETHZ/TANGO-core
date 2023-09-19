from tango.core import FluidState


class StreamState:

    def __init__(self) -> None:
        self.mass_rate: float = 0.0
        self.fluid_state: FluidState



class Stream:

    def __init__(self, id: str, state) -> None:
        self.id = id
        self.state = StreamState()
        self.state.mass_rate = state.mass_rate
        self.state.fluid_state = state.outlet_fluid

