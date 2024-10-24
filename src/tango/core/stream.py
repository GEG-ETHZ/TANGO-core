from tango.core import FluidState

class StreamState:
    """
    Represents the state of a stream, including its mass flow rate and fluid properties.

    Attributes:
        mass_rate (float): The mass flow rate of the stream in kg/s.
        fluid_state (FluidState): The fluid state of the stream.
    """

    def __init__(self) -> None:
        """
        Initializes a new instance of the StreamState class with default values.

        The `mass_rate` is set to 0.0 by default, and `fluid_state` is expected
        to be assigned externally to represent the fluid state.
        """
        self.mass_rate: float = 0.0
        self.fluid_state: FluidState


class Stream:
    """
    Represents a fluid stream with a unique identifier and a defined state.

    Attributes:
        id (str): A unique identifier for the stream.
        state (StreamState): The state of the stream, including mass rate and fluid properties.
    """

    def __init__(self, id: str, state) -> None:
        """
        Initializes a new instance of the Stream class.

        Args:
            id (str): A unique identifier for the stream.
            state: An object containing information to initialize the stream's state.
                Expected to have `mass_rate` and `outlet_fluid` attributes, where:
                - `mass_rate` (float): The mass flow rate of the stream in kg/s.
                - `outlet_fluid` (FluidState): The fluid state of the stream.

        Example:
            .. code-block:: python

                fluid_state = FluidState(...)
                initial_state = SomeStateObject(mass_rate=1.5, outlet_fluid=fluid_state)
                stream = Stream(id="Stream_01", state=initial_state)
        """
        self.id = id
        self.state = StreamState()
        self.state.mass_rate = state.mass_rate
        self.state.fluid_state = state.outlet_fluid
