from abc import ABC
from dataclasses import dataclass


class ReservoirSpecs(ABC):
    """Implements the common interface for classes providing reservoir specifications."""
    pass


class ReservoirState(ABC):
    """Implements the common interface for classes defining state for reservoir modeling computations."""

    def __init__(self):
        self.mass_rate: float = 0.0
        self.inlet_pressure: list[float]
        self.inlet_temperature: list[float]
        self.outlet_pressure: list[float]
        self.outlet_temperature: list[float]
    
    def update(self, specs: ReservoirSpecs) -> None:
        pass


class ReservoirModel(ABC):
    """Implements the common interface for classes providing reservoir modeling capabilities."""

    def execute(self, state: ReservoirState) -> None:
        pass

