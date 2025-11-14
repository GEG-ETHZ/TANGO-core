from enum import Enum, auto
from abc import ABC, abstractmethod

from tango.core import FluidState


class UnitSpecs(ABC):
    """
    Abstract base class for unit specifications.
    Extend this class to define specific specifications for different units.
    """
    pass

class Unit(ABC):
    r"""
    Abstract Base Unit for process simulations.

    Represents a unit operation in a process flow, handling mass and energy balances
    between inlet and outlet streams.

    Attributes:
        id (str): Unique identifier for the unit.
        specs (dict): Specifications for the unit.
        inlet_streams (list): List of inlet streams to the unit.
        outlet_streams (list): List of outlet streams from the unit.
        mass_rate (float): Total mass flow rate through the unit (kg/s).
        inlet_fluid (FluidState): Fluid state of the inlet.
        outlet_fluid (FluidState): Fluid state of the outlet.
    """

    def __init__(self, id, specs) -> None:
        """
        Initializes a new instance of the Unit class.

        Args:
            id (str): Unique identifier for the unit.
            specs (dict): Specifications for the unit.
        """
        self.id = id
        self.specs = specs
        self.inlet_streams = []
        self.outlet_streams = []
        self.mass_rate: float = 0.0
        self.inlet_fluid: FluidState
        self.outlet_fluid: FluidState

    def set_inlet_stream(self, sl) -> None:
        """
        Adds an inlet stream to the unit.

        Args:
            sl: Stream to be added as an inlet.
        """
        self.inlet_streams.append(sl)

    def set_outlet_stream(self, sl) -> None:
        """
        Adds an outlet stream to the unit.

        Args:
            sl: Stream to be added as an outlet.
        """
        self.outlet_streams.append(sl)

    def init_inlet_state(self, inlet_state) -> None:
        """
        Initializes the inlet fluid state by copying the outlet state of the previous unit.

        Args:
            inlet_state: The previous unit's outlet fluid state.
        """
        self.inlet_fluid = FluidState.copy(inlet_state.outlet_fluid)

    def update_inlet_state(self) -> None:
        r"""
        Updates the inlet fluid state based on mass flow rate weighted averages of inlet streams.

        Formula:
            .. math::
                T_{ave} = \frac{\sum_{i} \dot{m}_i \cdot T_i}{\sum_{i} \dot{m}_i}
                P_{ave} = \frac{\sum_{i} \dot{m}_i \cdot P_i}{\sum_{i} \dot{m}_i}
                H_{ave} = \frac{\sum_{i} \dot{m}_i \cdot H_i}{\sum_{i} \dot{m}_i}

        Where:
            - \( \dot{m}_i \): Mass flow rate of stream \( i \).
            - \( T_i, P_i, H_i \): Temperature, pressure, and enthalpy of stream \( i \).
        """
        total_mass_rate = sum(sl.mass_rate for sl in self.inlet_streams)
        T_ave, P_ave, H_ave = 0.0, 0.0, 0.0
        for sl in self.inlet_streams:
            wt = sl.mass_rate / total_mass_rate
            T_ave += wt * sl.fluid_state.T
            P_ave += wt * sl.fluid_state.P
            H_ave += wt * sl.fluid_state.H
        self.mass_rate = total_mass_rate
        try:
            self.inlet_fluid.updateHP(H=H_ave, P=P_ave)
        except:
            self.inlet_fluid.updatePT(P=P_ave, T=T_ave)

    def update_outlet_streams(self) -> None:
        r"""
        Updates the outlet streams based on the outlet fluid state, assuming uniform distribution.

        Each outlet stream receives an equal share of the mass flow rate and the same
        fluid state properties.
        """
        for sl in self.outlet_streams:
            sl.mass_rate = self.mass_rate / len(self.outlet_streams)
            try:
                sl.fluid_state.updateHP(H=self.outlet_fluid.H, P=self.outlet_fluid.P)
            except:
                sl.fluid_state.updatePT(P=self.outlet_fluid.P, T=self.outlet_fluid.T)

    def init_state(self) -> None:
        """
        Abstract method to initialize the unit state.

        Raises:
            NotImplementedError: This method must be implemented in derived classes.
        """
        raise NotImplementedError("Implement 'init_state' method in your derived Unit class.")

    def stream_interface(self) -> None:
        """
        Abstract method to execute the unit operation.

        Raises:
            NotImplementedError: This method must be implemented in derived classes.
        """
        raise NotImplementedError("Implement 'stream_interface' method in your derived Unit class.")


class FlowResistance(ABC):
    """Provides interface for simple resistance calculations"""

    @abstractmethod
    def flow_res(self) -> float:
        """Return module/component flow resistance as either pressure drop per mass flow
        rate or pressure drop per volume flow rate
        """
        pass
