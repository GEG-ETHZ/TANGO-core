from abc import ABC


class StreamSpecs(ABC):
    pass


class StreamState(ABC):

    def __init__(self):
        pass


class Stream(ABC):

    def __init__(self, id) -> None:
        self.id = id

